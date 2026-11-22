"""Вызовы опубликованных MCP-серверов с локальными ответами внешних API."""

import asyncio
from hashlib import sha256
import json
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from external_runtime import NODE_RUNTIME, ROOT, isolation_check, sandbox_policy
from mcp_compat import ToolContract
from mcp_compat.benchmark import RecoveryInput
from schema_keyword_study import Case

CATALOGS = ROOT / "tests/fixtures/schema-keyword-catalogs.json"
VERSIONS = {
    "firecrawl": ("3.24.0", "3.25.0"),
    "randomuser": ("531e85abff91c3ecf08cba9ace21b8ff440930dd", "28d483c3492dd53bb739fbc499da0d3854e751cd"),
    "docx": ("v0.4.0", "v0.5.0"),
}
TOOLS = {"firecrawl": "firecrawl_parse", "randomuser": "get_multiple_users", "docx": "docx-create"}


def package(source, version):
    if source == "firecrawl":
        base = NODE_RUNTIME / "npm/firecrawl-mcp" / version
        location = base / "node_modules/firecrawl-mcp"
        metadata = json.loads((location / "package.json").read_bytes())
        provenance = json.loads((base / "package-lock.json").read_bytes())["packages"]["node_modules/firecrawl-mcp"]
        if metadata["version"] != version or provenance["version"] != version:
            raise ValueError("Версия Firecrawl отличается от зафиксированной")
        return location, location / metadata["bin"]["firecrawl-mcp"], provenance["integrity"]
    location = NODE_RUNTIME / "source" / source / version
    metadata = json.loads((location / "package.json").read_bytes())
    endpoint = metadata.get("main", "dist/index.js")
    digest = sha256((location / "source.tar.gz").read_bytes()).hexdigest()
    return location, location / endpoint, digest


async def probe(source, version, arguments=None):
    location, entry, integrity = package(source, version)
    tool = TOOLS[source]
    with TemporaryDirectory(prefix="mcp-keyword-", dir="/private/tmp") as temporary:
        work = Path(temporary)
        preload = work / "fixture.mjs"
        copyfile(Path(__file__).with_name("schema_keyword_fixtures.mjs"), preload)
        fixture = work / "fixture.html"
        fixture.write_text("<h1>Контрольный документ</h1>", encoding="utf-8")
        params = StdioServerParameters(
            command="/usr/bin/sandbox-exec",
            args=["-p", sandbox_policy(work), "/opt/homebrew/bin/node", "--import", str(preload), str(entry)],
            cwd=work, env={"HOME": temporary, "TMPDIR": temporary, "PATH": "/usr/bin:/bin:/opt/homebrew/bin",
                "FIRECRAWL_API_KEY": "fc-local-fixture", "FIRECRAWL_API_URL": "https://fixture.invalid",
                "NO_TELEMETRY": "1", "KEYWORD_SOURCE": source, "KEYWORD_PACKAGE_DIR": str(location)},
        )
        with (work / "server.log").open("w") as log:
            async with stdio_client(params, errlog=log) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await asyncio.wait_for(session.initialize(), 15)
                    if arguments is None:
                        reply = await asyncio.wait_for(session.list_tools(), 15)
                        item = next(item for item in reply.tools if item.name == tool)
                        return {"integrity": integrity, "tool": item.model_dump(mode="json", exclude_none=True)}
                    if source == "firecrawl" and arguments.get("filePath") != fixture.name:
                        raise ValueError("Путь за пределами тестового сценария")
                    reply = await asyncio.wait_for(session.call_tool(tool, arguments), 15)
                    if reply.isError:
                        raise ValueError("MCP-сервер отклонил вызов")
        requests = [json.loads(line) for line in (work / "requests.jsonl").read_text().splitlines()]
        state = {"api_requests": requests, "fixture_html": fixture.read_text() if fixture.exists() else None}
        return reply.model_dump(mode="json", exclude_none=True), state


async def catalog():
    return {source: {version: await probe(source, version) for version in versions}
            for source, versions in VERSIONS.items()}


def published_inputs(catalogs):
    cases = [
        ("parse_html", "firecrawl", "propertyNames", {"filePath": "fixture.html"}, False),
        ("parse_empty_schema", "firecrawl", "propertyNames",
         {"filePath": "fixture.html", "formats": ["json"], "jsonOptions": {"schema": {}}}, False),
        ("parse_closed_schema", "firecrawl", "propertyNames",
         {"filePath": "fixture.html", "formats": ["json"], "jsonOptions": {"schema": {"type": "object"}}}, False),
        ("users_weights", "randomuser", "patternProperties",
         {"count": 4, "nationality": ["US", "GB"], "gender": "female", "nationalityWeights": {"US": .75, "GB": .25}}, True),
        ("users_equal_weights", "randomuser", "patternProperties",
         {"count": 4, "nationality": ["US", "GB"], "gender": "female", "nationalityWeights": {"US": .5, "GB": .5}}, True),
        ("users_invalid_weight", "randomuser", "patternProperties",
         {"count": 4, "nationality": ["US", "GB"], "gender": "female", "nationalityWeights": {"US": 1.3, "GB": .5}}, False),
    ]
    for name, source, keyword, arguments, recoverable in cases:
        entries = [catalogs[source][version] for version in VERSIONS[source]]
        old, new = (ToolContract(name=row["tool"]["name"], description=row["tool"].get("description"),
            input_schema=row["tool"]["inputSchema"], output_schema=row["tool"].get("outputSchema")) for row in entries)
        request = RecoveryInput.model_validate({"old_contract": old, "new_contract": new,
            "old_call": {"tool_name": old.name, "arguments": arguments}})
        yield name, source, keyword, request, recoverable, tuple(row["integrity"] for row in entries)


def published_cases():
    isolation_check()
    frozen = json.loads(CATALOGS.read_bytes())
    if asyncio.run(catalog()) != frozen:
        raise ValueError("Каталог или контрольная сумма не совпадает с зафиксированной")

    def handler(source, version):
        def invoke(arguments, state):
            reply, observed_state = asyncio.run(probe(source, version, arguments))
            state.update(observed_state)
            return reply
        return invoke

    return [Case(name, keyword, request, *[handler(source, v) for v in VERSIONS[source]],
        ("api_requests", "fixture_html"), recoverable, integrity)
        for name, source, keyword, request, recoverable, integrity in published_inputs(frozen)]


if __name__ == "__main__":
    isolation_check()
    print(json.dumps(asyncio.run(catalog()), ensure_ascii=False, indent=2))
