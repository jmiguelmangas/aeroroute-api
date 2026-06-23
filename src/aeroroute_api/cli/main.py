"""Administrative commands; never called by the public HTTP path."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from aeroroute_api.infrastructure.datasets.airport_importer import (
    import_airports_csv,
)
from aeroroute_api.infrastructure.db.session import session_factory


def main() -> None:
    parser = argparse.ArgumentParser(prog="aeroroute")
    subcommands = parser.add_subparsers(dest="command", required=True)
    import_parser = subcommands.add_parser("import-airports")
    import_parser.add_argument("--file", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.command == "import-airports":
        asyncio.run(_import_airports(arguments.file))


async def _import_airports(path: Path) -> None:
    async with session_factory()() as session:
        summary = await import_airports_csv(session, path)
    print(
        f"snapshot={summary.snapshot_id} accepted={summary.accepted_rows} "
        f"rejected={summary.rejected_rows} existing={summary.already_imported}"
    )
