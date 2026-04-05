import pytest
from shapely.geometry import Polygon

from scripts.malden_precinct_analysis import (
    GeographyFeature,
    build_acs_covariates,
    build_block_demographics,
    build_overlap_lookup,
    build_report,
    compute_precinct_historical_partisan_baselines,
    compute_correlations,
    parse_census_api_table,
    weighted_average,
)


def make_square(left: float, bottom: float, right: float, top: float) -> Polygon:
    return Polygon(
        [
            (left, bottom),
            (right, bottom),
            (right, top),
            (left, top),
        ]
    )


def test_parse_census_api_table_builds_geoids():
    table = [
        ["NAME", "B19013_001E", "state", "county", "tract", "block group"],
        ["Block Group 1", "80000", "25", "017", "341600", "2"],
        ["Block Group 2", "90000", "25", "017", "341700", "1"],
    ]

    parsed = parse_census_api_table(table, ["state", "county", "tract", "block group"])

    assert parsed["250173416002"]["B19013_001E"] == 80000.0
    assert parsed["250173417001"]["B19013_001E"] == 90000.0


def test_weighted_average_handles_empty_and_weighted_inputs():
    assert weighted_average([]) is None
    assert weighted_average([(10.0, 1.0), (20.0, 3.0)]) == pytest.approx(17.5)


def test_build_overlap_lookup_splits_source_geometry():
    precincts = {
        "left": make_square(0.0, 0.0, 1.0, 1.0),
        "right": make_square(1.0, 0.0, 2.0, 1.0),
    }
    features = [GeographyFeature("source", make_square(0.0, 0.0, 2.0, 1.0), 1.0)]

    overlaps = build_overlap_lookup(precincts, features)

    assert overlaps["left"]["source"] == pytest.approx(0.5)
    assert overlaps["right"]["source"] == pytest.approx(0.5)


def test_build_block_demographics_computes_precinct_shares():
    precincts = {
        "1-1": make_square(-71.07511, 42.425632, -71.07311, 42.427632),
    }
    features = [GeographyFeature("block1", make_square(-71.07511, 42.425632, -71.07311, 42.427632), 1000.0)]
    rows = {
        "block1": {
            "P1_001N": 100.0,
            "P1_003N": 50.0,
            "P1_004N": 20.0,
            "P1_006N": 10.0,
            "P1_009N": 20.0,
            "P2_002N": 30.0,
        }
    }

    demographics = build_block_demographics(precincts, features, rows)["1-1"]

    assert demographics["population_2020"] == 100.0
    assert demographics["white_share_2020"] == pytest.approx(0.5)
    assert demographics["black_share_2020"] == pytest.approx(0.2)
    assert demographics["asian_share_2020"] == pytest.approx(0.1)
    assert demographics["multiracial_share_2020"] == pytest.approx(0.2)
    assert demographics["hispanic_share_2020"] == pytest.approx(0.3)
    assert demographics["precinct_area_sq_miles"] > 0
    assert demographics["population_density_per_sq_mile"] > 0
    assert demographics["population_center_latitude"] == pytest.approx(42.426632)
    assert demographics["population_center_longitude"] == pytest.approx(-71.07411)
    assert demographics["population_center_source"] == "population_weighted_block_centroid"
    assert demographics["nearest_mbta_stop"] == "Malden Center"
    assert demographics["nearest_mbta_stop_distance_miles"] == pytest.approx(0.0, abs=1e-8)


def test_build_block_demographics_falls_back_to_geographic_centroid_when_population_center_unavailable():
    precincts = {
        "1-2": make_square(-71.072097, 42.43568, -71.070097, 42.43768),
    }
    features = [GeographyFeature("block1", make_square(-71.072097, 42.43568, -71.070097, 42.43768), 1000.0)]
    rows = {
        "block1": {
            "P1_001N": 0.0,
            "P1_003N": 0.0,
            "P1_004N": 0.0,
            "P1_006N": 0.0,
            "P1_009N": 0.0,
            "P2_002N": 0.0,
        }
    }

    demographics = build_block_demographics(precincts, features, rows)["1-2"]

    assert demographics["population_center_latitude"] == pytest.approx(42.43668)
    assert demographics["population_center_longitude"] == pytest.approx(-71.071097)
    assert demographics["population_center_source"] == "geographic_centroid"
    assert demographics["nearest_mbta_stop"] == "Oak Grove"
    assert demographics["nearest_mbta_stop_distance_miles"] == pytest.approx(0.0, abs=1e-8)


