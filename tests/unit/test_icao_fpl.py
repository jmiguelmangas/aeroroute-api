from fastapi.testclient import TestClient

from aeroroute_api.application.dto.icao_fpl import IcaoFplValidationRequest
from aeroroute_api.application.services.icao_fpl import validate_icao_fpl
from aeroroute_api.main import app


def _request(**updates: object) -> dict[str, object]:
    values: dict[str, object] = {
        "aircraft_identification": "ARO123",
        "flight_rules": "I",
        "flight_type": "S",
        "aircraft_type": "A359",
        "equipment": "SDE2E3FGHIJ1J5M1RWXY/LB1",
        "departure_aerodrome": "LEMD",
        "departure_time_hhmm": "1200",
        "cruising_speed": "N0480",
        "cruising_level": "F350",
        "route": "LEMD BARDI DCT KJFK",
        "destination_aerodrome": "KJFK",
        "total_eet_hhmm": "0745",
        "alternate_aerodrome": "KBOS",
        "other_information": "DOF/260709 REG/ECAAA",
    }
    values.update(updates)
    return values


def test_icao_fpl_validation_blocks_filing_even_when_items_are_valid() -> None:
    result = validate_icao_fpl(
        IcaoFplValidationRequest.model_validate(_request())
    )

    assert result.status == "blocked"
    assert result.operational_use_enabled is False
    assert result.filing_enabled is False
    assert {item.item for item in result.items} == {
        "7",
        "8",
        "9",
        "10",
        "13",
        "15",
        "16",
        "18",
        "19",
    }
    assert all("Filing gateway" in item.blockers[0] for item in result.items)


def test_icao_fpl_validation_rejects_unapproved_equipment() -> None:
    result = validate_icao_fpl(
        IcaoFplValidationRequest.model_validate(
            _request(aircraft_type="A320", equipment="SDE2E3FGHIJ1J5M1RWXY")
        )
    )

    item10 = next(item for item in result.items if item.item == "10")
    assert result.status == "invalid"
    assert item10.valid is False
    assert "exceed" in item10.blockers[0]


def test_icao_fpl_validation_endpoint_is_non_operational() -> None:
    response = TestClient(app).post(
        "/api/v1/icao-fpl/validate", json=_request()
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["baseline"] == "icao-fpl-validation-2026-07-09"
    assert payload["filing_enabled"] is False
