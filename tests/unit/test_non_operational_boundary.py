"""Systemic regression guard for the non-operational boundary (Phase 3).

AeroRoute MLX is an educational, non-operational flight-plan simulator
(HLD Section 2.2/2.3). It must never claim it can actually file an ICAO
flight plan. Today that guarantee is enforced endpoint-by-endpoint (see
``test_icao_fpl.py`` and ``test_operational_readiness.py``). This test
instead walks the *entire* generated OpenAPI schema so that a brand-new,
not-yet-imagined endpoint that reintroduces a ``filing_enabled`` or
``operational_use_enabled`` field gets caught automatically, without
anyone having to remember to add a bespoke test for it.
"""

from typing import Any

from aeroroute_api.main import app

GUARDED_FIELD_NAMES = {"filing_enabled", "operational_use_enabled"}

# Fields that are required (no static Pydantic default) rather than
# hard-pinned via `= False`, because the router/service always computes and
# passes `False` explicitly. Each entry here MUST be justified by a
# dedicated test elsewhere that proves the value can never be True.
KNOWN_REQUIRED_NO_DEFAULT_EXCEPTIONS = {
    # Proven always False, even when OPS_MODE requests an operational
    # mode, by test_operational_readiness.py::
    #   test_operational_readiness_blocks_requested_operational_mode
    ("OperationalReadinessResponse", "operational_use_enabled"),
    # Proven always False, even when OPS_MODE requests an operational
    # mode, by test_operational_readiness.py::
    #   test_operational_data_sources_fail_closed_for_ops_candidate
    ("OperationalDataSourcesResponse", "operational_use_enabled"),
}


def _find_guarded_properties() -> list[tuple[str, str, dict[str, Any], bool]]:
    """Return (schema_name, field_name, field_schema, is_required) tuples
    for every property named filing_enabled/operational_use_enabled found
    anywhere under components.schemas in the app's OpenAPI document."""

    schema = app.openapi()
    schemas = schema.get("components", {}).get("schemas", {})

    found: list[tuple[str, str, dict[str, Any], bool]] = []
    for schema_name, schema_def in schemas.items():
        properties = schema_def.get("properties", {})
        required = set(schema_def.get("required", []))
        for field_name, field_schema in properties.items():
            if field_name in GUARDED_FIELD_NAMES:
                found.append(
                    (schema_name, field_name, field_schema, field_name in required)
                )
    return found


def test_non_operational_boundary_fields_are_hard_pinned_to_false() -> None:
    found = _find_guarded_properties()

    # If the introspection logic itself regresses (e.g. FastAPI changes
    # where it puts schemas, or both guarded fields are removed from the
    # codebase entirely) we must fail loudly rather than pass vacuously.
    assert len(found) >= 2, (
        "Expected to find at least 2 filing_enabled/operational_use_enabled "
        f"properties across the OpenAPI schema, found {len(found)}: {found}"
    )

    failures: list[str] = []
    for schema_name, field_name, field_schema, is_required in found:
        location = f"{schema_name}.{field_name}"

        if "default" in field_schema:
            if field_schema["default"] is not False:
                failures.append(
                    f"{location} has default={field_schema['default']!r}, "
                    "expected default=False"
                )
            continue

        if "const" in field_schema:
            if field_schema["const"] is not False:
                failures.append(
                    f"{location} has const={field_schema['const']!r}, "
                    "expected const=False"
                )
            continue

        # No default and no const: the value must be supplied explicitly
        # by every caller of this schema. That is only acceptable for the
        # small, explicitly-justified allowlist above; anything else is
        # exactly the pattern where a future route handler could pass
        # True and defeat the non-operational guarantee.
        if (schema_name, field_name) not in KNOWN_REQUIRED_NO_DEFAULT_EXCEPTIONS:
            failures.append(
                f"{location} is required with no default and no const, and "
                "is not in KNOWN_REQUIRED_NO_DEFAULT_EXCEPTIONS. Either pin "
                "it with `= False` in the DTO, or add it to the exceptions "
                "list here with a comment pointing at the test that proves "
                "it can never be True."
            )

    assert not failures, "Non-operational boundary regression detected:\n" + "\n".join(
        failures
    )
