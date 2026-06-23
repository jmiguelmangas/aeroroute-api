from aeroroute_api.application.services.optimization import optimize_still_air


def test_optimizer_use_case_delegates_to_versioned_package() -> None:
    result = optimize_still_air(
        40.4722,
        -3.5608,
        40.6413,
        -73.7781,
        "A320",
        "minimum_fuel",
    )

    assert result.status == "optimal"
    assert result.algorithm_version == "0.1.0"
    assert result.winner is not None
    assert result.winner.path[0].startswith("0:")
    assert result.winner.path[-1].startswith("6:")
