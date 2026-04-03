from scripts.malden_override_map import (
    PRECINCTS_PATH,
    WORKBOOK_PATH,
    interpolate_color,
    interpolate_difference_color,
    load_precinct_geometries,
    load_precinct_results,
    validate_join,
)


def test_load_precinct_results_known_values():
    results = load_precinct_results(WORKBOOK_PATH)

    assert round(results["4-2"].q1a_yes_pct * 100, 1) == 75.7
    assert round(results["6-3"].q1b_yes_pct * 100, 1) == 28.3
    assert "3-1A" in results
    assert "5-3A" in results
    assert "7-3A" in results


def test_geometry_join_matches_workbook():
    results = load_precinct_results(WORKBOOK_PATH)
    geometries = load_precinct_geometries(PRECINCTS_PATH)
    missing, extra = validate_join(results, geometries)

    assert missing == []
    assert extra == []
    assert len(geometries) == 27


def test_interpolate_color_hits_expected_stops():
    assert interpolate_color(0.25) == (202, 0, 32)
    assert interpolate_color(0.50) == (247, 247, 247)
    assert interpolate_color(0.75) == (5, 113, 176)


def test_interpolate_color_clamps_and_blends():
    assert interpolate_color(0.10) == (202, 0, 32)
    assert interpolate_color(0.90) == (5, 113, 176)
    assert interpolate_color(0.40) == (229, 148, 161)


def test_difference_color_scale_and_known_gap():
    results = load_precinct_results(WORKBOOK_PATH)

    assert round((results["4-2"].q1a_minus_q1b_yes_pct) * 100, 1) == 9.7
    assert interpolate_difference_color(-0.10) == (59, 130, 246)
    assert interpolate_difference_color(0.00) == (245, 245, 235)
    assert interpolate_difference_color(0.10) == (217, 119, 6)
