from __future__ import annotations

from aeroroute_api.application.dto.data_sources import (
    OperationalDataSource,
    OperationalDataSourceLicense,
    OperationalDataSourceQuality,
)


def simulator_data_sources() -> list[OperationalDataSource]:
    return [
        OperationalDataSource(
            domain="navdata",
            source="airac.net",
            status="demo_only",
            version_or_cycle=None,
            timestamp=None,
            expires_at=None,
            license=OperationalDataSourceLicense(
                terms="Public/demo access; operational-use rights not established.",
                approved_for_operational_use=False,
                redistribution_allowed=False,
            ),
            quality=OperationalDataSourceQuality(
                grade="public_reference",
                validation_status="partial",
                validated_at=None,
            ),
            fallback_behavior="degrade_simulator_only",
            operational_ready=False,
            blockers=[
                "Operational AIRAC license and redistribution terms are missing.",
                "Cycle expiry and supplier validation are not gated.",
            ],
        ),
        OperationalDataSource(
            domain="weather",
            source="open-meteo or still-air simulator fallback",
            status="demo_only",
            version_or_cycle=None,
            timestamp=None,
            expires_at=None,
            license=OperationalDataSourceLicense(
                terms="Public/demo weather; not accepted for dispatch release.",
                approved_for_operational_use=False,
                redistribution_allowed=True,
            ),
            quality=OperationalDataSourceQuality(
                grade="public_reference",
                validation_status="partial",
                validated_at=None,
            ),
            fallback_behavior="degrade_simulator_only",
            operational_ready=False,
            blockers=[
                "Operational weather provider, latency and expiry gates are missing.",
                "Still-air fallback is simulator-only and must block operations.",
            ],
        ),
        OperationalDataSource(
            domain="notam",
            source="not configured",
            status="missing",
            version_or_cycle=None,
            timestamp=None,
            expires_at=None,
            license=OperationalDataSourceLicense(
                terms="No NOTAM provider configured.",
                approved_for_operational_use=False,
                redistribution_allowed=False,
            ),
            quality=OperationalDataSourceQuality(
                grade="unknown",
                validation_status="not_validated",
                validated_at=None,
            ),
            fallback_behavior="block_operational_use",
            operational_ready=False,
            blockers=["Operational NOTAM data is required and unavailable."],
        ),
        OperationalDataSource(
            domain="airspace_restrictions",
            source="not configured",
            status="missing",
            version_or_cycle=None,
            timestamp=None,
            expires_at=None,
            license=OperationalDataSourceLicense(
                terms="No RAD/ATC/airspace restriction provider configured.",
                approved_for_operational_use=False,
                redistribution_allowed=False,
            ),
            quality=OperationalDataSourceQuality(
                grade="unknown",
                validation_status="not_validated",
                validated_at=None,
            ),
            fallback_behavior="block_operational_use",
            operational_ready=False,
            blockers=[
                "RAD, ATC, flow and airspace restriction data is unavailable."
            ],
        ),
        OperationalDataSource(
            domain="airport_status",
            source="airport bundle plus procedure availability",
            status="demo_only",
            version_or_cycle=None,
            timestamp=None,
            expires_at=None,
            license=OperationalDataSourceLicense(
                terms="Public/demo airport data; live operational status absent.",
                approved_for_operational_use=False,
                redistribution_allowed=True,
            ),
            quality=OperationalDataSourceQuality(
                grade="public_reference",
                validation_status="partial",
                validated_at=None,
            ),
            fallback_behavior="degrade_simulator_only",
            operational_ready=False,
            blockers=[
                "Runway, airport-status and suitability data are not operationally current."
            ],
        ),
        OperationalDataSource(
            domain="terrain_obstacle",
            source="not configured",
            status="missing",
            version_or_cycle=None,
            timestamp=None,
            expires_at=None,
            license=OperationalDataSourceLicense(
                terms="No terrain/obstacle provider configured.",
                approved_for_operational_use=False,
                redistribution_allowed=False,
            ),
            quality=OperationalDataSourceQuality(
                grade="unknown",
                validation_status="not_validated",
                validated_at=None,
            ),
            fallback_behavior="block_operational_use",
            operational_ready=False,
            blockers=[
                "Terrain and obstacle data is unavailable for operational validation."
            ],
        ),
        OperationalDataSource(
            domain="aircraft_performance",
            source="curated educational performance model",
            status="demo_only",
            version_or_cycle="simulator-v1",
            timestamp=None,
            expires_at=None,
            license=OperationalDataSourceLicense(
                terms="Educational approximation; not an approved aircraft performance source.",
                approved_for_operational_use=False,
                redistribution_allowed=False,
            ),
            quality=OperationalDataSourceQuality(
                grade="demo",
                validation_status="partial",
                validated_at=None,
            ),
            fallback_behavior="degrade_simulator_only",
            operational_ready=False,
            blockers=[
                "Approved tail/fleet performance data and benchmark reconciliation are missing."
            ],
        ),
        OperationalDataSource(
            domain="filing",
            source="not configured",
            status="missing",
            version_or_cycle=None,
            timestamp=None,
            expires_at=None,
            license=OperationalDataSourceLicense(
                terms="No filing gateway configured.",
                approved_for_operational_use=False,
                redistribution_allowed=False,
            ),
            quality=OperationalDataSourceQuality(
                grade="unknown",
                validation_status="not_validated",
                validated_at=None,
            ),
            fallback_behavior="block_operational_use",
            operational_ready=False,
            blockers=[
                "ICAO filing gateway and acceptance validation are missing."
            ],
        ),
    ]
