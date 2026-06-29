from datetime import UTC, datetime
from io import BytesIO

from pypdf import PdfReader

from aeroroute_api.application.dto.flight_plan import (
    FlightPlanRequest,
    FlightPlanResponse,
)
from aeroroute_api.application.dto.optimization import OptimizationResponse
from aeroroute_api.application.services.ofp_pdf import render_flight_plan_pdf
from aeroroute_api.infrastructure.db.flight_plans import DISCLAIMER


def test_pdf_contains_identity_route_and_non_operational_warning() -> None:
    plan = FlightPlanResponse(
        flight_plan_id="00000000-0000-0000-0000-000000000001",
        optimization_run_id="00000000-0000-0000-0000-000000000002",
        created_at=datetime(2026, 6, 29, 14, 0, tzinfo=UTC),
        coded_route="LEMD BARD3N DCT PAWLN1 KJFK",
        request=FlightPlanRequest(
            origin_icao="LEMD",
            destination_icao="KJFK",
            aircraft_type="B77W",
            callsign="ARX101",
            payload_mass_kg=42_000,
        ),
        optimization=OptimizationResponse(
            status="optimal",
            algorithm_version="0.3.0",
            winner=None,
            alternatives=[],
            solver_termination_reason="fixture",
        ),
        disclaimer=DISCLAIMER,
    )

    content = render_flight_plan_pdf(plan)
    reader = PdfReader(BytesIO(content))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert content.startswith(b"%PDF")
    assert len(reader.pages) == 1
    assert "NOT OPERATIONAL" in text
    assert "ARX101" in text
    assert "LEMD BARD3N DCT PAWLN1 KJFK" in text
