"""Этот процесс и дочерние серверы работают только под OS sandbox."""

import ast
import json
from pathlib import Path
import sqlite3
import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run(payload):
    work = Path(payload["work"])
    project, era = payload["project"], payload["era"]
    state = payload["state"]
    source = Path(payload["source"])
    env = dict(HOME=str(work), TMPDIR=str(work), PYTHONDONTWRITEBYTECODE="1")
    if project == "fs":
        for name, text in state.get("files", {"data.txt": "alpha\nbeta\ngamma\n"}).items():
            if Path(name).name != name:
                raise ValueError("fixture filenames must be flat")
            (work/name).write_text(text)
        command = "/opt/homebrew/bin/node"
        args = [str(Path(payload["node_runtime"])/era/"index.js"), str(work)]
    elif project == "sqlite":
        database = work/"fixture.db"
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT, qty INTEGER)")
            connection.executemany("INSERT INTO items VALUES (:id,:name,:qty)", state.get("rows", []))
        command = sys.executable
        args = ["-c", "import asyncio,runpy,sys; asyncio.run(runpy.run_path(sys.argv[1])['main'](sys.argv[2]))",
                str(source/"server.py"), str(database)]
    else:
        command = sys.executable
        args = ["-c", "import runpy,sys; runpy.run_path(sys.argv[1])['main']()", str(source/"server.py")]
    params = StdioServerParameters(command=command, args=args, env=env, cwd=str(work))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            tools = (await client.list_tools()).tools
            if payload["tool"] is None:
                return dict(tools=[t.model_dump(mode="json", exclude_none=True) for t in tools])
            arguments = payload["arguments"]
            if project == "fs":
                arguments = dict(arguments, path=str(work/arguments["path"]))
            result = await client.call_tool(payload["tool"], arguments)
            if result.isError:
                raise ValueError("external tool returned an execution error")
            content = [c.model_dump(mode="json", exclude_none=True) for c in result.content]
    observed = dict(result=result.structuredContent if result.structuredContent is not None else content, state={})
    if project == "fs":
        observed["state"] = dict(files={p.name:p.read_text() for p in sorted(work.iterdir()) if p.is_file()})
    elif project == "sqlite":
        with sqlite3.connect(database) as connection:
            connection.row_factory = sqlite3.Row
            rows = [dict(row) for row in connection.execute("SELECT * FROM items ORDER BY id")]
        observed["state"] = dict(rows=rows)
        # Числа/строки из фактического TextContent, не эталон ожидаемого запроса.
        observed["result"] = ast.literal_eval(content[0]["text"])
    return observed


if __name__ == "__main__":
    print(json.dumps(anyio.run(run, json.load(sys.stdin)), ensure_ascii=False))
