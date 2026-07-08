"""Queries for the currently active immutable airport snapshot."""

from sqlalchemy import or_, select

from aeroroute_api.infrastructure.db.models import DatasetSnapshot


def active_airport_snapshot_id():
    return (
        select(DatasetSnapshot.id)
        .where(
            or_(
                DatasetSnapshot.source_name.startswith("airport-bundle:"),
                DatasetSnapshot.source_name == "ourairports-csv",
            )
        )
        .order_by(DatasetSnapshot.imported_at.desc(), DatasetSnapshot.id.desc())
        .limit(1)
        .scalar_subquery()
    )
