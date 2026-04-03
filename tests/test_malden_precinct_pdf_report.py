import fitz

from scripts.malden_precinct_analysis import CorrelationResult
from scripts.malden_precinct_pdf_report import (
    PAGE_HEIGHT,
    PAGE_WIDTH,
    ReportContext,
    build_summary_text,
    create_correlation_bar_chart,
    create_scatter_plot,
    render_analysis_page,
    render_correlation_overview_pages,
    render_conclusion_page,
    render_cover_page,
    render_example_graph_pages,
    write_pdf_from_images,
)


def make_context() -> ReportContext:
    precinct_rows = [
        {
            "precinct": "1-1",
            "q1a_yes_pct": 0.35,
            "q1b_yes_pct": 0.31,
            "q1a_minus_q1b_yes_pct": 0.04,
            "turnout_pct": 0.12,
            "transit_share": 0.10,
            "bachelors_plus_share": 0.30,
            "age_18_to_34_share": 0.25,
        },
        {
            "precinct": "1-2",
            "q1a_yes_pct": 0.48,
            "q1b_yes_pct": 0.43,
            "q1a_minus_q1b_yes_pct": 0.05,
            "turnout_pct": 0.18,
            "transit_share": 0.20,
            "bachelors_plus_share": 0.45,
            "age_18_to_34_share": 0.27,
        },
        {
            "precinct": "1-3",
            "q1a_yes_pct": 0.60,
            "q1b_yes_pct": 0.54,
            "q1a_minus_q1b_yes_pct": 0.06,
            "turnout_pct": 0.26,
            "transit_share": 0.32,
            "bachelors_plus_share": 0.58,
            "age_18_to_34_share": 0.26,
        },
    ]
    correlations = [
        CorrelationResult("transit_share", "q1a_yes_pct", 0.74, 0.0, 0.70, 0.0, 3),
        CorrelationResult("bachelors_plus_share", "q1a_yes_pct", 0.52, 0.0, 0.56, 0.0, 3),
        CorrelationResult("turnout_pct", "q1a_yes_pct", 0.28, 0.0, 0.22, 0.0, 3),
        CorrelationResult("carpool_share", "q1a_yes_pct", -0.53, 0.0, -0.58, 0.0, 3),
        CorrelationResult("hispanic_share_2020", "q1a_yes_pct", -0.45, 0.0, -0.40, 0.0, 3),
        CorrelationResult("age_18_to_34_share", "q1a_yes_pct", 0.01, 0.0, 0.12, 0.0, 3),
        CorrelationResult("male_share", "q1a_yes_pct", 0.08, 0.0, 0.08, 0.0, 3),
        CorrelationResult("median_age_estimate", "q1a_yes_pct", 0.04, 0.0, -0.06, 0.0, 3),
        CorrelationResult("transit_share", "q1b_yes_pct", 0.74, 0.0, 0.75, 0.0, 3),
        CorrelationResult("bachelors_plus_share", "q1b_yes_pct", 0.45, 0.0, 0.52, 0.0, 3),
        CorrelationResult("turnout_pct", "q1b_yes_pct", 0.26, 0.0, 0.24, 0.0, 3),
        CorrelationResult("carpool_share", "q1b_yes_pct", -0.47, 0.0, -0.55, 0.0, 3),
        CorrelationResult("under_18_share", "q1b_yes_pct", -0.46, 0.0, -0.28, 0.0, 3),
        CorrelationResult("age_18_to_34_share", "q1b_yes_pct", 0.03, 0.0, 0.08, 0.0, 3),
        CorrelationResult("male_share", "q1b_yes_pct", 0.06, 0.0, 0.05, 0.0, 3),
        CorrelationResult("median_age_estimate", "q1b_yes_pct", 0.05, 0.0, -0.02, 0.0, 3),
        CorrelationResult("bachelors_plus_share", "q1a_minus_q1b_yes_pct", 0.49, 0.0, 0.52, 0.0, 3),
        CorrelationResult("one_vehicle_share", "q1a_minus_q1b_yes_pct", 0.28, 0.0, 0.25, 0.0, 3),
        CorrelationResult("work_from_home_share", "q1a_minus_q1b_yes_pct", 0.21, 0.0, 0.31, 0.0, 3),
        CorrelationResult("walk_share", "q1a_minus_q1b_yes_pct", -0.41, 0.0, -0.33, 0.0, 3),
        CorrelationResult("carpool_share", "q1a_minus_q1b_yes_pct", -0.28, 0.0, -0.34, 0.0, 3),
        CorrelationResult("age_65_plus_share", "q1a_minus_q1b_yes_pct", 0.02, 0.0, -0.03, 0.0, 3),
    ]
    return ReportContext(precinct_rows=precinct_rows, correlations=correlations)


def test_build_summary_text_contains_core_sections():
    summary = build_summary_text(make_context())

    assert "goal is not to prove why people voted" in summary["intro"]
    assert len(summary["key_findings"]) >= 4
    assert len(summary["analysis_paragraphs"]) == 4


def test_chart_helpers_render_images(tmp_path):
    context = make_context()

    bar_chart = create_correlation_bar_chart(context.correlations, "q1a_yes_pct", tmp_path / "bars.png")
    full_bar_chart = create_correlation_bar_chart(
        context.correlations,
        "q1a_yes_pct",
        tmp_path / "all_bars.png",
        include_all_variables=True,
    )
    scatter = create_scatter_plot(
        context.precinct_rows,
        "transit_share",
        "q1a_yes_pct",
        "Transit share vs Q1A",
        "Synthetic test chart",
        tmp_path / "scatter.png",
    )

    assert bar_chart.size == (1080, 480)
    assert full_bar_chart.size[0] == 1080
    assert full_bar_chart.size[1] >= 480
    assert scatter.size == (540, 430)
    assert (tmp_path / "bars.png").exists()
    assert (tmp_path / "all_bars.png").exists()
    assert (tmp_path / "scatter.png").exists()


def test_page_renderers_and_pdf_writer(tmp_path):
    context = make_context()
    cover = render_cover_page(context)
    analysis = render_analysis_page(context)
    chart_pages, chart_paths = render_correlation_overview_pages(context, tmp_path / "charts")
    scatter_pages, scatter_paths = render_example_graph_pages(context, tmp_path / "charts")
    conclusion = render_conclusion_page(context)
    output_path = tmp_path / "report.pdf"

    write_pdf_from_images([cover, analysis, *chart_pages, *scatter_pages, conclusion], output_path)

    assert cover.size == (PAGE_WIDTH, PAGE_HEIGHT)
    assert analysis.size == (PAGE_WIDTH, PAGE_HEIGHT)
    assert all(page.size == (PAGE_WIDTH, PAGE_HEIGHT) for page in chart_pages)
    assert all(page.size == (PAGE_WIDTH, PAGE_HEIGHT) for page in scatter_pages)
    assert len(chart_paths) == 4
    assert len(scatter_paths) >= 1
    assert output_path.exists()
    assert output_path.stat().st_size > 0

    document = fitz.open(output_path)
    try:
        assert document.page_count == 2 + len(chart_pages) + len(scatter_pages) + 1
    finally:
        document.close()
