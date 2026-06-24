import hashlib
import json
from pathlib import Path

import pytest

from aeroroute_api.infrastructure.datasets.airport_bundle import (
    read_airport_bundle,
)


def _write_bundle(directory: Path, checksum: str) -> None:
    records = [
        {
            "ident": "LEMD",
            "airport_type": "large_airport",
            "name": "Madrid",
            "latitude_deg": 40.47,
            "longitude_deg": -3.56,
            "elevation_ft": 2000,
            "iso_country": "ES",
            "municipality": "Madrid",
            "iata_code": "MAD",
        }
    ]
    (directory / "airports.normalized.json").write_text(json.dumps(records))
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "version": "2026.06.1",
                "bundle_sha256": checksum,
                "rejected_rows": 1,
                "source_kind": "public",
                "contract_version": "1.0.0",
            }
        )
    )


def test_reads_bundle_with_matching_manifest_checksum(tmp_path: Path) -> None:
    canonical = json.dumps(
        [
            {
                "ident": "LEMD",
                "airport_type": "large_airport",
                "name": "Madrid",
                "latitude_deg": 40.47,
                "longitude_deg": -3.56,
                "elevation_ft": 2000,
                "iso_country": "ES",
                "municipality": "Madrid",
                "iata_code": "MAD",
            }
        ],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    _write_bundle(tmp_path, hashlib.sha256(canonical.encode()).hexdigest())

    bundle = read_airport_bundle(tmp_path)

    assert bundle.version == "2026.06.1"
    assert bundle.records[0]["ident"] == "LEMD"


def test_rejects_bundle_with_mismatched_checksum(tmp_path: Path) -> None:
    _write_bundle(tmp_path, "0" * 64)

    with pytest.raises(ValueError, match="checksum"):
        read_airport_bundle(tmp_path)
