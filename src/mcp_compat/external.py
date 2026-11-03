"""Внешние входы отделены от эталонов; этот загрузчик ничего не исполняет."""

import json
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import Field

from mcp_compat import ToolCall, canonical_bytes
from mcp_compat.benchmark import RecoveryInput
from mcp_compat.domain.scenarios import MutationFamily
from mcp_compat.llm import StrictModel
from mcp_compat.verification import ObservationProfile, fingerprint

VERSION = "external-mcp-1.0"


class ExternalCase(StrictModel):
    case_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    project: Literal["fs", "sqlite", "calculator"]
    kind: Literal["historical", "constructed"]
    family: MutationFamily
    request: RecoveryInput
    candidate: ToolCall
    initial: dict
    alteration: str = "none"
    profile: ObservationProfile


def _manifest(directory: Path, expected_digest: str) -> dict:
    manifest = json.loads((directory/"manifest.json").read_bytes())
    content = {k:v for k,v in manifest.items() if k != "digest"}
    if manifest["version"] != VERSION or fingerprint(content) != expected_digest or manifest["digest"] != expected_digest:
        raise ValueError("external manifest integrity failure")
    return manifest


def _file(directory: Path, name: str, expected: str) -> bytes:
    path = directory/name
    if path.resolve() != directory.resolve()/name:
        raise ValueError("external file path must not be a symlink")
    data = path.read_bytes()
    if sha256(data).hexdigest() != expected:
        raise ValueError("external document integrity failure")
    return data


def _document(directory: Path, manifest: dict, name: str):
    return json.loads(_file(directory, name, manifest["files"][name]))


def load_inputs(directory: Path, expected_digest: str) -> list[ExternalCase]:
    """Не открывает gold.json; допускает независимую работу без файла эталонов."""
    manifest = _manifest(directory, expected_digest)
    provenance = _document(directory, manifest, "provenance.json")
    for project in provenance.values():
        for name, digest in project["files"].items():
            if Path(name).is_absolute() or ".." in Path(name).parts:
                raise ValueError("invalid external source path")
            _file(directory, name, digest)
    cases = [ExternalCase.model_validate_json(canonical_bytes(row)) for row in _document(directory, manifest, "public.json")]
    if not cases or len({c.case_id for c in cases}) != len(cases) or len(cases) != manifest["count"]:
        raise ValueError("external case identity/count mismatch")
    for case in cases:
        if case.request.context:
            raise ValueError("external-mcp-1.0 has no public rules or evaluation context")
        case.request.old_call.validate_against(case.request.old_contract)
    return cases


def load_gold(directory: Path, expected_digest: str) -> dict:
    """Только оценщику после решения; метод не должен вызывать эту функцию."""
    return _document(directory, _manifest(directory, expected_digest), "gold.json")
