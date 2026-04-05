from __future__ import annotations

import csv
import json
import math
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean

from scipy.stats import pearsonr, spearmanr
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.ops import unary_union

try:
    from scripts.malden_override_map import OUTPUT_DIR, load_precinct_geometries, load_precinct_results
    from scripts.malden_turnout_graphs import load_precinct_turnout
except ModuleNotFoundError:
    from malden_override_map import OUTPUT_DIR, load_precinct_geometries, load_precinct_results  # type: ignore
    from malden_turnout_graphs import load_precinct_turnout  # type: ignore


ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_CACHE_DIR = ROOT / ".cache" / "precinct_analysis"
USER_AGENT = "Prop2.5OverrideData/1.0 (side-project precinct correlation analysis)"
CACHE_VERSION = "v2"

STATE_FIPS = "25"
COUNTY_FIPS = "017"
ACS_YEAR = "2024"
ACS_DATASET = "acs/acs5"
PL_YEAR = "2020"
PL_DATASET = "dec/pl"

BLOCK_GROUP_LAYER_ID = 1
BLOCK_LAYER_ID = 2
TIGERWEB_MAPSERVER = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Tracts_Blocks/MapServer"

COVARIATES_OUTPUT_PATH = OUTPUT_DIR / "malden_precinct_covariates.csv"
REPORT_OUTPUT_PATH = OUTPUT_DIR / "malden_vote_correlation_report.md"

BLOCK_FIELDS = ["GEOID", "OID", "AREALAND"]
BLOCK_GROUP_FIELDS = ["GEOID", "OID", "AREALAND"]

BLOCK_VARIABLES = [
    "P1_001N",
    "P1_003N",
    "P1_004N",
    "P1_006N",
    "P1_009N",
    "P2_002N",
]

# Parent-station coordinates from MBTA's official V3 stops API.
MBTA_PARENT_STOPS = {
    "Malden Center": (42.426632, -71.07411),
    "Oak Grove": (42.43668, -71.071097),
    "Wellington": (42.40237, -71.077082),
}

ACS_VARIABLES = [
    "B01001_001E",
    "B01001_002E",
    "B01001_003E",
    "B01001_004E",
    "B01001_005E",
    "B01001_006E",
    "B01001_007E",
    "B01001_008E",
    "B01001_009E",
    "B01001_010E",
    "B01001_011E",
    "B01001_012E",
    "B01001_013E",
    "B01001_014E",
    "B01001_015E",
    "B01001_016E",
    "B01001_017E",
    "B01001_018E",
    "B01001_019E",
    "B01001_020E",
    "B01001_021E",
    "B01001_022E",
    "B01001_023E",
    "B01001_024E",
    "B01001_025E",
    "B01001_026E",
    "B01001_027E",
    "B01001_028E",
    "B01001_029E",
    "B01001_030E",
    "B01001_031E",
    "B01001_032E",
    "B01001_033E",
    "B01001_034E",
    "B01001_035E",
    "B01001_036E",
    "B01001_037E",
    "B01001_038E",
    "B01001_039E",
    "B01001_040E",
    "B01001_041E",
    "B01001_042E",
    "B01001_043E",
    "B01001_044E",
    "B01001_045E",
    "B01001_046E",
    "B01001_047E",
    "B01001_048E",
    "B01001_049E",
    "B01002_001E",
    "B08301_001E",
    "B08301_003E",
    "B08301_004E",
    "B08301_010E",
    "B08301_018E",
    "B08301_019E",
    "B08301_021E",
    "B15003_001E",
    "B15003_022E",
    "B15003_023E",
    "B15003_024E",
    "B15003_025E",
    "B19013_001E",
    "B25003_001E",
    "B25003_002E",
    "B25003_003E",
    "B25044_001E",
    "B25044_003E",
    "B25044_004E",
    "B25044_006E",
    "B25044_007E",
    "B25044_010E",
    "B25044_011E",
    "B25044_013E",
    "B25044_014E",
    "B25064_001E",
]

ACS_AGE_UNDER_18_CODES = [
    "B01001_003E",
    "B01001_004E",
    "B01001_005E",
    "B01001_006E",
    "B01001_027E",
    "B01001_028E",
    "B01001_029E",
    "B01001_030E",
]
ACS_AGE_18_TO_34_CODES = [
    "B01001_007E",
    "B01001_008E",
    "B01001_009E",
    "B01001_010E",
    "B01001_011E",
    "B01001_012E",
    "B01001_031E",
    "B01001_032E",
    "B01001_033E",
    "B01001_034E",
    "B01001_035E",
    "B01001_036E",
]
ACS_AGE_35_TO_64_CODES = [
    "B01001_013E",
    "B01001_014E",
    "B01001_015E",
    "B01001_016E",
    "B01001_017E",
    "B01001_018E",
    "B01001_019E",
    "B01001_037E",
    "B01001_038E",
    "B01001_039E",
    "B01001_040E",
    "B01001_041E",
    "B01001_042E",
    "B01001_043E",
]
ACS_AGE_65_PLUS_CODES = [
    "B01001_020E",
    "B01001_021E",
    "B01001_022E",
    "B01001_023E",
    "B01001_024E",
    "B01001_025E",
    "B01001_044E",
    "B01001_045E",
    "B01001_046E",
    "B01001_047E",
    "B01001_048E",
    "B01001_049E",
]

