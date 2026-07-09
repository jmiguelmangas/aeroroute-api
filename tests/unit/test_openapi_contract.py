import json
from pathlib import Path

import pytest

from aeroroute_api.main import app
from scripts.validate_openapi_contract import (
    compare_openapi_contract,
    validate_openapi_contract,
)

# aeroroute-api/tests/unit/test_openapi_contract.py -> multi-repo root
_MULTI_REPO_ROOT = Path(__file__).resolve().parents[3]
_REAL_CONTRACT_PATH = (
    _MULTI_REPO_ROOT / "aeroroute-contracts" / "openapi" / "aeroroute-v1.json"
)


def test_real_contract_matches_live_schema() -> None:
    # This is the actual guardrail: it runs against the real, current
    # published contract and the real, current live FastAPI schema.
    validate_openapi_contract(_REAL_CONTRACT_PATH)


def test_live_schema_matches_itself() -> None:
    # Sanity check that the comparison is not vacuously true: a schema
    # compared against itself must never raise.
    live = app.openapi()
    compare_openapi_contract(live, live)


def test_endpoint_missing_from_contract_is_rejected() -> None:
    live = app.openapi()
    contract = json.loads(json.dumps(live))  # deep copy
    del contract["paths"]["/api/v1/flight-plans"]

    with pytest.raises(
        ValueError,
        match=(
            r"present in the live API but missing from the published "
            r"contract.*POST /api/v1/flight-plans"
        ),
    ):
        compare_openapi_contract(live, contract)


def test_endpoint_missing_from_live_api_is_rejected() -> None:
    live = app.openapi()
    contract = json.loads(json.dumps(live))  # deep copy
    contract["paths"]["/api/v1/legacy-optimizations"] = contract["paths"][
        "/api/v1/optimizations"
    ]

    with pytest.raises(
        ValueError,
        match=(
            r"present in the published contract but no longer present in "
            r"the live API.*GET /api/v1/legacy-optimizations"
        ),
    ):
        compare_openapi_contract(live, contract)


def test_request_body_field_removed_from_contract_is_rejected() -> None:
    # Reproduces the exact failure mode this guardrail exists for: a field
    # is added to the live OptimizationRequest model but the published
    # contract was never regenerated, so aeroroute-web's typed client would
    # silently be missing it.
    live = app.openapi()
    contract = json.loads(json.dumps(live))  # deep copy
    del contract["components"]["schemas"]["OptimizationRequest"]["properties"][
        "profile"
    ]

    with pytest.raises(
        ValueError,
        match=(
            r"POST /api/v1/optimizations request body: field\(s\) "
            r"\['profile'\] present in the live API but missing from the "
            r"published contract"
        ),
    ):
        compare_openapi_contract(live, contract)


def test_response_body_field_added_to_contract_is_rejected() -> None:
    # The opposite direction: the contract promises a field the live API
    # response no longer includes (e.g. removed from the live model but the
    # contract was never regenerated).
    live = app.openapi()
    contract = json.loads(json.dumps(live))  # deep copy
    contract["components"]["schemas"]["FlightPlanResponse"]["properties"][
        "legacy_field_no_longer_served"
    ] = {"type": "string"}

    with pytest.raises(
        ValueError,
        match=(
            r"POST /api/v1/flight-plans response body: field\(s\) "
            r"\['legacy_field_no_longer_served'\] present in the "
            r"published contract but missing from the live API"
        ),
    ):
        compare_openapi_contract(live, contract)


def test_drifted_contract_file_on_disk_is_rejected(tmp_path: Path) -> None:
    # End-to-end drift detection through validate_openapi_contract (the
    # entry point the Makefile target actually calls), using a mutated copy
    # of the real published contract file on disk -- not the live schema
    # copied onto itself -- to prove the file-reading path also works.
    real_contract = json.loads(_REAL_CONTRACT_PATH.read_text())
    del real_contract["components"]["schemas"]["FlightPlanRequest"][
        "properties"
    ]["origin_icao"]
    drifted_contract_path = tmp_path / "aeroroute-v1.json"
    drifted_contract_path.write_text(json.dumps(real_contract))

    with pytest.raises(
        ValueError,
        match=(
            r"POST /api/v1/flight-plans request body: field\(s\) "
            r"\['origin_icao'\] present in the live API but missing from "
            r"the published contract"
        ),
    ):
        validate_openapi_contract(drifted_contract_path)


def test_description_only_differences_are_ignored() -> None:
    # Byte-for-byte equality must NOT be required: descriptions, examples,
    # and schema ordering differences should not fail the check.
    live = app.openapi()
    contract = json.loads(json.dumps(live))  # deep copy
    contract["info"]["description"] = "A totally different description"
    contract["paths"]["/api/v1/optimizations"]["post"]["summary"] = (
        "A different summary"
    )
    contract["components"]["schemas"]["OptimizationRequest"]["description"] = (
        "Something else entirely"
    )

    compare_openapi_contract(live, contract)
