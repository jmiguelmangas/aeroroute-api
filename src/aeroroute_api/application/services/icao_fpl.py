from __future__ import annotations

import re

from aeroroute_api.application.dto.icao_fpl import (
    AircraftCapabilityProfile,
    IcaoFplItemValidation,
    IcaoFplValidationRequest,
    IcaoFplValidationResponse,
)


AIRCRAFT_CAPABILITIES: dict[str, set[str]] = {
    "A320": {
        "S",
        "D",
        "E2",
        "E3",
        "F",
        "G",
        "I",
        "J1",
        "M1",
        "R",
        "W",
        "X",
        "Y",
    },
    "B738": {
        "S",
        "D",
        "E2",
        "E3",
        "F",
        "G",
        "I",
        "J1",
        "M1",
        "R",
        "W",
        "X",
        "Y",
    },
    "B77W": {
        "S",
        "D",
        "E2",
        "E3",
        "F",
        "G",
        "H",
        "I",
        "J1",
        "J5",
        "M1",
        "R",
        "W",
        "X",
        "Y",
    },
    "B788": {
        "S",
        "D",
        "E2",
        "E3",
        "F",
        "G",
        "H",
        "I",
        "J1",
        "J5",
        "M1",
        "R",
        "W",
        "X",
        "Y",
    },
    "A359": {
        "S",
        "D",
        "E2",
        "E3",
        "F",
        "G",
        "H",
        "I",
        "J1",
        "J5",
        "M1",
        "R",
        "W",
        "X",
        "Y",
    },
    "A388": {
        "S",
        "D",
        "E2",
        "E3",
        "F",
        "G",
        "H",
        "I",
        "J1",
        "J5",
        "M1",
        "R",
        "W",
        "X",
        "Y",
    },
}
MANDATORY_OPERATIONAL_BLOCKERS = [
    "Filing gateway is not configured or operator-approved.",
    "NOTAM, RAD/ATC and airspace restriction data are not operationally available.",
    "Aircraft capability and operator approval records are not accepted.",
]
CAPABILITY_BASELINE = "aircraft-capability-simulator-2026-07-09"


def validate_icao_fpl(
    request: IcaoFplValidationRequest,
) -> IcaoFplValidationResponse:
    capability = aircraft_capability_profile(
        request.aircraft_type, request.equipment
    )
    items = [
        _item(
            "7",
            bool(
                re.fullmatch(
                    r"[A-Z0-9]{2,7}", request.aircraft_identification.upper()
                )
            ),
            "Aircraft identification must be 2-7 alphanumeric characters.",
        ),
        _item("8", True, ""),
        _item(
            "9",
            request.aircraft_type.upper() in AIRCRAFT_CAPABILITIES,
            "Aircraft type is not in the supported simulator fleet.",
        ),
        _item(
            "10",
            not capability.unsupported_equipment
            and bool(capability.requested_equipment),
            "Equipment codes exceed the simulator aircraft capability baseline.",
        ),
        _item(
            "13",
            _aerodrome(request.departure_aerodrome)
            and _hhmm(request.departure_time_hhmm),
            "Departure aerodrome or time is invalid.",
        ),
        _item(
            "15",
            _route(request.route),
            "Route contains unsupported characters or is empty.",
        ),
        _item(
            "16",
            _aerodrome(request.destination_aerodrome)
            and _eet(request.total_eet_hhmm),
            "Destination or total EET is invalid.",
        ),
        _item(
            "18",
            _other_information(request.other_information),
            "Other information must use compact ICAO-style tokens.",
        ),
        _item("19", True, ""),
    ]
    for item in items:
        item.blockers.extend(MANDATORY_OPERATIONAL_BLOCKERS)
    return IcaoFplValidationResponse(
        status="invalid"
        if any(not item.valid for item in items)
        else "blocked",
        items=items,
        aircraft_capability=capability,
    )


def _item(item: str, valid: bool, blocker: str) -> IcaoFplItemValidation:
    blockers = [] if valid or not blocker else [blocker]
    return IcaoFplItemValidation(item=item, valid=valid, blockers=blockers)  # type: ignore[arg-type]


def _aerodrome(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{4}", value.upper()))


def _hhmm(value: str) -> bool:
    return (
        bool(re.fullmatch(r"[0-2][0-9][0-5][0-9]", value))
        and int(value[:2]) < 24
    )


def _eet(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9]{4}", value)) and int(value[2:]) < 60


def _route(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z0-9/ .-]+", value.upper()))


def _other_information(value: str) -> bool:
    return not value or bool(re.fullmatch(r"[A-Z0-9/ .-]+", value.upper()))


def aircraft_capability_profile(
    aircraft_type: str, equipment: str
) -> AircraftCapabilityProfile:
    allowed = AIRCRAFT_CAPABILITIES.get(aircraft_type.upper())
    if not allowed:
        return AircraftCapabilityProfile(
            aircraft_type=aircraft_type.upper(),
            capability_baseline=CAPABILITY_BASELINE,
            allowed_equipment=[],
            requested_equipment=_equipment_tokens(equipment),
            unsupported_equipment=_equipment_tokens(equipment),
            blockers=[
                "Aircraft type is not in the simulator capability baseline.",
                "Operator aircraft capability approval is not accepted.",
            ],
        )
    requested = _equipment_tokens(equipment)
    unsupported = sorted(set(requested) - allowed)
    return AircraftCapabilityProfile(
        aircraft_type=aircraft_type.upper(),
        capability_baseline=CAPABILITY_BASELINE,
        allowed_equipment=sorted(allowed),
        requested_equipment=requested,
        unsupported_equipment=unsupported,
        blockers=[
            "Operator aircraft capability approval is not accepted.",
        ],
    )


def _equipment_tokens(equipment: str) -> list[str]:
    raw = equipment.split("/")[0]
    return re.findall(r"[A-Z][0-9]?", raw.upper())
