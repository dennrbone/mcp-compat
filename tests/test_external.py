from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import shutil

import pytest

from mcp_compat import canonical_bytes
from mcp_compat.external import load_gold, load_inputs
from mcp_compat.verification import fingerprint

DATA = Path(__file__).resolve().parents[1]/"benchmark/external-mcp"
DIGEST = "6ab2bfb7da1687012c70a8acac5254f571381af8cd03d0911d393ba41e010b8f"


def update_manifest(directory, **updates):
    path = directory/"manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest.pop("digest")
    for name in manifest["files"]:
        manifest["files"][name] = sha256((directory/name).read_bytes()).hexdigest()
    manifest.update(updates)
    manifest["digest"] = fingerprint(manifest)
    path.write_bytes(canonical_bytes(manifest))
    return manifest["digest"]


def test_pinned_sources_contracts_and_separate_gold(tmp_path):
    cases = load_inputs(DATA, DIGEST)
    assert len(cases) == 63 and sum(c.kind == "historical" for c in cases) == 12
    assert {c.project for c in cases} == {"fs", "sqlite", "calculator"}
    assert {c.family for c in cases} == {f"C{i}" for i in range(1, 9)}
    assert len(load_gold(DATA, DIGEST)) == 63
    assert all(not c.request.context for c in cases)
    shutil.copytree(DATA, tmp_path/"data")
    (tmp_path/"data/gold.json").unlink()
    assert load_inputs(tmp_path/"data", DIGEST) == cases
    with pytest.raises(FileNotFoundError):
        load_gold(tmp_path/"data", DIGEST)


def test_integrity_and_symlink_rejection(tmp_path):
    directory = tmp_path/"data"
    shutil.copytree(DATA, directory)
    with pytest.raises(ValueError, match="manifest"):
        load_inputs(directory, "wrong")
    public = directory/"public.json"
    original = public.read_bytes()
    public.write_bytes(original+b" ")
    with pytest.raises(ValueError, match="document integrity"):
        load_inputs(directory, DIGEST)
    public.unlink()
    (tmp_path/"elsewhere.json").write_bytes(original)
    public.symlink_to(tmp_path/"elsewhere.json")
    with pytest.raises(ValueError, match="symlink"):
        load_inputs(directory, DIGEST)


@pytest.mark.parametrize("issue", ["duplicate", "empty", "count", "oracle_leak", "context_leak", "invalid_call", "path", "version", "source"])
def test_loader_rejects_invalid_or_tampered_dataset(tmp_path, issue):
    directory = tmp_path/"data"
    shutil.copytree(DATA, directory)
    public = json.loads((directory/"public.json").read_bytes())
    updates = {}
    if issue == "duplicate":
        public[-1] = deepcopy(public[0])
    elif issue == "empty":
        public = []
    elif issue == "count":
        updates["count"] = 10
    elif issue == "oracle_leak":
        public[0]["request"]["oracle"] = {"expected": "private"}
    elif issue == "context_leak":
        public[0]["request"]["context"] = {"oracle": {"expected": "private"}}
    elif issue == "invalid_call":
        public[0]["request"]["old_call"]["arguments"] = {}
    elif issue == "path":
        provenance = json.loads((directory/"provenance.json").read_bytes())
        provenance["fs"]["files"]["../private.txt"] = "fake"
        (directory/"provenance.json").write_bytes(canonical_bytes(provenance))
    elif issue == "version":
        updates["version"] = "unknown"
    (directory/"public.json").write_bytes(canonical_bytes(public))
    digest = update_manifest(directory, **updates)
    if issue == "source":
        source = directory/"vendor/sqlite/old/server.py"
        source.write_bytes(source.read_bytes()+b"\n# corrupted\n")
        digest = update_manifest(directory)
    with pytest.raises(ValueError):
        load_inputs(directory, digest)
