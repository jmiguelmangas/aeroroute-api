"""Render an immutable flight-plan snapshot as a non-operational PDF."""

from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from aeroroute_api.application.dto.flight_plan import FlightPlanResponse


def render_flight_plan_pdf(plan: FlightPlanResponse) -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=17 * mm,
        bottomMargin=20 * mm,
        title=f"AeroRoute OFP {plan.flight_plan_id}",
        author="AeroRoute MLX",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "OFPTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=21,
        textColor=colors.HexColor("#0b3155"),
        spaceAfter=5 * mm,
    )
    section = ParagraphStyle(
        "OFPSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=12,
        textColor=colors.HexColor("#175f9c"),
        spaceBefore=4 * mm,
        spaceAfter=2 * mm,
    )
    body = ParagraphStyle(
        "OFPBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor("#172536"),
    )
    warning = ParagraphStyle(
        "OFPWarning",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#8b1e1e"),
        borderColor=colors.HexColor("#c74a4a"),
        borderWidth=0.8,
        borderPadding=7,
        backColor=colors.HexColor("#fff3f3"),
        spaceAfter=5 * mm,
    )
    story = [
        Paragraph("AeroRoute MLX - PRE-OPERATIONAL OFP", title),
        Paragraph("NOT OPERATIONAL - NOT ICAO FILEABLE", warning),
        _summary_table(plan, body),
        Paragraph("Coded route", section),
        Paragraph(_safe(plan.coded_route), body),
    ]
    result = plan.optimization
    if result.fuel_plan is not None:
        story.extend(
            [
                Paragraph("Fuel and mass", section),
                _fuel_table(result.fuel_plan, body),
            ]
        )
    story.extend(
        [
            Paragraph("Alternates and diversions", section),
            _alternate_table(plan, body),
        ]
    )
    winner = result.winner
    if winner is not None:
        story.extend(
            [
                Paragraph("Navigation log", section),
                _navlog_table(winner.waypoints, body),
            ]
        )
    story.extend(
        [
            Spacer(1, 4 * mm),
            KeepTogether(
                [
                    Paragraph("Sources and limitations", section),
                    Paragraph(
                        _safe("; ".join(result.assumptions or [])), body
                    ),
                    Spacer(1, 2 * mm),
                    Paragraph(_safe(plan.disclaimer), warning),
                ]
            ),
        ]
    )
    document.build(
        story,
        onFirstPage=lambda canvas, doc: _footer(canvas, doc, plan),
        onLaterPages=lambda canvas, doc: _footer(canvas, doc, plan),
    )
    return buffer.getvalue()


def _summary_table(plan: FlightPlanResponse, body: ParagraphStyle) -> Table:
    request = plan.request
    result = plan.optimization
    terminal = result.terminal_selection
    winner = result.winner
    rows = [
        ["Plan ID", plan.flight_plan_id, "Created", plan.created_at.isoformat()],
        ["Callsign", request.callsign or "-", "Aircraft", request.aircraft_type],
        ["Route", f"{request.origin_icao} - {request.destination_icao}", "Payload", _kg(request.payload_mass_kg)],
        ["Departure", _terminal(terminal.departure_runway if terminal else None, terminal.sid_identifier if terminal else None), "Arrival", _terminal(terminal.arrival_runway if terminal else None, terminal.star_identifier if terminal else None)],
        ["Distance", f"{winner.distance_m / 1852:,.0f} NM" if winner else "-", "Time", f"{winner.time_s / 60:,.0f} min" if winner else "-"],
        ["AIRAC", terminal.airac_cycle if terminal else "-", "Algorithm", result.algorithm_version],
    ]
    return _key_value_table(rows, body)


