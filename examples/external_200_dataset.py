"""Freeze 200 external scenarios while preserving the original 63 verbatim."""

from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json

from external_study import DATA, DIGEST, ROOT, native_arguments
from mcp_compat import canonical_bytes
from mcp_compat.external import ExternalCase, load_gold, load_inputs
from mcp_compat.verification import fingerprint

DATA_200 = ROOT / "benchmark/external-mcp-200"
TOTALS = {"fs": 67, "sqlite": 67, "calculator": 66}
FIELD = {"fs": "path", "sqlite": "query", "calculator": "expression"}


def workload(project, index):
    if project == "fs":
        name = f"sample-{index}.txt"
        lines = [f"{word}-{index}" for word in ("alpha", "beta", "gamma", "delta")]
        text = "\n".join(lines)
        args = {"path": name}
        expected = text
        if index % 3 == 1:
            args["head"] = 2
            expected = "\n".join(lines[:2])
        if index % 3 == 2:
            args["tail"] = 2
            expected = "\n".join(lines[-2:])
        return args, {"files": {"data.txt": f"snapshot-{index}", "other.txt": f"other-{index}", name: text}}, [
            {"type": "text", "text": expected}
        ]
    if project == "sqlite":
        row = {"id": index + 10, "name": f"sample-{index}", "qty": index * 3 + 1}
        rows = [{"id": 1, "name": "alpha", "qty": 5}, {"id": 2, "name": "beta", "qty": 9}, row]
        column = "qty" if index % 2 else "name"
        return {"query": f"SELECT {column} FROM items WHERE id={row['id']}"}, {"rows": rows}, [
            {column: row[column]}
        ]
    operand = index % 7 + 2
    expression, expected = [
        (f"{index} + {operand}", index + operand),
        (f"{index} * {operand}", index * operand),
        (f"{index} // {operand}", index // operand),
    ][index % 3]
    return {"expression": expression}, {}, {"result": str(expected)}


def extend(seed, index):
    row = seed.model_dump(mode="json")
    project, alteration = seed.project, seed.alteration
    field = FIELD[project]
    args, initial, expected = workload(project, index)
    row.update(case_id=f"{project}-{index:02}-{alteration}", initial=initial)
    row["request"]["old_call"]["arguments"] = args
    if alteration == "enum":
        choices = row["request"]["new_contract"]["input_schema"]["properties"][field]["enum"]
        choices[0] = args[field]
        row["candidate"]["arguments"] = dict(args, **{field: choices[1]})
    elif alteration == "nested":
        row["candidate"]["arguments"] = {"payload": args}
    elif alteration == "encoding":
        row["candidate"]["arguments"] = dict(args, **{field: [args[field]]})
    elif alteration == "removed":
        row["candidate"]["arguments"] = {key: value for key, value in args.items() if key != field}
    else:
        row["candidate"]["arguments"] = args
    case = ExternalCase.model_validate_json(canonical_bytes(row))
    case.request.old_call.validate_against(case.request.old_contract)
    if alteration != "required":
        case.candidate.validate_against(case.request.new_contract)
    if alteration not in ("enum", "removed", "required"):
        assert native_arguments(case, case.candidate.arguments) == args
    return case, {"result": expected, "state": initial}


def freeze(directory=DATA_200):
    base = load_inputs(DATA, DIGEST)
    gold = load_gold(DATA, DIGEST)
    cases = list(base)
    for project, total in TOTALS.items():
        seeds = [case for case in base if case.project == project and case.kind == "constructed"]
        for index in range(21, total):
            seed = seeds[(index - 21) % len(seeds)]
            case, expected = extend(seed, index)
            cases.append(case)
            gold[case.case_id] = dict(deepcopy(gold[seed.case_id]), expected=expected,
                                      basis="predetermined workload and independently checked old server")
    assert Counter(c.project for c in cases) == TOTALS
    assert Counter(c.kind for c in cases) == {"historical": 12, "constructed": 188}
    assert len({c.case_id for c in cases}) == len(gold) == 200
    assert len({fingerprint(c.request.model_dump()) for c in cases[len(base):]}) == 137
    files = {"public.json": canonical_bytes([c.model_dump() for c in cases]), "gold.json": canonical_bytes(gold)}
    manifest = dict(version="external-mcp-200-v1", count=200, source_benchmark=DIGEST,
                    counts=dict(TOTALS), files={name: sha256(data).hexdigest() for name, data in files.items()})
    manifest["digest"] = fingerprint(manifest)
    directory.mkdir(parents=True)
    for name, data in files.items():
        (directory / name).write_bytes(data)
    (directory / "manifest.json").write_bytes(canonical_bytes(manifest))
    print(manifest["digest"])


def read(name):
    if name not in ("public.json", "gold.json"):
        raise ValueError("unknown dataset artifact")
    manifest = json.loads((DATA_200 / "manifest.json").read_bytes())
    digest = manifest.pop("digest")
    data = (DATA_200 / name).read_bytes()
    if (fingerprint(manifest) != digest or manifest["source_benchmark"] != DIGEST
            or sha256(data).hexdigest() != manifest["files"][name]):
        raise ValueError("frozen dataset integrity failure")
    if name == "public.json":
        return digest, [ExternalCase.model_validate_json(canonical_bytes(row)) for row in json.loads(data)]
    return digest, json.loads(data)


if __name__ == "__main__":
    freeze()
