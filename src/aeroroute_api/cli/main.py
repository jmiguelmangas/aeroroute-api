"""Administrative commands; never called by the public HTTP path."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from aeroroute_api.infrastructure.datasets.airport_importer import (
    import_airport_bundle,
    import_airports_csv,
)
from aeroroute_api.infrastructure.db.session import session_factory


def main() -> None:
    parser = argparse.ArgumentParser(prog="aeroroute")
    subcommands = parser.add_subparsers(dest="command", required=True)
    import_parser = subcommands.add_parser("import-airports")
    source = import_parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path)
    source.add_argument("--bundle", type=Path)
    arguments = parser.parse_args()
    if arguments.command == "import-airports":
        asyncio.run(_import_airports(arguments.file, arguments.bundle))


async def _import_airports(
    file_path: Path | None, bundle_path: Path | None
) -> None:
    async with session_factory()() as session:
        summary = (
            await import_airports_csv(session, file_path)
            if file_path is not None
            else await import_airport_bundle(session, bundle_path)
        )
    print(
        f"snapshot={summary.snapshot_id} accepted={summary.accepted_rows} "
        f"rejected={summary.rejected_rows} existing={summary.already_imported}"
    )
