from copy import deepcopy
from importlib.metadata import version
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import subprocess

import pytest

if version("mcp") != "2.3.0":
    pytest.skip("NOT RUN: separate SDK 2.3.0 environment required", allow_module_level=True)

import anyio
from mcp import Client, StdioServerParameters, types
from mcp.client._memory import InMemoryTransport
from mcp.shared.message import SessionMessage
from pydantic import TypeAdapter

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"examples"))
from mcp2026_server import make_proxy_2026, make_server_2026
from mcp_compat import SchemaDiffEngine, ToolContract
from mcp_compat.hybrid import Hybrid
from mcp_compat.recovery import NoRecovery
from mcp_compat.schema import validate_instance
from mcp_compat.verification import EvidenceVerifier, ObservationProfile


class RecordingTransport:
    def __init__(self, server):
        self.transport = InMemoryTransport(server)
        self.messages = []

    async def __aenter__(self):
        read, write = await self.transport.__aenter__()
        return read, TapSend(write, self.messages)

    async def __aexit__(self, *args):
        await self.transport.__aexit__(*args)


class TapSend:
    def __init__(self, write, messages):
        self.write, self.messages = write, messages

    async def __aenter__(self):
        return self

    async def send(self, item):
        self.messages.append(item.message.model_dump(mode="json", by_alias=True, exclude_none=True))
        await self.write.send(item)

    async def aclose(self):
        await self.write.aclose()

    async def __aexit__(self, *args):
        await self.aclose()


def contract():
    return ToolContract(name="echo", input_schema=dict(type="object", properties=dict(x={"type":"integer"}),
        required=["x"]), output_schema=dict(type="object", properties=dict(x={"type":"integer"}), required=["x"]))


async def echo(arguments):
    return arguments


def test_modern_wire_meta_without_handshake_and_legacy_mode():
    async def run():
        for mode in ("2026-07-28", "legacy"):
            transport = RecordingTransport(make_server_2026(contract(), echo))
            async with Client(transport, mode=mode) as client:
                tools = (await client.list_tools()).tools
                assert tools[0].input_schema == contract().input_schema
                result = await client.call_tool("echo", dict(x=3))
                assert not result.is_error and result.structured_content == dict(x=3)
                assert client.protocol_version == ("2026-07-28" if mode != "legacy" else "2025-11-25")
            methods = [m.get("method") for m in transport.messages]
            if mode == "legacy":
                assert "initialize" in methods
            else:
                assert "initialize" not in methods and "notifications/initialized" not in methods
                schema = json.loads((Path(__file__).resolve().parents[2]/"protocol/mcp-2026-07-28/schema.json").read_bytes())
                for message in transport.messages:
                    meta = message["params"]["_meta"]
                    assert meta["io.modelcontextprotocol/protocolVersion"] == "2026-07-28"
                    assert "io.modelcontextprotocol/clientCapabilities" in meta
                    assert "io.modelcontextprotocol/clientInfo" in meta
                    name = "ListToolsRequest" if message["method"] == "tools/list" else "CallToolRequest"
                    validate_instance(message, dict(schema, **{"$ref":"#/$defs/"+name}))
    anyio.run(run)


def test_full_jsonschema_validation_is_separate_from_migration():
    async def run():
        c = contract()
        c.input_schema.update({"$defs":{"positive":{"type":"integer","minimum":1,"$anchor":"positive"}},
            "properties":{"x":{"$ref":"#positive"}},
            "allOf":[{"anyOf":[{"required":["x"]}]}],
            "oneOf":[{"properties":{"x":{"type":"integer"}}}],
            "not":{"properties":{"x":{"const":13}}},
            "if":{"properties":{"x":{"minimum":10}}},"then":{"properties":{"x":{"multipleOf":2}}},
            "else":{"properties":{"x":{"maximum":9}}}})
        assert not SchemaDiffEngine.compare(c,c).is_complete
        async with Client(InMemoryTransport(make_server_2026(c,echo)),mode="2026-07-28") as client:
            assert not (await client.call_tool("echo",{"x":2})).is_error
            for value in (0,13,11):
                assert (await client.call_tool("echo",{"x":value})).is_error
        # Новая редакция допускает structuredContent-массив; старый профиль не расширяется.
        c = contract().model_copy(update={"output_schema":{"type":"array","items":{"type":"integer"}}})
        async def array(a):
            return [a["x"]]
        async with Client(InMemoryTransport(make_server_2026(c,array)),mode="2026-07-28") as client:
            assert (await client.call_tool("echo",{"x":2})).structured_content == [2]
    anyio.run(run)


