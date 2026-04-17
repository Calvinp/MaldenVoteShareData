import pytest

from scripts.malden_car_ownership_maps import (
    METRICS,
    aggregate_ward_car_ownership,
    build_area_records,
    build_metric_colorizer,
    build_metric_label_lines,
    build_precinct_car_ownership_rows,
)


def test_build_precinct_car_ownership_rows_derives_all_metrics_and_sorts():
    precinct_rows = [
        {
            "precinct": "2-1",
            "ward": "2",
            "acs_population_estimate": 120.0,
            "adult_share": 0.75,
            "estimated_vehicle_count": 96.0,
            "estimated_vehicles_per_household": 1.6,
        },
        {
            "precinct": "1-2",
            "ward": "1",
            "population_2020": 90.0,
            "adult_share": 0.80,
            "estimated_vehicle_count": 54.0,
            "estimated_vehicles_per_household": 1.2,
        },
        {
            "precinct": "1-1",
            "ward": "1",
            "population_2020": 100.0,
            "adult_share": 0.70,
            "estimated_vehicle_count": 50.0,
            "estimated_vehicles_per_household": 1.0,
        },
    ]

    rows = build_precinct_car_ownership_rows(precinct_rows)

    assert [row["precinct"] for row in rows] == ["1-1", "1-2", "2-1"]
    assert rows[0]["adult_population"] == pytest.approx(70.0)
    assert rows[0]["estimated_households"] == pytest.approx(50.0)
    assert rows[0]["estimated_vehicles_per_person"] == pytest.approx(0.5)
    assert rows[0]["estimated_vehicles_per_adult"] == pytest.approx(50.0 / 70.0)
    assert rows[0]["estimated_residents_with_car_share"] == pytest.approx(0.5)


def test_aggregate_ward_car_ownership_uses_denominator_appropriate_to_each_metric():
    precinct_rows = [
        {
            "precinct": "1-1",
            "ward": "1",
            "population": 100.0,
            "adult_population": 70.0,
            "estimated_households": 50.0,
            "estimated_vehicle_count": 50.0,
            "estimated_vehicles_per_person": 0.50,
            "estimated_vehicles_per_household": 1.0,
            "estimated_vehicles_per_adult": 50.0 / 70.0,
            "estimated_residents_with_car_share": 0.50,
        },
        {
            "precinct": "1-2",
            "ward": "1",
            "population": 50.0,
            "adult_population": 40.0,
            "estimated_households": 25.0,
            "estimated_vehicle_count": 40.0,
            "estimated_vehicles_per_person": 0.80,
            "estimated_vehicles_per_household": 1.6,
            "estimated_vehicles_per_adult": 1.0,
            "estimated_residents_with_car_share": 0.80,
        },
    ]

    ward_rows = aggregate_ward_car_ownership(precinct_rows)

    assert ward_rows == [
        {
            "ward": "1",
            "population": 150.0,
            "adult_population": 110.0,
            "estimated_households": 75.0,
            "estimated_vehicle_count": 90.0,
            "estimated_vehicles_per_person": pytest.approx(0.6),
            "estimated_vehicles_per_household": pytest.approx(1.2),
            "estimated_vehicles_per_adult": pytest.approx(90.0 / 110.0),
            "estimated_residents_with_car_share": pytest.approx(0.6),
        }
    ]


def test_build_area_records_and_colorizer_cover_full_range():
    rows = [
        {
            "precinct": "1-1",
            "ward": "1",
            "population": 100.0,
            "adult_population": 70.0,
            "estimated_households": 50.0,
            "estimated_vehicle_count": 40.0,
            "estimated_vehicles_per_person": 0.4,
            "estimated_vehicles_per_household": 0.8,
            "estimated_vehicles_per_adult": 40.0 / 70.0,
            "estimated_residents_with_car_share": 0.4,
        },
        {
            "precinct": "2-1",
            "ward": "2",
            "population": 100.0,
            "adult_population": 80.0,
            "estimated_households": 40.0,
            "estimated_vehicle_count": 80.0,
            "estimated_vehicles_per_person": 0.8,
            "estimated_vehicles_per_household": 2.0,
            "estimated_vehicles_per_adult": 1.0,
            "estimated_residents_with_car_share": 0.8,
        },
    ]

    records = build_area_records(rows, "precinct")
    color_fn, legend = build_metric_colorizer([0.4, 0.8], METRICS[0])

    assert records["1-1"].ward == "1"
    assert records["2-1"].estimated_vehicle_count == pytest.approx(80.0)
    assert legend.title == "Estimated cars per resident"
    assert [label for label, _ in legend.items] == ["0.40", "0.53", "0.66", "0.80"]
    assert color_fn(0.4) != color_fn(0.8)


def test_pct_metric_legend_formats_as_percent():
    color_fn, legend = build_metric_colorizer([0.4, 0.8], METRICS[3])

    assert legend.title == "Estimated resident car coverage"
    assert [label for label, _ in legend.items] == ["40%", "53%", "66%", "80%"]
    assert color_fn(0.4) != color_fn(0.8)


def test_build_metric_label_lines_formats_decimal_and_percent_values():
    area = build_area_records(
        [
            {
                "precinct": "1-1",
                "ward": "1",
                "population": 100.0,
                "adult_population": 80.0,
                "estimated_households": 50.0,
                "estimated_vehicle_count": 40.0,
                "estimated_vehicles_per_person": 0.4,
                "estimated_vehicles_per_household": 0.8,
                "estimated_vehicles_per_adult": 0.5,
                "estimated_residents_with_car_share": 0.4,
            }
        ],
        "precinct",
    )["1-1"]

    assert build_metric_label_lines(area, METRICS[0]) == ["1-1", "(0.40)"]
    assert build_metric_label_lines(area, METRICS[3]) == ["1-1", "(40%)"]
