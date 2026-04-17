import pytest

from scripts.malden_car_ownership_maps import (
    aggregate_ward_car_ownership,
    build_area_records,
    build_car_ownership_colorizer,
    build_precinct_car_ownership_rows,
)


def test_build_precinct_car_ownership_rows_sorts_by_ward_and_precinct():
    precinct_rows = [
        {
            "precinct": "2-1",
            "ward": "2",
            "population_2020": 120.0,
            "estimated_vehicles_per_person": 0.80,
        },
        {
            "precinct": "1-2",
            "ward": "1",
            "population_2020": 90.0,
            "estimated_vehicles_per_person": 0.60,
        },
        {
            "precinct": "1-1",
            "ward": "1",
            "population_2020": 100.0,
            "estimated_vehicles_per_person": 0.50,
        },
    ]

    rows = build_precinct_car_ownership_rows(precinct_rows)

    assert [row["precinct"] for row in rows] == ["1-1", "1-2", "2-1"]
    assert rows[0]["estimated_vehicle_count"] == pytest.approx(50.0)
    assert rows[1]["estimated_vehicle_count"] == pytest.approx(54.0)


def test_aggregate_ward_car_ownership_uses_population_weighted_average():
    precinct_rows = [
        {
            "precinct": "1-1",
            "ward": "1",
            "population": 100.0,
            "estimated_vehicle_count": 50.0,
            "estimated_vehicles_per_person": 0.50,
        },
        {
            "precinct": "1-2",
            "ward": "1",
            "population": 50.0,
            "estimated_vehicle_count": 40.0,
            "estimated_vehicles_per_person": 0.80,
        },
        {
            "precinct": "2-1",
            "ward": "2",
            "population": 80.0,
            "estimated_vehicle_count": 48.0,
            "estimated_vehicles_per_person": 0.60,
        },
    ]

    ward_rows = aggregate_ward_car_ownership(precinct_rows)

    assert ward_rows == [
        {
            "ward": "1",
            "population": 150.0,
            "estimated_vehicle_count": 90.0,
            "estimated_vehicles_per_person": pytest.approx(0.6),
        },
        {
            "ward": "2",
            "population": 80.0,
            "estimated_vehicle_count": 48.0,
            "estimated_vehicles_per_person": pytest.approx(0.6),
        },
    ]


def test_build_area_records_and_colorizer_cover_full_range():
    rows = [
        {
            "precinct": "1-1",
            "ward": "1",
            "population": 100.0,
            "estimated_vehicle_count": 40.0,
            "estimated_vehicles_per_person": 0.4,
        },
        {
            "precinct": "2-1",
            "ward": "2",
            "population": 100.0,
            "estimated_vehicle_count": 80.0,
            "estimated_vehicles_per_person": 0.8,
        },
    ]

    records = build_area_records(rows, "precinct")
    color_fn, legend = build_car_ownership_colorizer([0.4, 0.8])

    assert records["1-1"].ward == "1"
    assert records["2-1"].estimated_vehicles_per_person == pytest.approx(0.8)
    assert legend.title == "Estimated cars per resident"
    assert [label for label, _ in legend.items] == ["0.40", "0.53", "0.66", "0.80"]
    assert color_fn(0.4) != color_fn(0.8)
