"""Conservative structural comparison of the supported JSON Schema subset."""

from copy import deepcopy
from typing import Any

from pydantic import BaseModel, Field

from mcp_compat.domain.contracts import ToolContract
from mcp_compat.domain.scenarios import MutationFamily
from mcp_compat.schema.canonical import canonical_json


class ContractChange(BaseModel):
    family: MutationFamily
    subtype: str
    path: str
    old_value: Any = None
    new_value: Any = None
    details: dict[str, Any] = Field(default_factory=dict)


class OpaqueChange(BaseModel):
    path: str
    reason: str
    old_value: Any = None
    new_value: Any = None


class SchemaDiff(BaseModel):
    changes: list[ContractChange] = Field(default_factory=list)
    opaque: list[OpaqueChange] = Field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.changes) or any(
            canonical_json(item.old_value) != canonical_json(item.new_value)
            for item in self.opaque
        )

    @property
    def is_complete(self) -> bool:
        return not self.opaque


def _path(parent: str, key: str) -> str:
    # JSON-quoted brackets keep arbitrary property names unambiguous.
    if key.isidentifier():
        return f"{parent}.{key}"
    return f"{parent}[{canonical_json(key)}]"


def _resolve(schema: Any, root: dict, seen: tuple[str, ...] = ()) -> Any:
    if isinstance(schema, bool):
        return schema
    node = deepcopy(schema)
    if "$id" in node:
        raise ValueError("$id resource scopes are unsupported")
    if "$ref" in node:
        ref = node["$ref"]
        if not ref.startswith("#/$defs/") or ref in seen:
            raise ValueError("only acyclic local #/$defs/ references are supported")
        if set(node) - {"$ref", "$defs"}:
            raise ValueError("$ref siblings are unsupported")
        target: Any = root
        for token in ref[2:].split("/"):
            token = token.replace("~1", "/").replace("~0", "~")
            if not isinstance(target, dict) or token not in target:
                raise ValueError("unresolved local $ref")
            target = target[token]
        if not isinstance(target, (dict, bool)):
            raise ValueError("$ref target is not a schema")
        return _resolve(target, root, seen + (ref,))
    node.pop("$defs", None)
    for name in sorted(node.get("properties", {})):
        node["properties"][name] = _resolve(node["properties"][name], root, seen)
    if "items" in node:
        node["items"] = _resolve(node["items"], root, seen)
    if "type" in node:
        value = node["type"]
        node["type"] = sorted([value] if isinstance(value, str) else value)
    if "required" in node:
        node["required"] = sorted(node["required"])
    if "enum" in node:
        node["enum"] = sorted(node["enum"], key=canonical_json)
    return node