ANALYSIS_VARIABLES = [
    "registered_voters",
    "turnout_pct",
    "precinct_area_sq_miles",
    "population_density_per_sq_mile",
    "nearest_mbta_stop_distance_miles",
    "white_share_2020",
    "black_share_2020",
    "asian_share_2020",
    "multiracial_share_2020",
    "hispanic_share_2020",
    "male_share",
    "under_18_share",
    "age_18_to_34_share",
    "age_35_to_64_share",
    "age_65_plus_share",
    "adult_share",
    "median_age_estimate",
    "median_household_income_estimate",
    "owner_share",
    "renter_share",
    "median_gross_rent_estimate",
    "no_vehicle_share",
    "one_vehicle_share",
    "three_plus_vehicle_share",
    "drive_alone_share",
    "carpool_share",
    "transit_share",
    "bicycle_share",
    "walk_share",
    "work_from_home_share",
    "bachelors_plus_share",
]

OUTCOME_LABELS = {
    "q1a_yes_pct": "Q1A yes share",
    "q1b_yes_pct": "Q1B yes share",
    "q1a_minus_q1b_yes_pct": "Q1A minus Q1B yes-share gap",
}

VARIABLE_LABELS = {
    "registered_voters": "Registered voters",
    "ballots_cast": "Ballots cast",
    "turnout_pct": "Turnout %",
    "population_2020": "2020 Census population",
    "precinct_area_sq_miles": "Precinct area (sq mi)",
    "population_density_per_sq_mile": "Population density",
    "nearest_mbta_stop_distance_miles": "Distance to nearest MBTA stop (mi)",
    "white_share_2020": "White share (2020)",
    "black_share_2020": "Black share (2020)",
    "asian_share_2020": "Asian share (2020)",
    "multiracial_share_2020": "Multiracial share (2020)",
    "hispanic_share_2020": "Hispanic share (2020)",
    "male_share": "Male share",
    "under_18_share": "Under 18 share",
    "age_18_to_34_share": "Age 18-34 share",
    "age_35_to_64_share": "Age 35-64 share",
    "age_65_plus_share": "Age 65+ share",
    "adult_share": "Adult share",
    "median_age_estimate": "Median age estimate",
    "median_household_income_estimate": "Median household income estimate",
    "owner_share": "Owner-occupied share",
    "renter_share": "Renter share",
    "median_gross_rent_estimate": "Median gross rent estimate",
    "no_vehicle_share": "No-vehicle share",
    "one_vehicle_share": "One-vehicle share",
    "three_plus_vehicle_share": "3+ vehicle share",
    "drive_alone_share": "Drive-alone commute share",
    "carpool_share": "Carpool commute share",
    "transit_share": "Transit commute share",
    "bicycle_share": "Bicycle commute share",
    "walk_share": "Walk commute share",
    "work_from_home_share": "Work-from-home share",
    "bachelors_plus_share": "Bachelor's+ share",
}

REPORT_FIELD_SPECS = {
    "registered_voters": ("count", 0),
    "ballots_cast": ("count", 0),
    "turnout_pct": ("pct", 1),
    "population_2020": ("count", 0),
    "precinct_area_sq_miles": ("decimal", 2),
    "population_density_per_sq_mile": ("count", 0),
    "nearest_mbta_stop_distance_miles": ("decimal", 2),
    "white_share_2020": ("pct", 1),
    "black_share_2020": ("pct", 1),
    "asian_share_2020": ("pct", 1),
    "multiracial_share_2020": ("pct", 1),
    "hispanic_share_2020": ("pct", 1),
    "male_share": ("pct", 1),
    "under_18_share": ("pct", 1),
    "age_18_to_34_share": ("pct", 1),
    "age_35_to_64_share": ("pct", 1),
    "age_65_plus_share": ("pct", 1),
    "adult_share": ("pct", 1),
    "median_age_estimate": ("decimal", 1),
    "median_household_income_estimate": ("currency", 0),
    "owner_share": ("pct", 1),
    "renter_share": ("pct", 1),
    "median_gross_rent_estimate": ("currency", 0),
    "no_vehicle_share": ("pct", 1),
    "one_vehicle_share": ("pct", 1),
    "three_plus_vehicle_share": ("pct", 1),
    "drive_alone_share": ("pct", 1),
    "carpool_share": ("pct", 1),
    "transit_share": ("pct", 1),
    "bicycle_share": ("pct", 1),
    "walk_share": ("pct", 1),
    "work_from_home_share": ("pct", 1),
    "bachelors_plus_share": ("pct", 1),
}


