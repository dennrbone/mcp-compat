"""Изолированный запуск закреплённых внешних серверов, без пользовательских данных."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "benchmark/external-mcp/vendor"
NODE_RUNTIME = Path(os.environ.get("MCP_EXTERNAL_NODE_RUNTIME", "/private/tmp/mcp-external-filesystem"))


def sandbox_policy(work: Path) -> str:
    reads = ["/System", "/usr", "/Library", "/opt/homebrew", "/dev",
             sys.base_prefix, sys.prefix, str(VENDOR), str(NODE_RUNTIME),
             str(Path(__file__).with_name("external_worker.py")), str(work)]
    return "\n".join([
        "(version 1)", "(deny default)", "(allow process-exec)", "(allow process-fork)",
        "(allow signal (target same-sandbox))", "(allow sysctl-read)",
        "(allow file-read-metadata)",
        '(allow file-read-data (literal "/"))',
        *[f"(allow file-read* (subpath {json.dumps(p)}))" for p in reads],
        f"(allow file-write* (subpath {json.dumps(str(work))}))",
    ])


def execute(project: str, era: str, *, tool: str | None = None,
            arguments: dict | None = None, state: dict | None = None) -> dict:
    if project not in ("fs", "sqlite", "calculator") or era not in ("old", "new"):
        raise ValueError("unknown pinned runtime")
    if project == "fs" and (NODE_RUNTIME/"package-lock.json").read_bytes() != (ROOT/"examples/external-filesystem/package-lock.json").read_bytes():
        raise ValueError("external Node dependency lock mismatch")
    with tempfile.TemporaryDirectory(prefix="mcp-external-", dir="/private/tmp") as temporary:
        work = Path(temporary).resolve()
        payload = dict(project=project, era=era, source=str(VENDOR/project/era),
                       work=str(work), node_runtime=str(NODE_RUNTIME),
                       tool=tool, arguments=arguments, state=state or {})
        env = dict(PATH="/usr/bin:/bin:/opt/homebrew/bin", HOME=str(work), TMPDIR=str(work),
                   PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run(["/usr/bin/sandbox-exec", "-p", sandbox_policy(work),
            sys.executable, str(Path(__file__).with_name("external_worker.py"))],
            input=json.dumps(payload), text=True, capture_output=True, timeout=30, env=env, cwd=work)
        if result.returncode:
            raise RuntimeError(f"external runtime failed: {result.stderr[:1400]}\n{result.stderr[-800:]}")
        return json.loads(result.stdout)


def isolation_check() -> dict:
    """Настоящие отрицательные пробы чтения, записи и сети под той же политикой."""
    with tempfile.TemporaryDirectory(prefix="mcp-isolation-", dir="/private/tmp") as tmp:
        work = Path(tmp).resolve()
        marker = ROOT / ".git/HEAD"
        program = (
            "import json,pathlib,socket\n"
            "checks={}\n"
            f"for name,operation in [('read',lambda:pathlib.Path({str(marker)!r}).read_bytes()),"
            "('write',lambda:pathlib.Path('/private/tmp/mcp-external-forbidden').write_text('x')),"
            "('network',lambda:socket.create_connection(('127.0.0.1',9),timeout=1))]:\n"
            " try: operation(); checks[name+'_denied']={'denied':False}\n"
            " except PermissionError as error: checks[name+'_denied']={'denied':True,'exception':'PermissionError','errno':error.errno}\n"
            "print(json.dumps(checks))\n"
        )
        result = subprocess.run(["/usr/bin/sandbox-exec", "-p", sandbox_policy(work),
                                 sys.executable, "-c", program], capture_output=True, text=True, timeout=10,
                                 cwd=work, env=dict(PATH="/usr/bin:/bin", HOME=str(work), TMPDIR=str(work)))
        if result.returncode:
            raise RuntimeError(result.stderr[-1000:])
        checks = json.loads(result.stdout)
        if not all(check["denied"] for check in checks.values()):
            raise RuntimeError("OS isolation preflight failed")
        return checks


if __name__ == "__main__":
    print(json.dumps(isolation_check()))
