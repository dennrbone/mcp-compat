"""Проверка исходных записей Hybrid по контрольным суммам."""

from hashlib import sha256
import json

from mcp_compat import canonical_bytes
from mcp_compat.experiments import Record


def read_before_retry(directory, backup):
    manifest = json.loads((backup/'manifest.json').read_bytes())
    identity = {k:v for k,v in manifest.items() if k not in ('created_at', 'fingerprint')}
    assert sha256(canonical_bytes(identity)).hexdigest() == manifest['fingerprint']
    digests = json.loads((backup/'result-digests.json').read_bytes())
    rows = []
    for key, expected in digests.items():
        path = backup/(key+'.json')
        record = Record.model_validate_json((path if path.exists() else directory/path.name).read_bytes())
        assert key == f'{record.repeat}-{record.method}-{record.scenario_id}'
        assert sha256(canonical_bytes(record.model_dump())).hexdigest() == expected
        rows.append(record)
    return manifest, rows