@dataclass(frozen=True)
class GeographyFeature:
    geoid: str
    geometry: Polygon | MultiPolygon
    area_land_sq_meters: float


@dataclass(frozen=True)
class CorrelationResult:
    variable: str
    outcome: str
    spearman_rho: float
    spearman_pvalue: float
    pearson_r: float
    pearson_pvalue: float
    n: int


def http_get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def load_json_cache(cache_path: Path, url: str) -> object:
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = http_get(url).decode("utf-8")
    cache_path.write_text(payload, encoding="utf-8")
    return json.loads(payload)


def chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def safe_float(value: object) -> float | None:
    if value in (None, "", "null"):
        return None
    numeric_value = float(value)
    if numeric_value < 0:
        return None
    return numeric_value


def sum_codes(row: dict[str, float | None], codes: list[str]) -> float:
    return sum((row.get(code) or 0.0) for code in codes)


def safe_divide(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def weighted_average(weighted_values: list[tuple[float, float]]) -> float | None:
    total_weight = sum(weight for _, weight in weighted_values if weight > 0)
    if total_weight <= 0:
        return None
    return sum(value * weight for value, weight in weighted_values if weight > 0) / total_weight


def weighted_point_coordinates(weighted_points: list[tuple[float, float, float]]) -> tuple[float, float] | None:
    total_weight = sum(weight for _, _, weight in weighted_points if weight > 0)
    if total_weight <= 0:
        return None
    latitude = sum(latitude * weight for latitude, _, weight in weighted_points if weight > 0) / total_weight
    longitude = sum(longitude * weight for _, longitude, weight in weighted_points if weight > 0) / total_weight
    return latitude, longitude


def geometry_centroid_coordinates(geometry: Polygon | MultiPolygon) -> tuple[float, float]:
    centroid = geometry.centroid
    return centroid.y, centroid.x


def haversine_distance_miles(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    earth_radius_miles = 3958.7613
    latitude_a_radians = math.radians(latitude_a)
    latitude_b_radians = math.radians(latitude_b)
    delta_latitude = math.radians(latitude_b - latitude_a)
    delta_longitude = math.radians(longitude_b - longitude_a)

    haversine = (
        math.sin(delta_latitude / 2) ** 2
        + math.cos(latitude_a_radians) * math.cos(latitude_b_radians) * math.sin(delta_longitude / 2) ** 2
    )
    return 2 * earth_radius_miles * math.asin(math.sqrt(haversine))


def nearest_mbta_stop(latitude: float, longitude: float) -> tuple[str, float]:
    return min(
        (
            (
                stop_name,
                haversine_distance_miles(latitude, longitude, stop_latitude, stop_longitude),
            )
            for stop_name, (stop_latitude, stop_longitude) in MBTA_PARENT_STOPS.items()
        ),
        key=lambda item: item[1],
    )


def query_tigerweb_geojson(
    layer_id: int,
    bounds: tuple[float, float, float, float],
    fields: list[str],
    cache_stem: str,
) -> list[dict[str, object]]:
    cache_path = ANALYSIS_CACHE_DIR / f"{cache_stem}.geojson"
    if cache_path.exists():
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        return data["features"]

    all_features: list[dict[str, object]] = []
    result_offset = 0
    while True:
        params = {
            "geometry": ",".join(f"{value:.6f}" for value in bounds),
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "where": f"STATE='{STATE_FIPS}' AND COUNTY='{COUNTY_FIPS}'",
            "outFields": ",".join(fields),
            "returnGeometry": "true",
            "f": "geojson",
            "orderByFields": "OID",
            "resultOffset": str(result_offset),
            "resultRecordCount": "1000",
        }
        url = f"{TIGERWEB_MAPSERVER}/{layer_id}/query?{urllib.parse.urlencode(params)}"
        page = json.loads(http_get(url).decode("utf-8"))
        features = page.get("features", [])
        all_features.extend(features)
        if not page.get("properties", {}).get("exceededTransferLimit"):
            break
        result_offset += len(features)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps({"type": "FeatureCollection", "features": all_features}), encoding="utf-8")
    return all_features


def load_precinct_union(precinct_geometries: dict[str, Polygon | MultiPolygon]) -> Polygon | MultiPolygon:
    return unary_union(list(precinct_geometries.values()))


def load_source_geometries(
    layer_id: int,
    precinct_geometries: dict[str, Polygon | MultiPolygon],
    cache_stem: str,
    geoid_key: str = "GEOID",
) -> list[GeographyFeature]:
    city_union = load_precinct_union(precinct_geometries)
    bounds = city_union.bounds
    features = query_tigerweb_geojson(
        layer_id,
        bounds,
        BLOCK_FIELDS if layer_id == BLOCK_LAYER_ID else BLOCK_GROUP_FIELDS,
        cache_stem,
    )

    source_features: list[GeographyFeature] = []
    for feature in features:
        geometry = shape(feature["geometry"])
        if not geometry.intersects(city_union):
            continue
        if geometry.intersection(city_union).area <= 0:
            continue
        properties = feature["properties"]
        source_features.append(
            GeographyFeature(
                geoid=str(properties[geoid_key]),
                geometry=geometry,
                area_land_sq_meters=float(properties.get("AREALAND") or 0.0),
            )
        )
    return source_features


def parse_census_api_table(
    table: list[list[str]],
    geography_fields: list[str],
) -> dict[str, dict[str, float | None]]:
    header = table[0]
    rows = table[1:]
    value_columns = [column for column in header if column not in geography_fields and column != "NAME"]

    parsed: dict[str, dict[str, float | None]] = {}
    for row in rows:
        row_map = dict(zip(header, row))
        geoid = "".join(row_map[field] for field in geography_fields)
        parsed[geoid] = {column: safe_float(row_map[column]) for column in value_columns}
    return parsed


def fetch_acs_block_group_data() -> dict[str, dict[str, float | None]]:
    grouped_rows: dict[str, dict[str, float | None]] = {}
    for index, variable_chunk in enumerate(chunked(ACS_VARIABLES, 25), start=1):
        params = {
            "get": ",".join(["NAME", *variable_chunk]),
            "for": "block group:*",
            "in": f"state:{STATE_FIPS} county:{COUNTY_FIPS} tract:*",
        }
        url = f"https://api.census.gov/data/{ACS_YEAR}/{ACS_DATASET}?{urllib.parse.urlencode(params)}"
        table = load_json_cache(ANALYSIS_CACHE_DIR / f"acs_block_groups_{CACHE_VERSION}_{index}.json", url)
        chunk_rows = parse_census_api_table(table, ["state", "county", "tract", "block group"])
        for geoid, values in chunk_rows.items():
            grouped_rows.setdefault(geoid, {}).update(values)
    return grouped_rows


def fetch_pl_block_data(tract_geoids: list[str]) -> dict[str, dict[str, float | None]]:
    block_rows: dict[str, dict[str, float | None]] = {}
    for tract_geoid in tract_geoids:
        tract = tract_geoid[-6:]
        params = {
            "get": ",".join(["NAME", *BLOCK_VARIABLES]),
            "for": "block:*",
            "in": f"state:{STATE_FIPS} county:{COUNTY_FIPS} tract:{tract}",
        }
        url = f"https://api.census.gov/data/{PL_YEAR}/{PL_DATASET}?{urllib.parse.urlencode(params)}"
        table = load_json_cache(ANALYSIS_CACHE_DIR / "pl_blocks" / f"{tract_geoid}.json", url)
        block_rows.update(parse_census_api_table(table, ["state", "county", "tract", "block"]))
    return block_rows


def estimate_area_overlap_share(
    precinct_geometry: Polygon | MultiPolygon,
    source_geometry: Polygon | MultiPolygon,
) -> float:
    source_area = source_geometry.area
    if source_area <= 0:
        return 0.0
    overlap_area = precinct_geometry.intersection(source_geometry).area
    if overlap_area <= 0:
        return 0.0
    return overlap_area / source_area


def build_overlap_lookup(
    precinct_geometries: dict[str, Polygon | MultiPolygon],
    source_features: list[GeographyFeature],
) -> dict[str, dict[str, float]]:
    overlaps = {precinct: {} for precinct in precinct_geometries}
    for precinct_name, precinct_geometry in precinct_geometries.items():
        for feature in source_features:
            share = estimate_area_overlap_share(precinct_geometry, feature.geometry)
            if share > 0:
                overlaps[precinct_name][feature.geoid] = share
    return overlaps


def polygon_ring_area_sq_miles(coordinates: list[tuple[float, float]], reference_lat: float) -> float:
    if len(coordinates) < 3:
        return 0.0

    x_values: list[float] = []
    y_values: list[float] = []
    miles_per_degree_lat = 69.172
    miles_per_degree_lon = miles_per_degree_lat * math.cos(math.radians(reference_lat))
    origin_lon, origin_lat = coordinates[0]
    for lon, lat in coordinates:
        x_values.append((lon - origin_lon) * miles_per_degree_lon)
        y_values.append((lat - origin_lat) * miles_per_degree_lat)

    area = 0.0
    for index in range(len(coordinates) - 1):
        area += x_values[index] * y_values[index + 1]
        area -= x_values[index + 1] * y_values[index]
    return abs(area) / 2.0


def geometry_area_sq_miles(geometry: Polygon | MultiPolygon) -> float:
    centroid_lat = geometry.centroid.y

    def polygon_area(polygon: Polygon) -> float:
        exterior = polygon_ring_area_sq_miles(list(polygon.exterior.coords), centroid_lat)
        holes = sum(polygon_ring_area_sq_miles(list(interior.coords), centroid_lat) for interior in polygon.interiors)
        return max(0.0, exterior - holes)

    if isinstance(geometry, Polygon):
        return polygon_area(geometry)
    return sum(polygon_area(polygon) for polygon in geometry.geoms)


def estimate_precinct_population_center(
    precinct_geometry: Polygon | MultiPolygon,
    precinct_overlap: dict[str, float],
    block_feature_lookup: dict[str, GeographyFeature],
    block_rows: dict[str, dict[str, float | None]],
) -> tuple[float, float, str]:
    weighted_points: list[tuple[float, float, float]] = []

    for geoid, share in precinct_overlap.items():
        if share <= 0:
            continue
        block_feature = block_feature_lookup.get(geoid)
        block_row = block_rows.get(geoid)
        if block_feature is None or block_row is None:
            continue

        estimated_population = (block_row.get("P1_001N") or 0.0) * share
        if estimated_population <= 0:
            continue

        overlap_geometry = precinct_geometry.intersection(block_feature.geometry)
        if overlap_geometry.is_empty or overlap_geometry.area <= 0:
            continue

        overlap_centroid = overlap_geometry.centroid
        weighted_points.append((overlap_centroid.y, overlap_centroid.x, estimated_population))

    weighted_center = weighted_point_coordinates(weighted_points)
    if weighted_center is not None:
        latitude, longitude = weighted_center
        return latitude, longitude, "population_weighted_block_centroid"

    latitude, longitude = geometry_centroid_coordinates(precinct_geometry)
    return latitude, longitude, "geographic_centroid"


def build_block_demographics(
    precinct_geometries: dict[str, Polygon | MultiPolygon],
    block_features: list[GeographyFeature],
    block_rows: dict[str, dict[str, float | None]],
) -> dict[str, dict[str, float | str | None]]:
    overlaps = build_overlap_lookup(precinct_geometries, block_features)
    block_feature_lookup = {feature.geoid: feature for feature in block_features}
    demographics: dict[str, dict[str, float | str | None]] = {}

    for precinct_name, precinct_overlap in overlaps.items():
        total_population = 0.0
        white = 0.0
        black = 0.0
        asian = 0.0
        multiracial = 0.0
        hispanic = 0.0
        for geoid, share in precinct_overlap.items():
            row = block_rows.get(geoid)
            if row is None:
                continue
            total_population += (row.get("P1_001N") or 0.0) * share
            white += (row.get("P1_003N") or 0.0) * share
            black += (row.get("P1_004N") or 0.0) * share
            asian += (row.get("P1_006N") or 0.0) * share
            multiracial += (row.get("P1_009N") or 0.0) * share
            hispanic += (row.get("P2_002N") or 0.0) * share

        population_center_latitude, population_center_longitude, population_center_source = (
            estimate_precinct_population_center(
                precinct_geometries[precinct_name],
                precinct_overlap,
                block_feature_lookup,
                block_rows,
            )
        )
        nearest_stop_name, nearest_stop_distance_miles = nearest_mbta_stop(
            population_center_latitude,
            population_center_longitude,
        )
        precinct_area = geometry_area_sq_miles(precinct_geometries[precinct_name])
        demographics[precinct_name] = {
            "population_2020": total_population,
            "precinct_area_sq_miles": precinct_area,
            "population_density_per_sq_mile": safe_divide(total_population, precinct_area),
            "population_center_latitude": population_center_latitude,
            "population_center_longitude": population_center_longitude,
            "population_center_source": population_center_source,
            "nearest_mbta_stop": nearest_stop_name,
            "nearest_mbta_stop_distance_miles": nearest_stop_distance_miles,
            "white_share_2020": safe_divide(white, total_population),
            "black_share_2020": safe_divide(black, total_population),
            "asian_share_2020": safe_divide(asian, total_population),
            "multiracial_share_2020": safe_divide(multiracial, total_population),
            "hispanic_share_2020": safe_divide(hispanic, total_population),
        }
    return demographics


def build_acs_covariates(
    precinct_geometries: dict[str, Polygon | MultiPolygon],
    block_group_features: list[GeographyFeature],
    block_group_rows: dict[str, dict[str, float | None]],
) -> dict[str, dict[str, float | None]]:
    overlaps = build_overlap_lookup(precinct_geometries, block_group_features)
    covariates: dict[str, dict[str, float | None]] = {}

    for precinct_name, precinct_overlap in overlaps.items():
        total_population = 0.0
        male_population = 0.0
        under_18_population = 0.0
        age_18_to_34_population = 0.0
        age_35_to_64_population = 0.0
        age_65_plus_population = 0.0
        occupied_housing = 0.0
        owner_housing = 0.0
        renter_housing = 0.0
        vehicle_households_total = 0.0
        no_vehicle = 0.0
        one_vehicle = 0.0
        three_plus_vehicle = 0.0
        commute_total = 0.0
        drive_alone = 0.0
        carpool = 0.0
        transit = 0.0
        bicycle = 0.0
        walk = 0.0
        work_from_home = 0.0
        education_total = 0.0
        bachelors_plus = 0.0
        median_age_weights: list[tuple[float, float]] = []
        income_weights: list[tuple[float, float]] = []
        rent_weights: list[tuple[float, float]] = []

        for geoid, share in precinct_overlap.items():
            row = block_group_rows.get(geoid)
            if row is None:
                continue

            population = (row.get("B01001_001E") or 0.0) * share
            households = (row.get("B25003_001E") or 0.0) * share
            renter_households = (row.get("B25003_003E") or 0.0) * share
            workers = (row.get("B08301_001E") or 0.0) * share
            vehicle_households = (row.get("B25044_001E") or 0.0) * share
            education_population = (row.get("B15003_001E") or 0.0) * share

            total_population += population
            male_population += (row.get("B01001_002E") or 0.0) * share
            under_18_population += sum_codes(row, ACS_AGE_UNDER_18_CODES) * share
            age_18_to_34_population += sum_codes(row, ACS_AGE_18_TO_34_CODES) * share
            age_35_to_64_population += sum_codes(row, ACS_AGE_35_TO_64_CODES) * share
            age_65_plus_population += sum_codes(row, ACS_AGE_65_PLUS_CODES) * share

            occupied_housing += households
            owner_housing += (row.get("B25003_002E") or 0.0) * share
            renter_housing += renter_households

            vehicle_households_total += vehicle_households
            no_vehicle += ((row.get("B25044_003E") or 0.0) + (row.get("B25044_010E") or 0.0)) * share
            one_vehicle += ((row.get("B25044_004E") or 0.0) + (row.get("B25044_011E") or 0.0)) * share
            three_plus_vehicle += (
                (row.get("B25044_006E") or 0.0)
                + (row.get("B25044_007E") or 0.0)
                + (row.get("B25044_013E") or 0.0)
                + (row.get("B25044_014E") or 0.0)
            ) * share

            commute_total += workers
            drive_alone += (row.get("B08301_003E") or 0.0) * share
            carpool += (row.get("B08301_004E") or 0.0) * share
            transit += (row.get("B08301_010E") or 0.0) * share
            bicycle += (row.get("B08301_018E") or 0.0) * share
            walk += (row.get("B08301_019E") or 0.0) * share
            work_from_home += (row.get("B08301_021E") or 0.0) * share

            education_total += education_population
            bachelors_plus += sum_codes(row, ["B15003_022E", "B15003_023E", "B15003_024E", "B15003_025E"]) * share

            median_age = row.get("B01002_001E")
            if median_age is not None and population > 0:
                median_age_weights.append((median_age, population))

            median_income = row.get("B19013_001E")
            if median_income is not None and households > 0:
                income_weights.append((median_income, households))

            median_rent = row.get("B25064_001E")
            if median_rent is not None and renter_households > 0:
                rent_weights.append((median_rent, renter_households))

        covariates[precinct_name] = {
            "male_share": safe_divide(male_population, total_population),
            "under_18_share": safe_divide(under_18_population, total_population),
            "age_18_to_34_share": safe_divide(age_18_to_34_population, total_population),
            "age_35_to_64_share": safe_divide(age_35_to_64_population, total_population),
            "age_65_plus_share": safe_divide(age_65_plus_population, total_population),
            "adult_share": safe_divide(total_population - under_18_population, total_population),
            "median_age_estimate": weighted_average(median_age_weights),
            "median_household_income_estimate": weighted_average(income_weights),
            "owner_share": safe_divide(owner_housing, occupied_housing),
            "renter_share": safe_divide(renter_housing, occupied_housing),
            "median_gross_rent_estimate": weighted_average(rent_weights),
            "no_vehicle_share": safe_divide(no_vehicle, vehicle_households_total),
            "one_vehicle_share": safe_divide(one_vehicle, vehicle_households_total),
            "three_plus_vehicle_share": safe_divide(three_plus_vehicle, vehicle_households_total),
            "drive_alone_share": safe_divide(drive_alone, commute_total),
            "carpool_share": safe_divide(carpool, commute_total),
            "transit_share": safe_divide(transit, commute_total),
            "bicycle_share": safe_divide(bicycle, commute_total),
            "walk_share": safe_divide(walk, commute_total),
            "work_from_home_share": safe_divide(work_from_home, commute_total),
            "bachelors_plus_share": safe_divide(bachelors_plus, education_total),
        }
    return covariates


def build_precinct_covariates() -> list[dict[str, float | str | None]]:
    results = load_precinct_results()
    turnout = load_precinct_turnout()
    precinct_geometries = load_precinct_geometries()

    block_group_features = load_source_geometries(BLOCK_GROUP_LAYER_ID, precinct_geometries, "block_groups")
    block_features = load_source_geometries(BLOCK_LAYER_ID, precinct_geometries, "blocks")

    block_group_rows = fetch_acs_block_group_data()
    intersecting_block_group_geoids = {feature.geoid for feature in block_group_features}
    block_group_rows = {
        geoid: row for geoid, row in block_group_rows.items() if geoid in intersecting_block_group_geoids
    }

    tract_geoids = sorted({feature.geoid[:11] for feature in block_features})
    block_rows = fetch_pl_block_data(tract_geoids)
    intersecting_block_geoids = {feature.geoid for feature in block_features}
    block_rows = {geoid: row for geoid, row in block_rows.items() if geoid in intersecting_block_geoids}

    block_demographics = build_block_demographics(precinct_geometries, block_features, block_rows)
    acs_covariates = build_acs_covariates(precinct_geometries, block_group_features, block_group_rows)

    precinct_rows: list[dict[str, float | str | None]] = []
    for precinct_name in sorted(results):
        result = results[precinct_name]
        turnout_row = turnout[precinct_name]
        row: dict[str, float | str | None] = {
            "precinct": precinct_name,
            "ward": result.ward,
            "q1a_yes": result.q1a_yes,
            "q1a_no": result.q1a_no,
            "q1b_yes": result.q1b_yes,
            "q1b_no": result.q1b_no,
            "q1a_yes_pct": result.q1a_yes_pct,
            "q1b_yes_pct": result.q1b_yes_pct,
            "q1a_minus_q1b_yes_pct": result.q1a_minus_q1b_yes_pct,
            "registered_voters": turnout_row.registered_voters,
            "ballots_cast": turnout_row.ballots_cast,
            "turnout_pct": turnout_row.turnout_pct,
        }
        row.update(block_demographics[precinct_name])
        row.update(acs_covariates[precinct_name])
        precinct_rows.append(row)
    return precinct_rows


def compute_correlations(
    precinct_rows: list[dict[str, float | str | None]],
    variables: list[str] = ANALYSIS_VARIABLES,
    outcomes: dict[str, str] | None = None,
) -> list[CorrelationResult]:
    outcomes = outcomes or OUTCOME_LABELS
    correlations: list[CorrelationResult] = []
    for outcome in outcomes:
        for variable in variables:
            x_values: list[float] = []
            y_values: list[float] = []
            for row in precinct_rows:
                x_value = row.get(variable)
                y_value = row.get(outcome)
                if x_value is None or y_value is None:
                    continue
                x_values.append(float(x_value))
                y_values.append(float(y_value))

            if len(x_values) < 3:
                continue
            if len(set(round(value, 12) for value in x_values)) <= 1:
                continue
            if len(set(round(value, 12) for value in y_values)) <= 1:
                continue

            spearman = spearmanr(x_values, y_values)
            pearson = pearsonr(x_values, y_values)
            if math.isnan(spearman.statistic) or math.isnan(pearson.statistic):
                continue

            correlations.append(
                CorrelationResult(
                    variable=variable,
                    outcome=outcome,
                    spearman_rho=float(spearman.statistic),
                    spearman_pvalue=float(spearman.pvalue),
                    pearson_r=float(pearson.statistic),
                    pearson_pvalue=float(pearson.pvalue),
                    n=len(x_values),
                )
            )
    return correlations


def correlation_rows_for_outcome(
    correlations: list[CorrelationResult],
    outcome: str,
) -> list[CorrelationResult]:
    return sorted(
        [correlation for correlation in correlations if correlation.outcome == outcome],
        key=lambda item: (abs(item.spearman_rho), abs(item.pearson_r)),
        reverse=True,
    )


def weakest_correlations_for_outcome(
    correlations: list[CorrelationResult],
    outcome: str,
) -> list[CorrelationResult]:
    return sorted(
        [correlation for correlation in correlations if correlation.outcome == outcome],
        key=lambda item: (abs(item.spearman_rho), abs(item.pearson_r)),
    )


def format_analysis_value(variable: str, value: float | None) -> str:
    if value is None:
        return "n/a"
    style, decimals = REPORT_FIELD_SPECS[variable]
    if style == "pct":
        return f"{value * 100:.{decimals}f}%"
    if style == "currency":
        return f"${value:,.{decimals}f}"
    if style == "count":
        return f"{value:,.{decimals}f}" if decimals else f"{round(value):,}"
    return f"{value:,.{decimals}f}"


def summarize_variable_range(precinct_rows: list[dict[str, float | str | None]], variable: str) -> str:
    values = [float(row[variable]) for row in precinct_rows if row.get(variable) is not None]
    if not values:
        return "n/a"
    return f"{format_analysis_value(variable, min(values))} to {format_analysis_value(variable, max(values))}"


def describe_relationship(variable_label: str, outcome_label: str, spearman_rho: float) -> str:
    if spearman_rho >= 0:
        return f"Precincts with higher `{variable_label}` tended to have higher {outcome_label}."
    return f"Precincts with higher `{variable_label}` tended to have lower {outcome_label}."


def build_report(
    precinct_rows: list[dict[str, float | str | None]],
    correlations: list[CorrelationResult],
) -> str:
    q1a_mean = fmean(float(row["q1a_yes_pct"]) for row in precinct_rows)
    q1b_mean = fmean(float(row["q1b_yes_pct"]) for row in precinct_rows)
    turnout_mean = fmean(float(row["turnout_pct"]) for row in precinct_rows)

    lines = [
        "# Malden precinct vote-share correlation analysis",
        "",
        "This report compares March 31, 2026 precinct vote shares against estimated precinct covariates built from official Census geographies plus the repo's turnout PDF parser.",
        "",
        "## Dataset notes",
        f"- Precincts analyzed: {len(precinct_rows)}",
        "- Election outcomes: Q1A yes share, Q1B yes share, and the Q1A minus Q1B yes-share gap",
        f"- Average Q1A yes share: {q1a_mean * 100:.1f}%",
        f"- Average Q1B yes share: {q1b_mean * 100:.1f}%",
        f"- Average turnout: {turnout_mean * 100:.1f}%",
        "- Demographic and housing covariates are precinct estimates created by spatially intersecting precinct polygons with 2020 Census blocks and 2025-vintage TIGER/ACS block groups.",
        "- Distance to the nearest MBTA stop is measured as straight-line miles from each precinct's population-weighted block-overlap center, with precinct centroid fallback where no population-weighted center is available.",
        "- Literal Walk Score is not included here; the analysis uses public walkability proxies instead, especially transit share, walk share, no-car share, and density.",
        "- Foreign-born share is omitted from this version because the block-group API fields available in this workflow were not clean enough to trust.",
        "- Correlation is not causation, and with only 27 precincts these results should be treated as directional rather than definitive.",
        "",
    ]

    for outcome in OUTCOME_LABELS:
        ranked = correlation_rows_for_outcome(correlations, outcome)
        weakest = weakest_correlations_for_outcome(correlations, outcome)
        strongest_positive = [item for item in ranked if item.spearman_rho > 0][:5]
        strongest_negative = [item for item in ranked if item.spearman_rho < 0][:5]
        weakest_items = weakest[:5]

        lines.append(f"## {OUTCOME_LABELS[outcome]}")
        lines.append("")

        if strongest_positive:
            lines.append("### Strongest positive correlations")
            for item in strongest_positive:
                lines.append(
                    f"- `{VARIABLE_LABELS[item.variable]}`: Spearman {item.spearman_rho:+.3f}, "
                    f"Pearson {item.pearson_r:+.3f}, range {summarize_variable_range(precinct_rows, item.variable)}. "
                    f"{describe_relationship(VARIABLE_LABELS[item.variable], OUTCOME_LABELS[outcome], item.spearman_rho)}"
                )
            lines.append("")

        if strongest_negative:
            lines.append("### Strongest negative correlations")
            for item in strongest_negative:
                lines.append(
                    f"- `{VARIABLE_LABELS[item.variable]}`: Spearman {item.spearman_rho:+.3f}, "
                    f"Pearson {item.pearson_r:+.3f}, range {summarize_variable_range(precinct_rows, item.variable)}. "
                    f"{describe_relationship(VARIABLE_LABELS[item.variable], OUTCOME_LABELS[outcome], item.spearman_rho)}"
                )
            lines.append("")

        if weakest_items:
            lines.append("### Weak or near-zero correlations")
            for item in weakest_items:
                lines.append(
                    f"- `{VARIABLE_LABELS[item.variable]}`: Spearman {item.spearman_rho:+.3f}, "
                    f"Pearson {item.pearson_r:+.3f}, range {summarize_variable_range(precinct_rows, item.variable)}."
                )
            lines.append("")

    return "\n".join(lines).strip() + "\n"


def write_covariates_csv(
    precinct_rows: list[dict[str, float | str | None]],
    output_path: Path = COVARIATES_OUTPUT_PATH,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(precinct_rows[0].keys())
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(precinct_rows)


def write_report(
    report_text: str,
    output_path: Path = REPORT_OUTPUT_PATH,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_text, encoding="utf-8")


def main() -> None:
    precinct_rows = build_precinct_covariates()
    correlations = compute_correlations(precinct_rows)
    write_covariates_csv(precinct_rows)
    write_report(build_report(precinct_rows, correlations))
    print(f"Wrote {COVARIATES_OUTPUT_PATH}")
    print(f"Wrote {REPORT_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
