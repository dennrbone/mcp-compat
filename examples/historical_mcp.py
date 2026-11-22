"""Isolated runtimes for the frozen Filesystem and Memory catalog changes."""

import asyncio
from base64 import b64decode
from copy import deepcopy
import json
from pathlib import Path, PurePosixPath
import stat
from tempfile import TemporaryDirectory

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import external_runtime
from mcp_compat import canonical_bytes
from mcp_compat.benchmark import RecoveryInput
from mcp_compat.experiments import _atomic
from mcp_compat.hybrid import Hybrid, normalize
from mcp_compat.verification import EvidenceVerifier, ObservationProfile

PIXEL = b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII=')
GRAPH = [
    dict(type='entity', name='alpha', entityType='sample', observations=['initial note']),
    dict(type='entity', name='beta', entityType='sample', observations=[]),
    dict(type='relation', **{'from':'alpha','to':'beta','relationType':'links'}),
]
MEMORY_LIST = dict(add_observations='results', create_entities='entities', create_relations='relations')
FIXTURES = external_runtime.ROOT / 'benchmark/external-mcp-historical'


def replace_path(value, old, new):
    if isinstance(value, dict):
        return {key: replace_path(item, old, new) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_path(item, old, new) for item in value]
    return value.replace(old, new) if isinstance(value, str) else value


def fixture_arguments(value, directory):
    if isinstance(value, dict):
        return {key: fixture_arguments(item, directory) for key, item in value.items()}
    if isinstance(value, list):
        return [fixture_arguments(item, directory) for item in value]
    if not isinstance(value, str):
        return value
    path = PurePosixPath(value)
    if ".." in path.parts or (path.is_absolute() and not path.is_relative_to("/fixture")):
        raise ValueError("path outside the experiment fixture")
    return str(directory / path.relative_to("/fixture")) if path.is_absolute() else value


def memory_json(text):
    try:
        return json.loads(text)
    except ValueError:
        return text


def old_result(project, tool, content):
    if project == 'filesystem':
        if tool == 'read_media_file':
            return {'content': content}
        assert len(content) == 1 and content[0]['type'] == 'text'
        return {'content': content[0]['text']}
    assert len(content) == 1 and content[0]['type'] == 'text'
    value = content[0]['text']
    if tool in MEMORY_LIST:
        result = {MEMORY_LIST[tool]: value}
        if tool == 'create_entities':
            result['skipped'] = []
        return result
    if tool.startswith('delete_'):
        return {'message': value, 'success': True}
    return value


async def invoke(project, version, package, tool, arguments, work, trial):
    data = work / 'fixture'
    data.mkdir()
    if project == 'filesystem':
        (data/'sample.txt').write_bytes(b'alpha\nbeta\ngamma\n')
        (data/'other.txt').write_bytes(b'omega\n')
        (data/'pixel.png').write_bytes(PIXEL)
    else:
        (data/'graph.jsonl').write_bytes(b'\n'.join(canonical_bytes(item) for item in GRAPH) + b'\n')
    package_root = external_runtime.NODE_RUNTIME/project/version/'node_modules'/package
    package_info = json.loads((package_root/'package.json').read_bytes())
    if package_info['version'] != version:
        raise ValueError('historical package version mismatch')
    binary = package_info['bin']
    entry = package_root/(binary if isinstance(binary, str) else next(iter(binary.values())))
    args = ['-p', external_runtime.sandbox_policy(work), '/opt/homebrew/bin/node', str(entry)]
    if project == 'filesystem':
        args.append(str(data))
    env = {'HOME':str(work),'TMPDIR':str(work),'XDG_CONFIG_HOME':str(work),'XDG_CACHE_HOME':str(work),
           'PATH':'/usr/bin:/bin:/opt/homebrew/bin','MEMORY_FILE_PATH':str(data/'graph.jsonl')}
    params = StdioServerParameters(command='/usr/bin/sandbox-exec', args=args, env=env, cwd=str(work))
    with (work/'server.log').open('w') as server_log:
        async with stdio_client(params, errlog=server_log) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await asyncio.wait_for(session.initialize(), 12)
                try:
                    native = fixture_arguments(arguments, data) if project == 'filesystem' else arguments
                except ValueError:
                    trial['blocked'] = True
                    raise
                trial['called'] = True
                reply = await asyncio.wait_for(session.call_tool(tool, native), 12)
                result = replace_path(reply.model_dump(mode='json', exclude_none=True), str(data), '/fixture')
                trial['response'] = result
                if reply.isError:
                    raise ValueError('tool rejected test input')
        if project == 'filesystem':
            snapshot = {}
            for path in sorted(data.rglob('*')):
                entry_mode = path.lstat().st_mode
                assert stat.S_ISDIR(entry_mode) or stat.S_ISREG(entry_mode)
                snapshot[str(path.relative_to(data))] = {
                    'mode': entry_mode, 'bytes': path.read_bytes().hex() if path.is_file() else None,
                }
        else:
            snapshot = [json.loads(line) for line in (data/'graph.jsonl').read_bytes().splitlines()]
    return result, snapshot


