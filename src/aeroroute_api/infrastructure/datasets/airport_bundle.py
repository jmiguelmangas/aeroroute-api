"""Reader for immutable airport bundles produced by aeroroute-data."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AirportBundle:
    version: str
    bundle_sha256: str
    rejected_rows: int
    records: tuple[dict[str, object], ...]


def read_airport_bundle(directory: Path) -> AirportBundle:
    manifest = json.loads(
        (directory / "manifest.json").read_text(encoding="utf-8")
    )
    records = json.loads(
        (directory / "airports.normalized.json").read_text(encoding="utf-8")
    )
    if manifest.get("contract_version") != "1.0.0":
        raise ValueError("unsupported airport bundle contract version")
    if manifest.get("source_kind") not in {"public", "synthetic"}:
        raise ValueError("airport bundle source kind is invalid")
    if not isinstance(records, list) or not all(
        isinstance(record, dict) for record in records
    ):
        raise ValueError("airport bundle records are invalid")
    canonical = json.dumps(
        records, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    actual_checksum = hashlib.sha256(canonical.encode()).hexdigest()
    if actual_checksum != manifest.get("bundle_sha256"):
        raise ValueError("airport bundle checksum does not match manifest")
    return AirportBundle(
        version=str(manifest["version"]),
        bundle_sha256=actual_checksum,
        rejected_rows=int(manifest["rejected_rows"]),
        records=tuple(records),
    )
