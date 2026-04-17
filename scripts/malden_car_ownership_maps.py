from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

try:
    from scripts.malden_override_map import (
        LegendSpec,
        build_basemap,
        interpolate_between_stops,
        load_precinct_geometries,
        render_map,
    )
    from scripts.malden_precinct_analysis import build_precinct_covariates
except ModuleNotFoundError:
    from malden_override_map import (  # type: ignore
        LegendSpec,
        build_basemap,
        interpolate_between_stops,
        load_precinct_geometries,
        render_map,
    )
    from malden_precinct_analysis import build_precinct_covariates  # type: ignore


ROOT = Path(__file__).resolve().parent.parent
OTHER_DATA_DIR = ROOT / "OtherData" / "CarOwnership"

CAR_OWNERSHIP_COLOR_STOPS = [
    (0.0, (255, 255, 217)),
    (0.33, (127, 205, 187)),
    (0.66, (44, 127, 184)),
    (1.0, (37, 52, 148)),
]


@dataclass(frozen=True)
class AreaCarOwnership:
    label: str
    estimated_vehicle_count: float
    population: float
    estimated_vehicles_per_person: float

    @property
    def ward(self) -> str:
        return self.label.split("-")[0] if "-" in self.label else self.label


def build_precinct_car_ownership_rows(
    precinct_rows: list[dict[str, float | str | None]],
) -> list[dict[str, float | str]]:
    rows: list[dict[str, float | str]] = []
    for row in precinct_rows:
        value = row.get("estimated_vehicles_per_person")
        if value is None:
            continue
        population_value = row.get("acs_population_estimate")
        if population_value is None:
            population_value = row.get("population_2020")
        if population_value is None:
            raise KeyError("Expected an ACS or 2020 population field for car-ownership export")

        estimated_vehicle_count = row.get("estimated_vehicle_count")
        if estimated_vehicle_count is None:
            estimated_vehicle_count = float(value) * float(population_value)

        rows.append(
            {
                "precinct": str(row["precinct"]),
                "ward": str(row["ward"]),
                "population": float(population_value),
                "estimated_vehicle_count": float(estimated_vehicle_count),
                "estimated_vehicles_per_person": float(value),
            }
        )
    return sorted(rows, key=lambda item: (int(str(item["ward"])), str(item["precinct"])))


def aggregate_ward_car_ownership(
    precinct_rows: list[dict[str, float | str]],
) -> list[dict[str, float | str]]:
    ward_totals: dict[str, dict[str, float]] = {}
    for row in precinct_rows:
        ward = str(row["ward"])
        totals = ward_totals.setdefault(ward, {"population": 0.0, "estimated_vehicle_count": 0.0})
        totals["population"] += float(row["population"])
        totals["estimated_vehicle_count"] += float(row["estimated_vehicle_count"])

    ward_rows: list[dict[str, float | str]] = []
    for ward, totals in sorted(ward_totals.items(), key=lambda item: int(item[0])):
        ward_rows.append(
            {
                "ward": ward,
                "population": totals["population"],
                "estimated_vehicle_count": totals["estimated_vehicle_count"],
                "estimated_vehicles_per_person": totals["estimated_vehicle_count"] / totals["population"],
            }
        )
    return ward_rows


def build_area_records(
    rows: list[dict[str, float | str]],
    key_field: str,
) -> dict[str, AreaCarOwnership]:
    return {
        str(row[key_field]): AreaCarOwnership(
            label=str(row[key_field]),
            population=float(row["population"]),
            estimated_vehicle_count=float(row["estimated_vehicle_count"]),
            estimated_vehicles_per_person=float(row["estimated_vehicles_per_person"]),
        )
        for row in rows
    }


def build_ward_geometries(
    precinct_geometries: dict[str, Polygon | MultiPolygon],
) -> dict[str, Polygon | MultiPolygon]:
    ward_geometries: dict[str, Polygon | MultiPolygon] = {}
    for ward in sorted({precinct.split("-")[0] for precinct in precinct_geometries}, key=int):
        ward_geometries[ward] = unary_union(
            [geometry for precinct, geometry in precinct_geometries.items() if precinct.split("-")[0] == ward]
        )
    return ward_geometries


def build_car_ownership_colorizer(
    values: list[float],
) -> tuple[callable, LegendSpec]:
    min_value = min(values)
    max_value = max(values)
    if max_value <= min_value:
        max_value = min_value + 0.01

    def color_fn(value: float) -> tuple[int, int, int]:
        normalized = (value - min_value) / (max_value - min_value)
        return interpolate_between_stops(normalized, CAR_OWNERSHIP_COLOR_STOPS)

    legend_values = [
        min_value + (max_value - min_value) * fraction for fraction in (0.0, 0.33, 0.66, 1.0)
    ]
    legend = LegendSpec(
        title="Estimated cars per resident",
        items=[(f"{value:.2f}", color_fn(value)) for value in legend_values],
        position="bottom-right",
    )
    return color_fn, legend


def write_rows_csv(rows: list[dict[str, float | str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def generate_all_outputs() -> None:
    precinct_covariates = build_precinct_covariates()
    precinct_rows = build_precinct_car_ownership_rows(precinct_covariates)
    ward_rows = aggregate_ward_car_ownership(precinct_rows)

    write_rows_csv(precinct_rows, OTHER_DATA_DIR / "malden_precinct_car_ownership.csv")
    write_rows_csv(ward_rows, OTHER_DATA_DIR / "malden_ward_car_ownership.csv")

    precinct_records = build_area_records(precinct_rows, "precinct")
    ward_records = build_area_records(ward_rows, "ward")

    precinct_geometries = load_precinct_geometries()
    ward_geometries = build_ward_geometries(precinct_geometries)

    all_values = [
        *(record.estimated_vehicles_per_person for record in precinct_records.values()),
        *(record.estimated_vehicles_per_person for record in ward_records.values()),
    ]
    color_fn, legend = build_car_ownership_colorizer(all_values)

    precinct_basemap = build_basemap(precinct_geometries)
    render_map(
        "Malden estimated cars per resident by precinct",
        lambda record: record.estimated_vehicles_per_person,
        precinct_records,
        precinct_geometries,
        precinct_basemap,
        OTHER_DATA_DIR / "malden_car_ownership_precinct_map",
        color_fn,
        legend,
    )

    ward_basemap = build_basemap(ward_geometries)
    render_map(
        "Malden estimated cars per resident by ward",
        lambda record: record.estimated_vehicles_per_person,
        ward_records,
        ward_geometries,
        ward_basemap,
        OTHER_DATA_DIR / "malden_car_ownership_ward_map",
        color_fn,
        legend,
    )


if __name__ == "__main__":
    generate_all_outputs()