def test_build_acs_covariates_derives_expected_shares_and_medians():
    precincts = {
        "1-1": make_square(-71.06, 42.42, -71.05, 42.43),
    }
    features = [GeographyFeature("bg1", make_square(-71.06, 42.42, -71.05, 42.43), 1000.0)]
    rows = {
        "bg1": {
            "B01001_001E": 100.0,
            "B01001_002E": 48.0,
            "B01001_003E": 4.0,
            "B01001_004E": 3.0,
            "B01001_005E": 2.0,
            "B01001_006E": 1.0,
            "B01001_027E": 4.0,
            "B01001_028E": 3.0,
            "B01001_029E": 2.0,
            "B01001_030E": 1.0,
            "B01001_007E": 2.0,
            "B01001_008E": 1.0,
            "B01001_009E": 1.0,
            "B01001_010E": 3.0,
            "B01001_011E": 4.0,
            "B01001_012E": 4.0,
            "B01001_031E": 2.0,
            "B01001_032E": 1.0,
            "B01001_033E": 1.0,
            "B01001_034E": 3.0,
            "B01001_035E": 5.0,
            "B01001_036E": 3.0,
            "B01001_013E": 4.0,
            "B01001_014E": 4.0,
            "B01001_015E": 4.0,
            "B01001_016E": 3.0,
            "B01001_017E": 2.0,
            "B01001_018E": 1.0,
            "B01001_019E": 2.0,
            "B01001_037E": 4.0,
            "B01001_038E": 3.0,
            "B01001_039E": 3.0,
            "B01001_040E": 1.0,
            "B01001_041E": 1.0,
            "B01001_042E": 1.0,
            "B01001_043E": 2.0,
            "B01001_020E": 1.0,
            "B01001_021E": 1.0,
            "B01001_022E": 1.0,
            "B01001_023E": 1.0,
            "B01001_024E": 1.0,
            "B01001_025E": 0.0,
            "B01001_044E": 3.0,
            "B01001_045E": 2.0,
            "B01001_046E": 2.0,
            "B01001_047E": 1.0,
            "B01001_048E": 1.0,
            "B01001_049E": 1.0,
            "B01002_001E": 40.0,
            "B08301_001E": 40.0,
            "B08301_003E": 20.0,
            "B08301_004E": 5.0,
            "B08301_010E": 7.0,
            "B08301_018E": 1.0,
            "B08301_019E": 4.0,
            "B08301_021E": 3.0,
            "B15003_001E": 60.0,
            "B15003_022E": 10.0,
            "B15003_023E": 5.0,
            "B15003_024E": 2.0,
            "B15003_025E": 1.0,
            "B19013_001E": 90000.0,
            "B25003_001E": 50.0,
            "B25003_002E": 20.0,
            "B25003_003E": 30.0,
            "B25044_001E": 50.0,
            "B25044_003E": 4.0,
            "B25044_004E": 8.0,
            "B25044_006E": 3.0,
            "B25044_007E": 1.0,
            "B25044_010E": 6.0,
            "B25044_011E": 12.0,
            "B25044_013E": 5.0,
            "B25044_014E": 1.0,
            "B25064_001E": 2000.0,
        }
    }

    covariates = build_acs_covariates(precincts, features, rows)["1-1"]

    assert covariates["male_share"] == pytest.approx(0.48)
    assert covariates["under_18_share"] == pytest.approx(0.2)
    assert covariates["age_18_to_34_share"] == pytest.approx(0.3)
    assert covariates["age_35_to_64_share"] == pytest.approx(0.35)
    assert covariates["age_65_plus_share"] == pytest.approx(0.15)
    assert covariates["adult_share"] == pytest.approx(0.8)
    assert covariates["median_age_estimate"] == pytest.approx(40.0)
    assert covariates["median_household_income_estimate"] == pytest.approx(90000.0)
    assert covariates["owner_share"] == pytest.approx(0.4)
    assert covariates["renter_share"] == pytest.approx(0.6)
    assert covariates["median_gross_rent_estimate"] == pytest.approx(2000.0)
    assert covariates["no_vehicle_share"] == pytest.approx(0.2)
    assert covariates["one_vehicle_share"] == pytest.approx(0.4)
    assert covariates["three_plus_vehicle_share"] == pytest.approx(0.2)
    assert covariates["transit_share"] == pytest.approx(0.175)
    assert covariates["walk_share"] == pytest.approx(0.1)
    assert covariates["work_from_home_share"] == pytest.approx(0.075)
    assert covariates["bachelors_plus_share"] == pytest.approx(0.3)


