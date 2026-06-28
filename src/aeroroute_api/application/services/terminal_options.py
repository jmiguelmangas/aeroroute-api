import math
from typing import Literal

from aeroroute_api.application.dto.navigation import (
    ProcedureOption,
    ProcedureOptionsResponse,
    RunwayOption,
    RunwayOptionsResponse,
)
from aeroroute_api.infrastructure.navigation.airac import (
    AiracNavigationClient,
    AiracProcedure,
)
from aeroroute_api.infrastructure.weather.open_meteo import SurfaceWind


class IncompatibleRunwayError(ValueError):
    pass


def runway_matches_family(runway: str, family: str) -> bool:
    normalized_runway = runway.upper().removeprefix("RW")
    normalized_family = family.upper().removeprefix("RW").removesuffix("B")
    if normalized_family == "ALL":
        return True
    return normalized_runway.startswith(normalized_family)


def procedures_for_runway(
    procedures: tuple[AiracProcedure, ...], runway: str | None
) -> tuple[AiracProcedure, ...]:
    if runway is None:
        return procedures
    return tuple(
        procedure
        for procedure in procedures
        if runway_matches_family(runway, procedure.runway)
    )


async def runway_options(
    client: AiracNavigationClient,
    airport: str,
    procedure_type: Literal["SID", "STAR"],
    surface_wind: SurfaceWind | None = None,
) -> RunwayOptionsResponse:
    runways = await client.runways(airport)
    procedures = await client.procedures(airport, procedure_type)
    counts = {
        runway.identifier: sum(
            runway_matches_family(runway.identifier, procedure.runway)
            for procedure in procedures
        )
        for runway in runways
    }
    eligible = [runway for runway in runways if counts[runway.identifier]]
    components = {
        runway.identifier: _wind_components(runway.bearing_deg, surface_wind)
        for runway in runways
    }
    suggested = (
        min(
            eligible,
            key=lambda item: (
                -components[item.identifier][0],
                components[item.identifier][1],
                -item.length_ft,
                item.identifier,
            ),
        )
        if eligible and surface_wind
        else min(eligible, key=lambda item: (-item.length_ft, item.identifier))
        if eligible
        else None
    )
    cycles = {
        value
        for value in (
            *(runway.cycle for runway in runways),
            *(procedure.cycle for procedure in procedures),
        )
        if value
    }
    return RunwayOptionsResponse(
        airport_icao=airport.upper(),
        procedure_type=procedure_type,
        suggested_runway=suggested.identifier if suggested else None,
        airac_cycle=", ".join(sorted(cycles)) if cycles else None,
        recommendation_basis=[
            (
                "Best headwind component among published runways with compatible AIRAC procedures."
                if surface_wind
                else "Longest published runway with compatible AIRAC procedures."
            ),
            (
                "Open-Meteo 10 m wind is advisory; NOTAM, runway condition, and ATC assignment are not applied."
                if surface_wind
                else "Surface wind unavailable; NOTAM, runway condition, and ATC assignment are not applied."
            ),
        ],
        surface_wind_speed_kt=surface_wind.speed_kt if surface_wind else None,
        surface_wind_direction_deg=(
            surface_wind.direction_from_deg if surface_wind else None
        ),
        surface_wind_source=surface_wind.source if surface_wind else None,
        items=[
            RunwayOption(
                identifier=runway.identifier,
                bearing_deg=runway.bearing_deg,
                length_ft=runway.length_ft,
                width_ft=runway.width_ft,
                surface=runway.surface,
                compatible_procedures=counts[runway.identifier],
                suggested=bool(
                    suggested and runway.identifier == suggested.identifier
                ),
                headwind_component_kt=(
                    round(components[runway.identifier][0], 1)
                    if surface_wind
                    else None
                ),
                crosswind_component_kt=(
                    round(components[runway.identifier][1], 1)
                    if surface_wind
                    else None
                ),
            )
            for runway in runways
        ],
    )


def _wind_components(
    runway_bearing_deg: float, surface_wind: SurfaceWind | None
) -> tuple[float, float]:
    if surface_wind is None:
        return 0.0, 0.0
    angle = math.radians(surface_wind.direction_from_deg - runway_bearing_deg)
    return (
        surface_wind.speed_kt * math.cos(angle),
        abs(surface_wind.speed_kt * math.sin(angle)),
    )


async def procedure_options(
    client: AiracNavigationClient,
    airport: str,
    procedure_type: Literal["SID", "STAR"],
    runway: str | None,
) -> ProcedureOptionsResponse:
    procedures = procedures_for_runway(
        await client.procedures(airport, procedure_type), runway
    )
    return ProcedureOptionsResponse(
        airport_icao=airport.upper(),
        procedure_type=procedure_type,
        runway=runway,
        items=[
            ProcedureOption(
                identifier=procedure.identifier,
                procedure_type=procedure_type,
                runway_family=procedure.runway,
                entry_fix=procedure.points[0].identifier,
                exit_fix=procedure.points[-1].identifier,
                point_count=len(procedure.points),
                airac_cycle=procedure.cycle,
            )
            for procedure in procedures
        ],
    )


async def validate_runway_selection(
    client: AiracNavigationClient,
    airport: str,
    procedure_type: Literal["SID", "STAR"],
    runway: str,
) -> None:
    available_runways = await client.runways(airport)
    if not any(
        item.identifier.upper() == runway.upper() for item in available_runways
    ):
        raise IncompatibleRunwayError(
            f"Runway {runway} is not published for {airport.upper()}."
        )
    procedures = procedures_for_runway(
        await client.procedures(airport, procedure_type), runway
    )
    if not procedures:
        raise IncompatibleRunwayError(
            f"Runway {runway} has no compatible {procedure_type}."
        )