class SchemaDiffEngine:
    @staticmethod
    def compare(old_contract: ToolContract, new_contract: ToolContract) -> SchemaDiff:
        """Compare versions of one scenario; never infer semantic equivalence."""
        result = SchemaDiff()

        def emit(family: MutationFamily, subtype: str, path: str,
                 old: Any, new: Any, **details: Any) -> None:
            result.changes.append(ContractChange(
                family=family, subtype=subtype, path=path,
                old_value=deepcopy(old), new_value=deepcopy(new), details=details,
            ))

        def opaque(path: str, reason: str, old: Any, new: Any) -> None:
            result.opaque.append(OpaqueChange(
                path=path, reason=reason, old_value=deepcopy(old), new_value=deepcopy(new),
            ))

        def walk(old: Any, new: Any, path: str, raw_old: Any, raw_new: Any) -> None:
            if isinstance(old, bool) or isinstance(new, bool):
                if old != new:
                    opaque(path, "boolean schema comparison", old, new)
                return
            supported = {"type", "properties", "required", "items", "enum", "format",
                         "semantic_unit", "$schema", "title", "description", "$comment"}
            for key in sorted((old.keys() | new.keys()) - supported):
                opaque(_path(path, key), "unsupported schema keyword", old.get(key), new.get(key))
            for key in ("title", "description", "$comment", "$schema"):
                if old.get(key) != new.get(key):
                    opaque(_path(path, key), "annotation/dialect change", old.get(key), new.get(key))
            a, b = set(old.get("type", [])), set(new.get("type", []))
            if ("null" in a) != ("null" in b):
                emit("C5", "nullable_changed", path + ".type", "null" in a, "null" in b)
            if a - {"null"} != b - {"null"}:
                family = "C7" if "object" in a | b else "C5"
                emit(family, "type_changed", path + ".type", sorted(a), sorted(b))
            for key, family, subtype in (("format", "C5", "format_changed"),
                                          ("semantic_unit", "C8", "semantic_unit_changed")):
                if old.get(key) != new.get(key):
                    emit(family, subtype, _path(path, key), old.get(key), new.get(key))
            if canonical_json(old.get("enum")) != canonical_json(new.get("enum")):
                before = {canonical_json(v) for v in old.get("enum", [])}
                after = {canonical_json(v) for v in new.get("enum", [])}
                subtype = "enum_changed"
                if "enum" in old and "enum" in new:
                    if before < after:
                        subtype = "enum_values_added"
                    elif after < before:
                        subtype = "enum_values_removed"
                emit("C6", subtype, path + ".enum", old.get("enum"), new.get("enum"))
            op, np = old.get("properties", {}), new.get("properties", {})
            required_old, required_new = set(old.get("required", [])), set(new.get("required", []))
            removed, added = set(op) - set(np), set(np) - set(op)
            # ponytail: sibling-only reference identity; cross-object mapping belongs to the semantic layer.
            ro = raw_old.get("properties", {})
            rn = raw_new.get("properties", {})
            renamed: set[str] = set()
            for name in sorted(removed.copy()):
                ref = ro.get(name, {}).get("$ref") if isinstance(ro.get(name), dict) else None
                if ref is None:
                    continue
                old_matches = [k for k, v in ro.items() if isinstance(v, dict) and v.get("$ref") == ref]
                new_matches = [k for k, v in rn.items() if isinstance(v, dict) and v.get("$ref") == ref]
                if len(old_matches) != 1 or len(new_matches) != 1:
                    continue
                target = new_matches[0]
                if target not in added or canonical_json(op[name]) != canonical_json(np[target]) or (name in required_old) != (target in required_new):
                    continue
                emit("C1", "parameter_renamed", _path(path + ".properties", name), name, target,
                     new_path=_path(path + ".properties", target), reference=ref)
                renamed.update((name, target))
                removed.remove(name)
                added.remove(target)
            for name in sorted(removed):
                emit("C4" if name in required_old else "C2", "parameter_removed",
                     _path(path + ".properties", name), op[name], None)
            for name in sorted(added):
                emit("C3" if name in required_new else "C2", "parameter_added",
                     _path(path + ".properties", name), None, np[name])
            for name in sorted(set(op) & set(np)):
                walk(op[name], np[name], _path(path + ".properties", name),
                     ro.get(name, {}), rn.get(name, {}))
            for name in sorted(required_old ^ required_new):
                if name in removed | added | renamed:
                    continue
                emit("C3", "required_changed", _path(path + ".required", name),
                     name in required_old, name in required_new)
            if "items" in old or "items" in new:
                walk(old.get("items", {}), new.get("items", {}), path + ".items",
                     raw_old.get("items", {}), raw_new.get("items", {}))

        if old_contract.name != new_contract.name:
            emit("C1", "tool_renamed", "name", old_contract.name, new_contract.name)
        if old_contract.description != new_contract.description:
            opaque("description", "tool description change", old_contract.description, new_contract.description)
        for key in sorted(old_contract.metadata.keys() | new_contract.metadata.keys()):
            old, new = old_contract.metadata.get(key), new_contract.metadata.get(key)
            if canonical_json(old) != canonical_json(new):
                if key == "semantic_unit":
                    emit("C8", "semantic_unit_changed", "metadata.semantic_unit", old, new)
                else:
                    opaque(_path("metadata", key), "uninterpreted metadata", old, new)
        for path, old, new in (("input", old_contract.input_schema, new_contract.input_schema),
                               ("output", old_contract.output_schema, new_contract.output_schema)):
            if old is None or new is None:
                if old != new:
                    opaque(path, "output schema added/removed", old, new)
                continue
            try:
                resolved_old, resolved_new = _resolve(old, old), _resolve(new, new)
            except ValueError as error:
                opaque(path, str(error), old, new)
                continue
            walk(resolved_old, resolved_new, path, old, new)
        result.changes.sort(key=lambda c: (c.family, c.path, c.subtype))
        result.opaque.sort(key=lambda c: (c.path, c.reason))
        return result
