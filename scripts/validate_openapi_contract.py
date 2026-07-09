"""Guardrail: verify the live FastAPI OpenAPI schema matches the published
contract in ``aeroroute-contracts/openapi/aeroroute-v1.json``.

The typed web client is generated from that contract file, but nothing
previously verified the contract actually reflects what the running FastAPI
application serves. This script closes that gap by importing the FastAPI
``app`` object directly (no server process needed) and diffing
``app.openapi()`` against the published contract:

1. Every path+method that exists on one side must exist on the other.
2. For the highest-drift-risk endpoints (``/api/v1/optimizations`` and
   ``/api/v1/flight-plans``), the top-level field set of each request body
   and success response body must match between live and contract.

This is a pragmatic, not byte-for-byte, comparison: descriptions, examples,
field ordering, and nested-schema details are intentionally ignored. Only
added/removed/renamed top-level fields and added/removed endpoints are
treated as drift.
"""

import json
import sys
from pathlib import Path

# Endpoints most likely to drift (richest request/response shapes) get a
# top-level field-set comparison in addition to the path+method check that
# applies to every endpoint.
FIELD_CHECK_PATHS = ("/api/v1/optimizations", "/api/v1/flight-plans")

_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def _load_live_schema() -> dict:
    # Imported lazily so importing this module (e.g. from a test) doesn't
    # require the FastAPI app's dependencies to be importable unless the
    # live schema is actually needed.
    from aeroroute_api.main import app

    return app.openapi()


def _load_contract_schema(path: Path) -> dict:
    return json.loads(path.read_text())


def _operation_set(schema: dict) -> set[tuple[str, str]]:
    operations = set()
    for path, methods in schema.get("paths", {}).items():
        if not isinstance(methods, dict):
            continue
        for method in methods:
            if method.lower() in _HTTP_METHODS:
                operations.add((method.upper(), path))
    return operations


def _deref(root: dict, node: dict | None) -> dict | None:
    if node is None:
        return None
    ref = node.get("$ref")
    if ref is None:
        return node
    prefix = "#/components/schemas/"
    if not ref.startswith(prefix):
        raise ValueError(f"Unsupported schema reference: {ref!r}")
    name = ref[len(prefix) :]
    schemas = root.get("components", {}).get("schemas", {})
    if name not in schemas:
        raise ValueError(
            f"Schema component {name!r} is referenced but not defined"
        )
    return schemas[name]


def _field_set(root: dict, node: dict | None) -> set[str] | None:
    """Return the top-level field names for a (possibly $ref'd, possibly
    array-wrapped, possibly allOf-composed) schema node."""
    resolved = _deref(root, node)
    if resolved is None:
        return None
    if resolved.get("type") == "array" and "items" in resolved:
        return _field_set(root, resolved["items"])
    fields = set(resolved.get("properties", {}).keys())
    for member in resolved.get("allOf", []):
        member_resolved = _deref(root, member)
        if member_resolved:
            fields |= set(member_resolved.get("properties", {}).keys())
    return fields


def _body_schema(operation: dict, *, request: bool) -> dict | None:
    if request:
        body = operation.get("requestBody")
        if not body:
            return None
        content = body.get("content", {})
    else:
        responses = operation.get("responses", {})
        content = {}
        for status in sorted(responses):
            if status.startswith("2"):
                content = responses[status].get("content", {})
                if content:
                    break
    media = content.get("application/json")
    return media.get("schema") if media else None


def _check_field_sets(live: dict, contract: dict, errors: list[str]) -> None:
    for path in FIELD_CHECK_PATHS:
        live_methods = live.get("paths", {}).get(path, {})
        contract_methods = contract.get("paths", {}).get(path, {})
        shared_methods = sorted(
            (set(live_methods) & set(contract_methods)) & _HTTP_METHODS
        )
        for method in shared_methods:
            live_op = live_methods[method]
            contract_op = contract_methods[method]
            for label, is_request in (
                ("request", True),
                ("response", False),
            ):
                live_schema = _body_schema(live_op, request=is_request)
                contract_schema = _body_schema(contract_op, request=is_request)
                if live_schema is None and contract_schema is None:
                    continue
                if (live_schema is None) != (contract_schema is None):
                    where = (
                        "live API"
                        if contract_schema is None
                        else ("published contract")
                    )
                    errors.append(
                        f"{method.upper()} {path} {label} body is only "
                        f"present in the {where}"
                    )
                    continue
                live_fields = _field_set(live, live_schema) or set()
                contract_fields = _field_set(contract, contract_schema) or set()
                added = live_fields - contract_fields
                removed = contract_fields - live_fields
                if added:
                    errors.append(
                        f"{method.upper()} {path} {label} body: field(s) "
                        f"{sorted(added)} present in the live API but "
                        "missing from the published contract"
                    )
                if removed:
                    errors.append(
                        f"{method.upper()} {path} {label} body: field(s) "
                        f"{sorted(removed)} present in the published "
                        "contract but missing from the live API"
                    )


def compare_openapi_contract(live: dict, contract: dict) -> None:
    """Compare a live ``app.openapi()`` schema dict against a published
    contract schema dict. Raises ``ValueError`` naming exactly what
    disagrees; does nothing on success."""
    errors: list[str] = []

    live_ops = _operation_set(live)
    contract_ops = _operation_set(contract)
    added = sorted(live_ops - contract_ops)
    removed = sorted(contract_ops - live_ops)
    if added:
        errors.append(
            "Endpoint(s) present in the live API but missing from the "
            "published contract: " + ", ".join(f"{m} {p}" for m, p in added)
        )
    if removed:
        errors.append(
            "Endpoint(s) present in the published contract but no longer "
            "present in the live API: "
            + ", ".join(f"{m} {p}" for m, p in removed)
        )

    _check_field_sets(live, contract, errors)

    if errors:
        raise ValueError(
            "OpenAPI contract drift detected between the live FastAPI "
            "schema and aeroroute-contracts/openapi/aeroroute-v1.json:\n- "
            + "\n- ".join(errors)
        )


def validate_openapi_contract(contract_path: Path) -> None:
    live = _load_live_schema()
    contract = _load_contract_schema(contract_path)
    compare_openapi_contract(live, contract)


def _default_contract_path() -> Path:
    # aeroroute-api/scripts/validate_openapi_contract.py -> multi-repo root
    multi_repo_root = Path(__file__).resolve().parents[2]
    return (
        multi_repo_root
        / "aeroroute-contracts"
        / "openapi"
        / "aeroroute-v1.json"
    )


def main(contract_path: str | None = None) -> None:
    path = Path(contract_path) if contract_path else _default_contract_path()
    if not path.is_file():
        raise SystemExit(f"Contract file not found: {path}")
    try:
        validate_openapi_contract(path)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print("Live OpenAPI schema matches the published contract.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