@pytest.mark.parametrize("behavior", ["raise", "invalid", "nonfinite", "null"])
def test_tool_errors_do_not_expose_private_details(behavior):
    async def implementation(a):
        if behavior == "raise":
            raise RuntimeError("PRIVATE")
        return {"x":"wrong"} if behavior == "invalid" else {"x":float("nan")} if behavior == "nonfinite" else None
    async def run():
        async with Client(InMemoryTransport(make_server_2026(contract(),implementation)),mode="2026-07-28") as client:
            result = await client.call_tool("echo",{"x":2})
            assert result.is_error and "PRIVATE" not in str(result)
            with pytest.raises(Exception):
                await client.call_tool("missing",{})
    anyio.run(run)


def test_verified_proxy_and_abstention():
    async def run():
        c = contract()
        profile = ObservationProfile(name="closed", complete=True, closed_environment=True,
            deterministic=True, unambiguous=True)
        verifier = EvidenceVerifier(c,c,lambda a,s:a,lambda a,s:a,profile=profile,
            handler_ids=("echo-1","echo-1"))
        async with Client(InMemoryTransport(make_server_2026(c,echo)),mode="2026-07-28") as upstream:
            for strategy, expected_error in [(Hybrid(verifier=verifier),False),(Hybrid(),True)]:
                server = make_proxy_2026(c,c,upstream,strategy)
                async with Client(InMemoryTransport(server),mode="2026-07-28") as proxy:
                    result = await proxy.call_tool("echo",dict(x=4))
                    assert result.is_error == expected_error
            for timeout in (0,float("inf"),float("nan")):
                with pytest.raises(ValueError):
                    make_proxy_2026(c,c,upstream,NoRecovery(),timeout=timeout)
            changed = deepcopy(c)
            changed.name = "missing"
            async with Client(InMemoryTransport(make_proxy_2026(c,changed,upstream,NoRecovery())),mode="2026-07-28") as proxy:
                assert (await proxy.call_tool("echo",dict(x=4))).is_error
    anyio.run(run)


def test_missing_meta_unknown_version_and_method_rejected_on_wire():
    async def run():
        base = {"io.modelcontextprotocol/protocolVersion":"2026-07-28",
                "io.modelcontextprotocol/clientCapabilities":{}}
        messages = [dict(jsonrpc="2.0", id=1, method="tools/list", params={}),
            dict(jsonrpc="2.0", id=2, method="tools/list", params={"_meta":dict(base, **{"io.modelcontextprotocol/protocolVersion":"2099-01-01"})}),
            dict(jsonrpc="2.0", id=3, method="tools/missing", params={"_meta":base}),
            dict(jsonrpc="2.0", id=4, method="tools/list", params={"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28"}})]
        for message in messages:
            async with InMemoryTransport(make_server_2026(contract(),echo)) as (read,write):
                await write.send(SessionMessage(TypeAdapter(types.JSONRPCMessage).validate_python(message)))
                with anyio.fail_after(3):
                    response = await read.receive()
                body = response.message.model_dump(mode="json",by_alias=True,exclude_none=True)
                assert "error" in body
                assert body["error"]["code"] < 0
    anyio.run(run)


def test_actual_sdk1_sdk2_interoperation():
    legacy_python = os.environ.get("MCP_COMPAT_LEGACY_PYTHON")
    if not legacy_python:
        pytest.skip("NOT RUN: MCP_COMPAT_LEGACY_PYTHON with SDK 1.30.0 required")
    root = Path(__file__).resolve().parents[2]

    async def modern_to_legacy():
        params = StdioServerParameters(command=legacy_python,args=[str(root/"examples/mcp_server.py")],
            env={"PYTHONPATH":str(root/"src")})
        async with Client(params,mode="auto") as client:
            assert client.protocol_version == "2025-11-25"
            tools = (await client.list_tools()).tools
            assert tools[0].name == "check_migration"
    anyio.run(modern_to_legacy)
    program = '''import anyio,sys
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
async def run():
 p=StdioServerParameters(command=sys.argv[1],args=[sys.argv[2]],env={'PYTHONPATH':sys.argv[3]})
 async with stdio_client(p) as (r,w):
  async with ClientSession(r,w) as client:
   initialized=await client.initialize()
   assert initialized.protocolVersion=='2025-11-25'
   result=await client.call_tool('echo',{'legacy':True})
   assert not result.isError and result.structuredContent=={'legacy':True}
anyio.run(run)
'''
    result = subprocess.run([legacy_python,"-c",program,sys.executable,str(root/"examples/mcp2026_server.py"),
                             str(root/"src")],text=True,capture_output=True,timeout=20)
    assert result.returncode == 0, result.stderr


def test_official_schema_source_integrity():
    directory = Path(__file__).resolve().parents[2]/"protocol/mcp-2026-07-28"
    provenance = json.loads((directory/"provenance.json").read_bytes())
    assert provenance["commit"] == "271ecc9accafdd9b83a3c869fa67c22953b2af80"
    for name, digest in provenance["files"].items():
        assert sha256((directory/name).read_bytes()).hexdigest() == digest
    assert 'LATEST_PROTOCOL_VERSION = "2026-07-28"' in (directory/"schema.ts").read_text()
