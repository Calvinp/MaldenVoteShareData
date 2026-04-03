from scripts.malden_turnout_graphs import (
    TURNOUT_PDF_PATH,
    aggregate_ward_turnout,
    build_turnout_legend,
    load_precinct_turnout,
    render_turnout_chart,
    render_turnout_map,
    turnout_color,
)


def test_load_precinct_turnout_known_values():
    turnout = load_precinct_turnout(TURNOUT_PDF_PATH)

    assert turnout["1-1"].registered_voters == 1318
    assert turnout["1-1"].ballots_cast == 107
    assert round(turnout["3-1A"].turnout_pct * 100, 1) == 33.6
    assert len(turnout) == 27


def test_aggregate_ward_turnout_known_values():
    ward_turnout = aggregate_ward_turnout(load_precinct_turnout(TURNOUT_PDF_PATH))
    ward_lookup = {item.ward: item for item in ward_turnout}

    assert ward_lookup["3"].registered_voters == 5241
    assert ward_lookup["3"].ballots_cast == 1179
    assert round(ward_lookup["3"].turnout_pct * 100, 1) == 22.5
    assert sum(item.registered_voters for item in ward_turnout) == 38432
    assert sum(item.ballots_cast for item in ward_turnout) == 5796


def test_render_turnout_chart_writes_png(tmp_path):
    ward_turnout = aggregate_ward_turnout(load_precinct_turnout(TURNOUT_PDF_PATH))
    output_path = tmp_path / "turnout.png"

    render_turnout_chart("Question 1A", ward_turnout, output_path)

    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_turnout_color_and_legend():
    assert turnout_color(0.05) == (219, 234, 254)
    assert turnout_color(0.15) == (96, 165, 250)
    assert turnout_color(0.25) == (29, 78, 216)
    assert turnout_color(0.35) == (30, 64, 175)

    legend = build_turnout_legend()
    assert legend.title == "Turnout"
    assert [label for label, _ in legend.items] == ["5%", "15%", "25%", "35%"]


def test_render_turnout_map_writes_png_and_svg(tmp_path):
    output_stem = tmp_path / "turnout_map"

    render_turnout_map(load_precinct_turnout(TURNOUT_PDF_PATH), output_stem=output_stem)

    assert output_stem.with_suffix(".png").exists()
    assert output_stem.with_suffix(".svg").exists()
    assert output_stem.with_suffix(".png").stat().st_size > 0
    assert output_stem.with_suffix(".svg").stat().st_size > 0