def test_build_acs_covariates_accumulates_vehicle_denominator_across_sources():
    precincts = {
        "1-1": make_square(0.0, 0.0, 2.0, 1.0),
    }
    features = [
        GeographyFeature("bg1", make_square(0.0, 0.0, 1.0, 1.0), 1000.0),
        GeographyFeature("bg2", make_square(1.0, 0.0, 2.0, 1.0), 1000.0),
    ]
    rows = {
        "bg1": {
            "B25044_001E": 50.0,
            "B25044_003E": 10.0,
            "B25044_004E": 20.0,
            "B25044_006E": 5.0,
            "B25044_007E": 5.0,
            "B25044_010E": 0.0,
            "B25044_011E": 0.0,
            "B25044_013E": 0.0,
            "B25044_014E": 0.0,
        },
        "bg2": {
            "B25044_001E": 50.0,
            "B25044_003E": 0.0,
            "B25044_004E": 10.0,
            "B25044_006E": 0.0,
            "B25044_007E": 0.0,
            "B25044_010E": 0.0,
            "B25044_011E": 20.0,
            "B25044_013E": 10.0,
            "B25044_014E": 0.0,
        },
    }

    covariates = build_acs_covariates(precincts, features, rows)["1-1"]

    assert covariates["no_vehicle_share"] == pytest.approx(0.1)
    assert covariates["one_vehicle_share"] == pytest.approx(0.5)
    assert covariates["three_plus_vehicle_share"] == pytest.approx(0.2)


def test_compute_precinct_historical_partisan_baselines_uses_only_democratic_republican_contests():
    rows = [
        {
            "election_key": "2022",
            "contest_slug": "governor",
            "candidate_party": "Democratic",
            "precinct": "1-1",
            "votes": "60",
        },
        {
            "election_key": "2022",
            "contest_slug": "governor",
            "candidate_party": "Republican",
            "precinct": "1-1",
            "votes": "40",
        },
        {
            "election_key": "2022",
            "contest_slug": "auditor",
            "candidate_party": "Democratic",
            "precinct": "1-1",
            "votes": "50",
        },
        {
            "election_key": "2022",
            "contest_slug": "auditor",
            "candidate_party": "Republican",
            "precinct": "1-1",
            "votes": "30",
        },
        {
            "election_key": "2022",
            "contest_slug": "auditor",
            "candidate_party": "Green-Rainbow Party",
            "precinct": "1-1",
            "votes": "20",
        },
        {
            "election_key": "2024",
            "contest_slug": "senate",
            "candidate_party": "Democratic",
            "precinct": "1-1",
            "votes": "35",
        },
        {
            "election_key": "2024",
            "contest_slug": "senate",
            "candidate_party": "Republican",
            "precinct": "1-1",
            "votes": "65",
        },
        {
            "election_key": "2024",
            "contest_slug": "register_of_deeds",
            "candidate_party": "Democratic",
            "precinct": "1-1",
            "votes": "80",
        },
        {
            "election_key": "2024",
            "contest_slug": "register_of_deeds",
            "candidate_party": "Independent",
            "precinct": "1-1",
            "votes": "20",
        },
        {
            "election_key": "2022",
            "contest_slug": "governor",
            "candidate_party": "Democratic",
            "precinct": "1-2",
            "votes": "25",
        },
        {
            "election_key": "2022",
            "contest_slug": "governor",
            "candidate_party": "Republican",
            "precinct": "1-2",
            "votes": "75",
        },
        {
            "election_key": "2022",
            "contest_slug": "auditor",
            "candidate_party": "Democratic",
            "precinct": "1-2",
            "votes": "45",
        },
        {
            "election_key": "2022",
            "contest_slug": "auditor",
            "candidate_party": "Republican",
            "precinct": "1-2",
            "votes": "55",
        },
        {
            "election_key": "2024",
            "contest_slug": "senate",
            "candidate_party": "Democratic",
            "precinct": "1-2",
            "votes": "90",
        },
        {
            "election_key": "2024",
            "contest_slug": "senate",
            "candidate_party": "Republican",
            "precinct": "1-2",
            "votes": "10",
        },
    ]

    baselines = compute_precinct_historical_partisan_baselines(rows)

    assert baselines["1-1"]["mean_dr_vote_share_2022_2024"] == pytest.approx(0.05)
    assert baselines["1-1"]["median_dr_vote_share_2022_2024"] == pytest.approx(0.20)
    assert baselines["1-2"]["mean_dr_vote_share_2022_2024"] == pytest.approx((0.20) / 3.0)
    assert baselines["1-2"]["median_dr_vote_share_2022_2024"] == pytest.approx(-0.10)


