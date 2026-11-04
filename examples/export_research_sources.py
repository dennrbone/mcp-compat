"""Экспорт точного экспериментального кода из сохранённой истории Git."""

import argparse
from hashlib import sha256
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def export(label, output):
    snapshots = json.loads((ROOT/"docs/validation/source-snapshots.json").read_bytes())
    record = snapshots[label]
    if output.exists():
        raise ValueError("source export directory already exists")
    paths = ["src/mcp_compat", "examples", "pyproject.toml", "requirements.lock", "benchmark"]
    data = subprocess.check_output(["git", "archive", "--format=tar", record["commit"], *paths], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        files = {}
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
                raise ValueError("unsafe archived source path")
            if member.isfile():
                stream = archive.extractfile(member)
                assert stream is not None
                files[member.name] = stream.read()
    modules = sorted(name for name in files if name.startswith("src/mcp_compat/") and name.endswith(".py"))
    assert len(modules) == record["modules"]
    assert sha256(b"".join(files[name] for name in modules)).hexdigest() == record["core_digest"]
    if "manifest_source_digest" in record:
        hashes = {name: sha256(files[name]).hexdigest() for name in modules+record["extra_sources"]}
        encoded = json.dumps(hashes, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        assert sha256(encoded).hexdigest() == record["manifest_source_digest"]
    for name, value in files.items():
        path = output/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    print(label, record["commit"], "MATCH", len(modules), "modules")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("label", choices=("phase16", "phase17", "phase18", "external-v1", "external-v2", "final-admission"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    export(args.label, args.output)