def cases():
    root = external_runtime.ROOT
    data = json.loads((root/'tests/fixtures/upstream-catalogs.json').read_bytes())
    arguments = json.loads((FIXTURES/'arguments.json').read_bytes())
    result = {}
    for index, change in enumerate(data['changes'], 1):
        tool = change['tool']
        releases = [data['releases'][change[key]] for key in ('before', 'after')]
        contracts = []
        for release in releases:
            item = release['tools'][tool]
            contracts.append(dict(name=tool, description=item.get('description'),
                                  input_schema=item['inputSchema'], output_schema=item.get('outputSchema')))
        project = change['before'].split('@', 1)[0]
        identifiers = [release['provenance']['dist.integrity'] for release in releases]
        result[f'{index:02}-{project}-{tool}'] = dict(
            change=change['id'], project=project, versions=[change['before'], change['after']],
            packages=[release['provenance']['package'] for release in releases], identifiers=identifiers,
            data=dict(old_contract=contracts[0], new_contract=contracts[1],
                      old_call=dict(tool_name=tool, arguments=arguments[change['id']])),
        )
    assert len(result) == len(arguments) == 23
    return result


def check_installation():
    for lock in FIXTURES.glob('*/*/package-lock.json'):
        installed = external_runtime.NODE_RUNTIME / lock.relative_to(FIXTURES)
        if not installed.is_file() or installed.read_bytes() != lock.read_bytes():
            raise ValueError(f'historical dependency lock mismatch: {installed}')


def handlers(case, request, traces):
    def build(era, release, package, contract):
        version = release.split('@', 1)[1]
        project = case['project']

        def call(arguments, state):
            trial = dict(era=era, release=release, tool=contract.name, called=False)
            traces.append(trial)
            try:
                with TemporaryDirectory(prefix='mcp-hybrid-history-', dir='/private/tmp') as temp:
                    result, snapshot = asyncio.run(invoke(project, version, package, contract.name,
                                                          arguments, Path(temp), trial))
                content = deepcopy(result['content'])
                if project == 'memory':
                    for part in content:
                        if part['type'] == 'text':
                            part['text'] = memory_json(part['text'])
                state.update(data=snapshot, client_content=content)
                if contract.output_schema is not None:
                    return result['structuredContent']
                return old_result(project, contract.name, content)
            except Exception as error:
                trial['error'] = type(error).__name__
                raise

        return call

    return [build(era, release, package, contract) for era, release, package, contract in zip(
        ('old', 'new'), case['versions'], case['packages'], (request.old_contract, request.new_contract))]


def decide(case, mapper, mode, folder):
    traces = []
    request = RecoveryInput.from_catalogs(case['data'], mode=mode, import_legacy=True)
    checker = EvidenceVerifier(request.old_contract, request.new_contract, *handlers(case, request, traces),
        profile=ObservationProfile(name='local-file-or-graph-fixture', state_components=('data','client_content'),
            complete=True, closed_environment=True, deterministic=True, unambiguous=True),
        handler_ids=tuple(case['identifiers']), timeout=55)
    decision = Hybrid(mapper, checker, mode=mode, current_state=dict).recover(request)
    return dict(decision=decision.model_dump(mode='json'), probes=traces,
                blocked_probes=sum(t.get('blocked', False) for t in traces))


def evaluate(case, decision, folder):
    if decision.action != 'EXECUTE':
        return None
    request = RecoveryInput.from_catalogs(case['data'], import_legacy=True)
    traces = []
    previous, updated = handlers(case, request, traces)
    observations = []
    try:
        for _ in range(2):
            for handle, args in ((previous, request.old_call.arguments), (updated, decision.adapted_call.arguments)):
                state = {}
                result = handle(args, state)
                observations.append(canonical_bytes(normalize(dict(result=result, state=state))))
        equivalent = len(set(observations)) == 1
    except (ValueError, RuntimeError, OSError, TimeoutError, ExceptionGroup):
        equivalent = None
    _atomic(folder/'evaluation-probes.json', traces)
    return equivalent