def _fuel_table(fuel: object, body: ParagraphStyle) -> Table:
    rows = [
        ["Taxi", _kg(fuel.taxi_fuel_kg), "Trip", _kg(fuel.trip_fuel_kg)],
        ["Contingency", _kg(fuel.contingency_fuel_kg), "Alternate", _kg(fuel.alternate_fuel_kg)],
        ["Final reserve", _kg(fuel.final_reserve_fuel_kg), "Extra", _kg(fuel.extra_fuel_kg)],
        ["Block fuel", _kg(fuel.block_fuel_kg), "Takeoff fuel", _kg(fuel.takeoff_fuel_kg)],
        ["Ramp mass", _kg(fuel.ramp_mass_kg), "Takeoff mass", _kg(fuel.takeoff_mass_kg)],
        ["Landing mass", _kg(fuel.estimated_landing_mass_kg), "Mass iteration", f"{fuel.mass_iterations} ({'converged' if fuel.mass_converged else 'not converged'})"],
    ]
    return _key_value_table(rows, body)


def _alternate_table(plan: FlightPlanResponse, body: ParagraphStyle) -> Table:
    result = plan.optimization
    rows = [["Role", "Airport", "Distance", "Runway", "Source"]]
    alternate = result.destination_alternate
    if alternate is not None:
        rows.append(["Destination", alternate.icao_code, f"{alternate.distance_from_destination_nm:.1f} NM", _ft(alternate.longest_published_runway_ft), _source(alternate.navigation_source, alternate.airac_cycle)])
    for diversion in result.enroute_diversions:
        rows.append(["En-route", diversion.icao_code, f"{diversion.distance_to_route_nm:.1f} NM", _ft(diversion.longest_published_runway_ft), _source(diversion.navigation_source, diversion.airac_cycle)])
    if len(rows) == 1:
        rows.append(["-", "No compatible candidate", "-", "-", "-"])
    return _table(rows, body, repeat_rows=1)


def _navlog_table(waypoints: list[object], body: ParagraphStyle) -> Table:
    rows = [["Fix", "Via", "FL", "Elapsed", "Dist", "Fuel", "Source"]]
    for point in waypoints:
        rows.append(
            [
                point.display_name,
                point.inbound_via or "-",
                str(point.flight_level) if point.flight_level > 0 else "-",
                f"{point.elapsed_time_s / 60:.0f}m",
                f"{point.cumulative_distance_m / 1852:.0f}",
                f"{point.cumulative_fuel_kg:.0f}",
                _source(point.navigation_source, point.airac_cycle),
            ]
        )
    return _table(rows, body, repeat_rows=1, font_size=6.5)


def _key_value_table(rows: list[list[str]], body: ParagraphStyle) -> Table:
    table = _table(rows, body)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8f1f8")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#e8f1f8")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
            ]
        )
    )
    return table


def _table(
    rows: list[list[str]],
    body: ParagraphStyle,
    *,
    repeat_rows: int = 0,
    font_size: float = 7.5,
) -> Table:
    header = ParagraphStyle(
        "TableHeader",
        parent=body,
        fontName="Helvetica-Bold",
        textColor=colors.white,
    )
    wrapped = [
        [
            Paragraph(
                _safe(str(cell)),
                header if repeat_rows and row_index == 0 else body,
            )
            for cell in row
        ]
        for row_index, row in enumerate(rows)
    ]
    table = Table(wrapped, repeatRows=repeat_rows, hAlign="LEFT")
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#b6c8d8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
    ]
    if repeat_rows:
        commands.extend(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b3155")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]
        )
    table.setStyle(TableStyle(commands))
    return table


def _footer(canvas: object, doc: object, plan: FlightPlanResponse) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#b6c8d8"))
    canvas.line(14 * mm, 14 * mm, A4[0] - 14 * mm, 14 * mm)
    canvas.setFont("Helvetica", 6.5)
    canvas.setFillColor(colors.HexColor("#5b6b7b"))
    canvas.drawString(14 * mm, 9.5 * mm, "NOT OPERATIONAL - AeroRoute MLX educational simulation")
    canvas.drawRightString(A4[0] - 14 * mm, 9.5 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _safe(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _kg(value: float | None) -> str:
    return f"{value:,.0f} kg" if value is not None else "-"


def _ft(value: float | None) -> str:
    return f"{value:,.0f} ft" if value is not None else "-"


def _source(source: str | None, cycle: str | None) -> str:
    return f"{source or '-'} {cycle or ''}".strip()


def _terminal(runway: str | None, procedure: str | None) -> str:
    return f"RWY {runway or '-'} / {procedure or '-'}"
