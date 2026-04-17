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
    population: float
    adult_population: float
    estimated_households: float
    estimated_vehicle_count: float

    @property
    def ward(self) -> str:
        return self.label.split("-")[0] if "-" in self.label else self.label


@dataclass(frozen=True)
class MetricSpec:
    column: str
    title: str
    legend_title: str
    output_stem_prefix: str
    formatter: str

    def compute(self, area: AreaCarOwnership) -> float:
        if self.column == "estimated_vehicles_per_person":
            return safe_divide(area.estimated_vehicle_count, area.population)
        if self.column == "estimated_vehicles_per_household":
            return safe_divide(area.estimated_vehicle_count, area.estimated_households)
        if self.column == "estimated_vehicles_per_adult":
            return safe_divide(area.estimated_vehicle_count, area.adult_population)
        if self.column == "estimated_residents_with_car_share":
            return safe_divide(min(area.estimated_vehicle_count, area.population), area.population)
        raise ValueError(f"Unknown metric: {self.column}")


METRICS = [
    MetricSpec(
        column="estimated_vehicles_per_person",
        title="Malden estimated cars per resident by {level}",
        legend_title="Estimated cars per resident",
        output_stem_prefix="malden_cars_per_resident",
        formatter="decimal",
    ),
    MetricSpec(
        column="estimated_vehicles_per_household",
        title="Malden estimated cars per household by {level}",
        legend_title="Estimated cars per household",
        output_stem_prefix="malden_cars_per_household",
        formatter="decimal",
    ),
    MetricSpec(
        column="estimated_vehicles_per_adult",
        title="Malden estimated cars per adult resident by {level}",
        legend_title="Estimated cars per adult",
        output_stem_prefix="malden_cars_per_adult",
        formatter="decimal",
    ),
    MetricSpec(
        column="estimated_residents_with_car_share",
        title="Malden estimated resident car coverage share by {level}",
        legend_title="Estimated resident car coverage",
        output_stem_prefix="malden_resident_car_coverage",
        formatter="pct",
    ),
]


def safe_divide(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def build_precinct_car_ownership_rows(
    precinct_rows: list[dict[str, float | str | None]],
) -> list[dict[str, float | str]]:
    rows: list[dict[str, float | str]] = []
    for row in precinct_rows:
        population_value = row.get("acs_population_estimate")
        if population_value is None:
            population_value = row.get("population_2020")
        if population_value is None:
            raise KeyError("Expected an ACS or 2020 population field for car-ownership export")

        adult_share = row.get("adult_share")
        adult_population = float(population_value) * float(adult_share) if adult_share is not None else float(population_value)

        estimated_vehicle_count = row.get("estimated_vehicle_count")
        estimated_vehicles_per_household = row.get("estimated_vehicles_per_household")
        estimated_vehicles_per_person = row.get("estimated_vehicles_per_person")
        if estimated_vehicle_count is None:
            if estimated_vehicles_per_person is None:
                raise KeyError("Expected an estimated vehicle count or per-person vehicle metric")
            estimated_vehicle_count = float(estimated_vehicles_per_person) * float(population_value)

        if estimated_vehicles_per_household is None:
            raise KeyError("Expected estimated_vehicles_per_household for car-ownership export")
        estimated_households = safe_divide(float(estimated_vehicle_count), float(estimated_vehicles_per_household))

        area = AreaCarOwnership(
            label=str(row["precinct"]),
            population=float(population_value),
            adult_population=adult_population,
            estimated_households=estimated_households,
            estimated_vehicle_count=float(estimated_vehicle_count),
        )
        rows.append(export_row(area))
    return sorted(rows, key=lambda item: (int(str(item["ward"])), str(item["precinct"])))


def aggregate_ward_car_ownership(
    precinct_rows: list[dict[str, float | str]],
) -> list[dict[str, float | str]]:
    ward_totals: dict[str, AreaCarOwnership] = {}
    for row in precinct_rows:
        ward = str(row["ward"])
        existing = ward_totals.get(ward)
        current = AreaCarOwnership(
            label=ward,
            population=float(row["population"]),
            adult_population=float(row["adult_population"]),
            estimated_households=float(row["estimated_households"]),
            estimated_vehicle_count=float(row["estimated_vehicle_count"]),
        )
        if existing is None:
            ward_totals[ward] = current
        else:
            ward_totals[ward] = AreaCarOwnership(
                label=ward,
                population=existing.population + current.population,
                adult_population=existing.adult_population + current.adult_population,
                estimated_households=existing.estimated_households + current.estimated_households,
                estimated_vehicle_count=existing.estimated_vehicle_count + current.estimated_vehicle_count,
            )

    return [export_row(area) for _, area in sorted(ward_totals.items(), key=lambda item: int(item[0]))]


def export_row(area: AreaCarOwnership) -> dict[str, float | str]:
    row: dict[str, float | str] = {
        "population": area.population,
        "adult_population": area.adult_population,
        "estimated_households": area.estimated_households,
        "estimated_vehicle_count": area.estimated_vehicle_count,
    }
    if "-" in area.label:
        row["precinct"] = area.label
        row["ward"] = area.ward
    else:
        row["ward"] = area.label

    for metric in METRICS:
        row[metric.column] = metric.compute(area)
    return row


def build_area_records(
    rows: list[dict[str, float | str]],
    key_field: str,
) -> dict[str, AreaCarOwnership]:
    return {
        str(row[key_field]): AreaCarOwnership(
            label=str(row[key_field]),
            population=float(row["population"]),
            adult_population=float(row["adult_population"]),
            estimated_households=float(row["estimated_households"]),
            estimated_vehicle_count=float(row["estimated_vehicle_count"]),
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


def format_metric_value(value: float, formatter: str) -> str:
    if formatter == "pct":
        return f"{value * 100:.0f}%"
    return f"{value:.2f}"


def build_metric_label_lines(area: AreaCarOwnership, metric: MetricSpec) -> list[str]:
    return [area.label, f"({format_metric_value(metric.compute(area), metric.formatter)})"]


def build_metric_colorizer(
    values: list[float],
    metric: MetricSpec,
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
        title=metric.legend_title,
        items=[(format_metric_value(value, metric.formatter), color_fn(value)) for value in legend_values],
        position="bottom-right",
    )
    return color_fn, legend


def write_rows_csv(rows: list[dict[str, float | str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def render_metric_maps(
    area_records: dict[str, AreaCarOwnership],
    geometries: dict[str, Polygon | MultiPolygon],
    level: str,
    metric_colorizers: dict[str, tuple[callable, LegendSpec]],
) -> None:
    basemap = build_basemap(geometries)
    for metric in METRICS:
        color_fn, legend = metric_colorizers[metric.column]
        render_map(
            metric.title.format(level=level),
            metric.compute,
            area_records,
            geometries,
            basemap,
            OTHER_DATA_DIR / f"{metric.output_stem_prefix}_{level}_map",
            color_fn,
            legend,
            label_text_getter=lambda area, metric=metric: build_metric_label_lines(area, metric),
        )


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

    metric_colorizers = {
        metric.column: build_metric_colorizer(
            [
                *(metric.compute(area) for area in precinct_records.values()),
                *(metric.compute(area) for area in ward_records.values()),
            ],
            metric,
        )
        for metric in METRICS
    }

    render_metric_maps(precinct_records, precinct_geometries, "precinct", metric_colorizers)
    render_metric_maps(ward_records, ward_geometries, "ward", metric_colorizers)


if __name__ == "__main__":
    generate_all_outputs()