def test_compute_correlations_and_report_surface_rankings():
    rows = [
        {
            "precinct": "1-1",
            "q1a_yes_pct": 0.30,
            "q1b_yes_pct": 0.25,
            "q1a_minus_q1b_yes_pct": 0.05,
            "turnout_pct": 0.10,
            "registered_voters": 100.0,
            "ballots_cast": 10.0,
            "population_2020": 1000.0,
            "precinct_area_sq_miles": 0.25,
            "population_density_per_sq_mile": 4000.0,
            "nearest_mbta_stop_distance_miles": 1.2,
            "renter_share": 0.70,
            "owner_share": 0.30,
            "walk_share": 0.05,
        },
        {
            "precinct": "1-2",
            "q1a_yes_pct": 0.40,
            "q1b_yes_pct": 0.35,
            "q1a_minus_q1b_yes_pct": 0.05,
            "turnout_pct": 0.20,
            "registered_voters": 200.0,
            "ballots_cast": 40.0,
            "population_2020": 1100.0,
            "precinct_area_sq_miles": 0.25,
            "population_density_per_sq_mile": 4400.0,
            "nearest_mbta_stop_distance_miles": 0.8,
            "renter_share": 0.50,
            "owner_share": 0.50,
            "walk_share": 0.10,
        },
        {
            "precinct": "1-3",
            "q1a_yes_pct": 0.50,
            "q1b_yes_pct": 0.45,
            "q1a_minus_q1b_yes_pct": 0.05,
            "turnout_pct": 0.30,
            "registered_voters": 300.0,
            "ballots_cast": 90.0,
            "population_2020": 1200.0,
            "precinct_area_sq_miles": 0.25,
            "population_density_per_sq_mile": 4800.0,
            "nearest_mbta_stop_distance_miles": 0.4,
            "renter_share": 0.30,
            "owner_share": 0.70,
            "walk_share": 0.15,
        },
    ]

    correlations = compute_correlations(
        rows,
        ["turnout_pct", "renter_share", "walk_share", "nearest_mbta_stop_distance_miles"],
    )
    turnout_q1a = next(
        item for item in correlations if item.variable == "turnout_pct" and item.outcome == "q1a_yes_pct"
    )
    renter_q1a = next(
        item for item in correlations if item.variable == "renter_share" and item.outcome == "q1a_yes_pct"
    )
    mbta_distance_q1a = next(
        item
        for item in correlations
        if item.variable == "nearest_mbta_stop_distance_miles" and item.outcome == "q1a_yes_pct"
    )
    report = build_report(rows, correlations)

    assert turnout_q1a.spearman_rho == pytest.approx(1.0)
    assert renter_q1a.spearman_rho == pytest.approx(-1.0)
    assert mbta_distance_q1a.spearman_rho == pytest.approx(-1.0)
    assert "Strongest positive correlations" in report
    assert "`Turnout %`" in report
    assert "`Renter share`" in report
    assert "`Distance to nearest MBTA stop (mi)`" in report
