from __future__ import annotations

import io
import math
import os
import zlib
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean

import fitz
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.stats import spearmanr

try:
    from scripts.malden_precinct_analysis import (
        OUTPUT_DIR,
        ANALYSIS_VARIABLES,
        OUTCOME_LABELS,
    REPORT_FIELD_SPECS,
    VARIABLE_LABELS,
        CorrelationResult,
        build_precinct_covariates,
        compute_correlations,
        correlation_rows_for_outcome,
        weakest_correlations_for_outcome,
    )
    from scripts.malden_turnout_graphs import TURNOUT_PDF_URL
except ModuleNotFoundError:
    from malden_precinct_analysis import (  # type: ignore
        OUTPUT_DIR,
        ANALYSIS_VARIABLES,
        OUTCOME_LABELS,
    REPORT_FIELD_SPECS,
    VARIABLE_LABELS,
        CorrelationResult,
        build_precinct_covariates,
        compute_correlations,
        correlation_rows_for_outcome,
        weakest_correlations_for_outcome,
    )
    from malden_turnout_graphs import TURNOUT_PDF_URL  # type: ignore


PDF_REPORT_OUTPUT_PATH = OUTPUT_DIR / "malden_vote_correlation_report_human.pdf"
CHART_OUTPUT_DIR = OUTPUT_DIR / "malden_vote_correlation_report_charts"
PAGE_WIDTH = 1275
PAGE_HEIGHT = 1650
PAGE_MARGIN = 90
TEXT_COLOR = (30, 34, 41)
MUTED_TEXT_COLOR = (92, 99, 112)
BLUE = (23, 92, 211)
ORANGE = (211, 118, 23)
GREEN = (31, 142, 84)
LIGHT_BLUE = (231, 241, 255)
LIGHT_ORANGE = (255, 239, 225)
LIGHT_GREEN = (230, 246, 237)
GRID = (222, 226, 232)
HEADER_LINE = (210, 214, 220)
TURNOUT_OUTCOME_LABEL = "Turnout %"
BOOTSTRAP_ITERATIONS = 400

CHART_VARIABLE_LABELS = {
    "median_household_income_estimate": "Median household income",
    "median_gross_rent_estimate": "Median gross rent",
}

DIRECT_VARIABLES = {
    "registered_voters",
    "turnout_pct",
    "precinct_area_sq_miles",
}

BLOCK_LEVEL_VARIABLES = {
    "population_density_per_sq_mile",
    "nearest_mbta_stop_distance_miles",
    "white_share_2020",
    "black_share_2020",
    "asian_share_2020",
    "multiracial_share_2020",
    "hispanic_share_2020",
}

BLOCK_GROUP_VARIABLES = set(ANALYSIS_VARIABLES) - DIRECT_VARIABLES - BLOCK_LEVEL_VARIABLES

WEB_SOURCE_ENTRIES = [
    (
        "City of Malden Election Results page",
        "https://www.cityofmalden.org/198/Election-Results",
        "Public index page for Malden election-result documents and archived results.",
    ),
    (
        "City of Malden unofficial March 31, 2026 results PDF",
        TURNOUT_PDF_URL,
        "Used for precinct-level Q1A and Q1B vote totals, registered voters, ballots cast, and turnout calculations.",
    ),
    (
        "City of Malden Geographic Information Systems page",
        "https://www.cityofmalden.org/214/Geographic-Information-Systems",
        "Public GIS landing page that links to Malden's official parcel viewer and ward/precinct reference map.",
    ),
    (
        "City of Malden Ward and Precinct 2020 Map PDF",
        "https://www.cityofmalden.org/DocumentCenter/View/4895/Ward-and-Precinct-2020-Map",
        "Official precinct-boundary reference map used to validate the precinct geometry export and labels.",
    ),
    (
        "Malden GIS Parcel Viewer",
        "https://maldenma.mapgeo.io/",
        "Public municipal GIS viewer used as the online source for official precinct-boundary context.",
    ),
    (
        "U.S. Census Bureau 2024 ACS 5-year API",
        "https://api.census.gov/data/2024/acs/acs5",
        "Used for age, sex, income, tenure, rent, commute, vehicles, and education variables.",
    ),
    (
        "U.S. Census Bureau 2020 Decennial PL API",
        "https://api.census.gov/data/2020/dec/pl",
        "Used for block-level race and Hispanic-share estimates.",
    ),
    (
        "U.S. Census Bureau TIGERweb Tracts/Blocks service",
        "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Tracts_Blocks/MapServer",
        "Used for Census block and block-group geometry intersections with precinct polygons.",
    ),
    (
        "MBTA V3 stops API",
        "https://api-v3.mbta.com/docs/swagger/index.html",
        "Used to verify the parent-station coordinates for Malden Center, Oak Grove, and Wellington when computing nearest-stop distance.",
    ),
]


@dataclass(frozen=True)
class ReportContext:
    precinct_rows: list[dict[str, float | str | None]]
    correlations: list[CorrelationResult]


@dataclass(frozen=True)
class CorrelationUncertainty:
    lower: float
    upper: float
    bootstrap_lower: float
    bootstrap_upper: float
    nonzero_count: int
    sample_count: int
    source_tier: str


def symmetric_uncertainty_half_width(
    correlation: CorrelationResult,
    uncertainty: CorrelationUncertainty,
) -> float:
    return max(
        abs(correlation.spearman_rho - uncertainty.lower),
        abs(uncertainty.upper - correlation.spearman_rho),
    )


def load_font(size: int, *, bold: bool = False, serif: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_dirs: list[Path] = []
    for env_var in ("WINDIR", "SystemRoot"):
        base_dir = os.environ.get(env_var)
        if not base_dir:
            continue
        font_dir = Path(base_dir) / "Fonts"
        if font_dir not in font_dirs:
            font_dirs.append(font_dir)
    if serif:
        candidates = [
            font_dir / ("georgiab.ttf" if bold else "georgia.ttf")
            for font_dir in font_dirs
        ] + [
            font_dir / ("timesbd.ttf" if bold else "times.ttf")
            for font_dir in font_dirs
        ]
    else:
        candidates = [
            font_dir / ("arialbd.ttf" if bold else "arial.ttf")
            for font_dir in font_dirs
        ] + [
            font_dir / ("Arialbd.ttf" if bold else "Arial.ttf")
            for font_dir in font_dirs
        ] + [
            font_dir / ("segoeuib.ttf" if bold else "segoeui.ttf")
            for font_dir in font_dirs
        ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    x: int,
    y: int,
    max_width: int,
    *,
    fill: tuple[int, int, int] = TEXT_COLOR,
    line_gap: int = 10,
) -> int:
    for paragraph in text.split("\n"):
        lines = wrap_text(draw, paragraph, font, max_width)
        for line in lines:
            draw.text((x, y), line, font=font, fill=fill)
            y += font.size + line_gap
        y += line_gap
    return y


def draw_bullet_list(
    draw: ImageDraw.ImageDraw,
    items: list[str],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    x: int,
    y: int,
    max_width: int,
) -> int:
    bullet_indent = 24
    text_x = x + bullet_indent
    for item in items:
        draw.ellipse((x, y + 14, x + 8, y + 22), fill=BLUE)
        y = draw_wrapped_text(draw, item, font, text_x, y, max_width - bullet_indent, line_gap=8)
        y += 6
    return y


def format_value_for_axis(style_key: str, value: float) -> str:
    style, decimals = REPORT_FIELD_SPECS.get(style_key, ("decimal", 1))
    if style == "pct":
        return f"{value * 100:.0f}%"
    if style == "currency":
        if abs(value) >= 1000:
            return f"${value/1000:.0f}k"
        return f"${value:.0f}"
    if style == "count":
        if abs(value) >= 1000:
            return f"{value/1000:.1f}k"
        return f"{value:.0f}"
    return f"{value:.1f}"


def strongest_with_sign(
    correlations: list[CorrelationResult],
    outcome: str,
    *,
    positive: bool,
    limit: int,
) -> list[CorrelationResult]:
    ranked = correlation_rows_for_outcome(correlations, outcome)
    return [item for item in ranked if (item.spearman_rho > 0) == positive][:limit]


def correlation_for_variable(
    correlations: list[CorrelationResult],
    variable: str,
    outcome: str,
) -> CorrelationResult | None:
    for item in correlations:
        if item.variable == variable and item.outcome == outcome:
            return item
    return None


def best_outcome_for_variable(
    correlations: list[CorrelationResult],
    variable: str,
) -> str | None:
    matches = [item for item in correlations if item.variable == variable]
    if not matches:
        return None
    return max(matches, key=lambda item: abs(item.spearman_rho)).outcome


def ordered_variables(context: ReportContext) -> list[str]:
    present = {item.variable for item in context.correlations}
    ordered = [variable for variable in VARIABLE_LABELS if variable in present]
    return ordered


def has_plot_data(
    precinct_rows: list[dict[str, float | str | None]],
    x_key: str,
    y_key: str,
) -> bool:
    points = [
        (row.get(x_key), row.get(y_key))
        for row in precinct_rows
        if row.get(x_key) is not None and row.get(y_key) is not None
    ]
    if len(points) < 3:
        return False
    x_values = {round(float(point[0]), 12) for point in points}
    y_values = {round(float(point[1]), 12) for point in points}
    return len(x_values) > 1 and len(y_values) > 1


def example_graph_variables(context: ReportContext) -> list[str]:
    ranked_q1a = correlation_rows_for_outcome(context.correlations, "q1a_yes_pct")
    return [
        item.variable
        for item in ranked_q1a
        if has_plot_data(context.precinct_rows, item.variable, "q1a_yes_pct")
    ]


def build_summary_text(context: ReportContext) -> dict[str, object]:
    q1a_top = strongest_with_sign(context.correlations, "q1a_yes_pct", positive=True, limit=2)
    q1a_bottom = strongest_with_sign(context.correlations, "q1a_yes_pct", positive=False, limit=2)
    q1b_top = strongest_with_sign(context.correlations, "q1b_yes_pct", positive=True, limit=2)
    gap_top = strongest_with_sign(context.correlations, "q1a_minus_q1b_yes_pct", positive=True, limit=2)
    q1a_weak = weakest_correlations_for_outcome(context.correlations, "q1a_yes_pct")[:3]
    avg_q1a = fmean(float(row["q1a_yes_pct"]) for row in context.precinct_rows)
    avg_q1b = fmean(float(row["q1b_yes_pct"]) for row in context.precinct_rows)
    avg_turnout = fmean(float(row["turnout_pct"]) for row in context.precinct_rows)

    intro_paragraph = (
        "This report summarizes a precinct-level correlation analysis of Malden's March 31, 2026 special election "
        "for Questions 1A and 1B. The goal is not to prove why people voted the way they did, but to show which "
        "precinct characteristics tended to move together with support for the two questions."
    )
    method_paragraph = (
        "Each precinct was matched to official Census blocks and block groups, then estimated demographic and housing "
        "measures were compared against Q1A yes share, Q1B yes share, and the Q1A minus Q1B gap. The main score used "
        "here is Spearman correlation: values closer to +1 or -1 indicate a stronger relationship, while values near 0 "
        "indicate little obvious relationship."
    )
    key_findings = [
        f"Across both ballot questions, `{VARIABLE_LABELS[q1a_top[0].variable]}` was the clearest positive correlate of yes vote share.",
        f"`{VARIABLE_LABELS[q1a_bottom[0].variable]}` and `{VARIABLE_LABELS[q1a_bottom[1].variable]}` were among the clearest negative correlates of Q1A support.",
        f"The Q1A-Q1B gap was most associated with `{VARIABLE_LABELS[gap_top[0].variable]}` and `{VARIABLE_LABELS[gap_top[1].variable]}`.",
        f"`{VARIABLE_LABELS[q1a_weak[0].variable]}` and `{VARIABLE_LABELS[q1a_weak[1].variable]}` were close to non-correlated with Q1A support.",
        f"Turnout averaged {avg_turnout * 100:.1f}% citywide and showed only a mild positive relationship with support, not a dominant one.",
    ]
    analysis_paragraphs = [
        (
            f"Support for both questions was higher in precincts with more `{VARIABLE_LABELS[q1a_top[0].variable].lower()}` "
            f"and more `{VARIABLE_LABELS[q1a_top[1].variable].lower()}`. That does not mean those traits caused support, "
            "but it does suggest the city's more transit-oriented, college-educated areas were generally friendlier terrain for yes votes."
        ),
        (
            f"On the other side, Q1A and Q1B tended to run weaker in precincts with more `{VARIABLE_LABELS[q1a_bottom[0].variable].lower()}`, "
            f"`{VARIABLE_LABELS[q1a_bottom[1].variable].lower()}`, and higher shares of children or racial groups that were negatively correlated in this dataset. "
            "The practical read is that support was not evenly distributed across neighborhood types."
        ),
        (
            f"The difference between Q1A and Q1B was smaller than the difference between yes and no overall, but it still had a pattern: "
            f"Q1A ran relatively better in precincts with more `{VARIABLE_LABELS[gap_top[0].variable].lower()}` and `{VARIABLE_LABELS[gap_top[1].variable].lower()}`."
        ),
        (
            f"Several variables did not do much by themselves. `{VARIABLE_LABELS[q1a_weak[0].variable]}`, "
            f"`{VARIABLE_LABELS[q1a_weak[1].variable]}`, and `{VARIABLE_LABELS[q1a_weak[2].variable]}` all sat close to zero, "
            "which is a useful reminder that not every intuitive story shows up in the data."
        ),
    ]
    conclusion_bullets = [
        "The strongest recurring story is geographic and lifestyle related: transit-oriented, highly educated precincts were more supportive.",
        "Turnout mattered some, but much less than the strongest neighborhood-composition variables.",
        "Q1A and Q1B largely moved together; the same broad precinct types tended to like or dislike both.",
        "This is still a small-precinct analysis. It is best used as a guide for pattern-spotting, not as proof of individual voter behavior.",
    ]

    return {
        "intro": intro_paragraph,
        "methods": method_paragraph,
        "key_findings": key_findings,
        "analysis_paragraphs": analysis_paragraphs,
        "conclusions": conclusion_bullets,
        "averages": (avg_q1a, avg_q1b, avg_turnout),
        "q1a_top": q1a_top,
        "q1a_bottom": q1a_bottom,
        "q1b_top": q1b_top,
    }


def make_base_page(title: str, subtitle: str) -> tuple[Image.Image, ImageDraw.ImageDraw, int]:
    image = Image.new("RGB", (PAGE_WIDTH, PAGE_HEIGHT), "white")
    draw = ImageDraw.Draw(image)
    title_font = load_font(44, bold=True, serif=True)
    subtitle_font = load_font(22)
    draw.text((PAGE_MARGIN, 52), title, font=title_font, fill=TEXT_COLOR)
    draw.text((PAGE_MARGIN, 112), subtitle, font=subtitle_font, fill=MUTED_TEXT_COLOR)
    draw.line((PAGE_MARGIN, 150, PAGE_WIDTH - PAGE_MARGIN, 150), fill=HEADER_LINE, width=3)
    return image, draw, 185


def variable_source_tier(variable: str) -> str:
    if variable in DIRECT_VARIABLES:
        return "direct"
    if variable in BLOCK_LEVEL_VARIABLES:
        return "block"
    return "block-group"


def chart_variable_label(variable: str) -> str:
    return CHART_VARIABLE_LABELS.get(variable, VARIABLE_LABELS[variable])


def source_uncertainty_factor(variable: str) -> float:
    tier = variable_source_tier(variable)
    if tier == "direct":
        return 1.0
    if tier == "block":
        return 1.05
    return 1.12


def sparsity_uncertainty_factor(nonzero_count: int, sample_count: int) -> float:
    if sample_count <= 0:
        return 1.0
    nonzero_fraction = nonzero_count / sample_count
    return 1.0 + max(0.0, (0.50 - nonzero_fraction) / 0.50) * 0.35


def bootstrap_seed(variable: str, outcome: str) -> int:
    return zlib.crc32(f"{variable}:{outcome}".encode("utf-8")) & 0xFFFFFFFF


def compute_correlation_uncertainty(
    precinct_rows: list[dict[str, float | str | None]],
    correlation: CorrelationResult,
    *,
    iterations: int = BOOTSTRAP_ITERATIONS,
) -> CorrelationUncertainty:
    pairs = [
        (float(row[correlation.variable]), float(row[correlation.outcome]))
        for row in precinct_rows
        if row.get(correlation.variable) is not None and row.get(correlation.outcome) is not None
    ]
    sample_count = len(pairs)
    nonzero_count = sum(1 for x_value, _ in pairs if abs(x_value) > 1e-12)
    source_tier = variable_source_tier(correlation.variable)
    if sample_count < 3:
        return CorrelationUncertainty(
            lower=correlation.spearman_rho,
            upper=correlation.spearman_rho,
            bootstrap_lower=correlation.spearman_rho,
            bootstrap_upper=correlation.spearman_rho,
            nonzero_count=nonzero_count,
            sample_count=sample_count,
            source_tier=source_tier,
        )

    values = np.array(pairs, dtype=float)
    rng = np.random.default_rng(bootstrap_seed(correlation.variable, correlation.outcome))
    estimates: list[float] = []
    for _ in range(iterations):
        sample_indices = rng.integers(0, sample_count, size=sample_count)
        sampled = values[sample_indices]
        x_values = sampled[:, 0]
        y_values = sampled[:, 1]
        if len({round(value, 12) for value in x_values}) <= 1:
            continue
        if len({round(value, 12) for value in y_values}) <= 1:
            continue
        statistic = float(spearmanr(x_values, y_values).statistic)
        if math.isnan(statistic):
            continue
        estimates.append(statistic)

    if estimates:
        bootstrap_lower = float(np.percentile(estimates, 2.5))
        bootstrap_upper = float(np.percentile(estimates, 97.5))
    else:
        bootstrap_lower = correlation.spearman_rho
        bootstrap_upper = correlation.spearman_rho

    inflation = source_uncertainty_factor(correlation.variable) * sparsity_uncertainty_factor(nonzero_count, sample_count)
    lower = correlation.spearman_rho - (correlation.spearman_rho - bootstrap_lower) * inflation
    upper = correlation.spearman_rho + (bootstrap_upper - correlation.spearman_rho) * inflation
    lower = max(-1.0, min(lower, correlation.spearman_rho))
    upper = min(1.0, max(upper, correlation.spearman_rho))

    return CorrelationUncertainty(
        lower=lower,
        upper=upper,
        bootstrap_lower=bootstrap_lower,
        bootstrap_upper=bootstrap_upper,
        nonzero_count=nonzero_count,
        sample_count=sample_count,
        source_tier=source_tier,
    )


def create_correlation_bar_chart(
    correlations: list[CorrelationResult],
    outcome: str,
    output_path: Path | None = None,
    *,
    precinct_rows: list[dict[str, float | str | None]] | None = None,
    width: int = 1080,
    height: int | None = None,
    include_all_variables: bool = False,
    outcome_label: str | None = None,
) -> Image.Image:
    ranked = correlation_rows_for_outcome(correlations, outcome)
    if include_all_variables:
        selected = sorted(ranked, key=lambda item: item.spearman_rho)
    else:
        strongest_positive = [item for item in ranked if item.spearman_rho > 0][:4]
        strongest_negative = [item for item in ranked if item.spearman_rho < 0][:4]
        selected = sorted(strongest_positive + strongest_negative, key=lambda item: item.spearman_rho)
    height = height or max(480, 150 + len(selected) * 34)

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font = load_font(28, bold=True)
    label_font = load_font(16)
    axis_font = load_font(16)
    outcome_label = outcome_label or OUTCOME_LABELS[outcome]
    chart_title = (
        f"All precinct-level correlations: {outcome_label}"
        if include_all_variables
        else f"Strongest precinct-level correlations: {outcome_label}"
    )
    draw.text((30, 20), chart_title, font=title_font, fill=TEXT_COLOR)
    subtitle = "Bars show Spearman correlation."
    if precinct_rows is not None:
        subtitle += " Blue means more support as the variable rises; orange means less. Whiskers show 95% uncertainty intervals widened modestly for coarser Census interpolation and sparse variables."
    else:
        subtitle += " Blue means more support as the variable rises; orange means less."
    draw.text((30, 58), subtitle, font=axis_font, fill=MUTED_TEXT_COLOR)

    variable_text_x = 30
    chart_top = 110
    chart_right = width - 70
    chart_bottom = height - 55

    value_font = load_font(14)
    label_padding = 18
    value_padding = 20
    base_value_text_x = 265 if include_all_variables else 225
    base_chart_left = 435 if include_all_variables else 365
    if selected:
        max_label_width = max(
            draw.textbbox((0, 0), chart_variable_label(item.variable), font=label_font)[2]
            for item in selected
        )
        if precinct_rows is not None:
            max_value_width = 0
            for item in selected:
                uncertainty = compute_correlation_uncertainty(precinct_rows, item)
                half_width = symmetric_uncertainty_half_width(item, uncertainty)
                value_label = f"{item.spearman_rho:+.2f} +/- {half_width:.2f}"
                value_width = draw.textbbox((0, 0), value_label, font=value_font)[2]
                max_value_width = max(max_value_width, value_width)
        else:
            max_value_width = max(
                draw.textbbox((0, 0), f"{item.spearman_rho:+.2f}", font=value_font)[2]
                for item in selected
            )
        value_text_x = max(base_value_text_x, variable_text_x + max_label_width + label_padding)
        chart_left = max(base_chart_left, value_text_x + max_value_width + value_padding)
        chart_left = min(chart_left, chart_right - 220)
    else:
        value_text_x = base_value_text_x
        chart_left = base_chart_left

    zero_x = chart_left + (chart_right - chart_left) / 2
    draw.line((zero_x, chart_top, zero_x, chart_bottom), fill=(150, 157, 166), width=2)

    for tick in [-0.75, -0.5, -0.25, 0.0, 0.25, 0.5, 0.75]:
        x = zero_x + tick * ((chart_right - chart_left) / 2)
        draw.line((x, chart_top, x, chart_bottom), fill=GRID, width=1)
        label = f"{tick:+.2f}" if tick else "0"
        bbox = draw.textbbox((0, 0), label, font=axis_font)
        draw.text((x - (bbox[2] - bbox[0]) / 2, chart_bottom + 8), label, font=axis_font, fill=MUTED_TEXT_COLOR)

    if selected:
        row_height = (chart_bottom - chart_top) / len(selected)
        for index, item in enumerate(selected):
            bar_center_y = chart_top + row_height * index + row_height / 2
            label = chart_variable_label(item.variable)
            draw.text((variable_text_x, bar_center_y - 10), label, font=label_font, fill=TEXT_COLOR)
            uncertainty = compute_correlation_uncertainty(precinct_rows, item) if precinct_rows is not None else None
            bar_top = bar_center_y - 12
            bar_bottom = bar_center_y + 12
            x_end = zero_x + item.spearman_rho * ((chart_right - chart_left) / 2)
            x0, x1 = sorted([zero_x, x_end])
            draw.rounded_rectangle((x0, bar_top, x1, bar_bottom), radius=9, fill=BLUE if item.spearman_rho > 0 else ORANGE)
            if uncertainty is not None:
                half_width = symmetric_uncertainty_half_width(item, uncertainty)
                whisker_y = bar_center_y
                whisker_left = zero_x + max(-1.0, item.spearman_rho - half_width) * ((chart_right - chart_left) / 2)
                whisker_right = zero_x + min(1.0, item.spearman_rho + half_width) * ((chart_right - chart_left) / 2)
                draw.line((whisker_left, whisker_y, whisker_right, whisker_y), fill="white", width=6)
                draw.line((whisker_left, whisker_y, whisker_right, whisker_y), fill=(24, 28, 34), width=2)
                draw.line((whisker_left, whisker_y - 5, whisker_left, whisker_y + 5), fill="white", width=5)
                draw.line((whisker_left, whisker_y - 5, whisker_left, whisker_y + 5), fill=(24, 28, 34), width=2)
                draw.line((whisker_right, whisker_y - 5, whisker_right, whisker_y + 5), fill="white", width=5)
                draw.line((whisker_right, whisker_y - 5, whisker_right, whisker_y + 5), fill=(24, 28, 34), width=2)
                value_label = f"{item.spearman_rho:+.2f} +/- {half_width:.2f}"
            else:
                value_label = f"{item.spearman_rho:+.2f}"
            draw.text((value_text_x, bar_center_y - 9), value_label, font=value_font, fill=TEXT_COLOR)

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path)
    return image


def create_scatter_plot(
    precinct_rows: list[dict[str, float | str | None]],
    x_key: str,
    y_key: str,
    title: str,
    subtitle: str,
    output_path: Path | None = None,
    *,
    width: int = 540,
    height: int = 430,
) -> Image.Image:
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font = load_font(22, bold=True)
    label_font = load_font(15)
    axis_font = load_font(14)
    draw.text((24, 18), title, font=title_font, fill=TEXT_COLOR)
    draw.text((24, 48), subtitle, font=axis_font, fill=MUTED_TEXT_COLOR)

    points = [
        (float(row[x_key]), float(row[y_key]))
        for row in precinct_rows
        if row.get(x_key) is not None and row.get(y_key) is not None
    ]
    if not points:
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(output_path)
        return image

    chart_left = 70
    chart_top = 90
    chart_right = width - 28
    chart_bottom = height - 64
    x_values = np.array([point[0] for point in points], dtype=float)
    y_values = np.array([point[1] for point in points], dtype=float)
    x_min = float(x_values.min())
    x_max = float(x_values.max())
    y_min = float(y_values.min())
    y_max = float(y_values.max())
    if x_min == x_max:
        x_min -= 1.0
        x_max += 1.0
    if y_min == y_max:
        y_min -= 0.05
        y_max += 0.05
    x_padding = (x_max - x_min) * 0.08
    y_padding = (y_max - y_min) * 0.10
    x_min -= x_padding
    x_max += x_padding
    y_min -= y_padding
    y_max += y_padding

    def project_x(value: float) -> float:
        return chart_left + ((value - x_min) / (x_max - x_min)) * (chart_right - chart_left)

    def project_y(value: float) -> float:
        return chart_bottom - ((value - y_min) / (y_max - y_min)) * (chart_bottom - chart_top)

    for tick_index in range(5):
        x_value = x_min + (x_max - x_min) * tick_index / 4
        y_value = y_min + (y_max - y_min) * tick_index / 4
        x = project_x(x_value)
        y = project_y(y_value)
        draw.line((x, chart_top, x, chart_bottom), fill=GRID, width=1)
        draw.line((chart_left, y, chart_right, y), fill=GRID, width=1)
        x_label = format_value_for_axis(x_key, x_value)
        y_label = format_value_for_axis(y_key, y_value)
        x_bbox = draw.textbbox((0, 0), x_label, font=axis_font)
        y_bbox = draw.textbbox((0, 0), y_label, font=axis_font)
        draw.text((x - (x_bbox[2] - x_bbox[0]) / 2, chart_bottom + 10), x_label, font=axis_font, fill=MUTED_TEXT_COLOR)
        draw.text((chart_left - y_bbox[2] - 10, y - 8), y_label, font=axis_font, fill=MUTED_TEXT_COLOR)

    draw.rectangle((chart_left, chart_top, chart_right, chart_bottom), outline=(140, 147, 158), width=2)

    if len(points) >= 2:
        slope, intercept = np.polyfit(x_values, y_values, 1)
        trend_start = (x_min, slope * x_min + intercept)
        trend_end = (x_max, slope * x_max + intercept)
        draw.line((project_x(trend_start[0]), project_y(trend_start[1]), project_x(trend_end[0]), project_y(trend_end[1])), fill=GREEN, width=4)

    for x_value, y_value in points:
        x = project_x(x_value)
        y = project_y(y_value)
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=BLUE, outline="white", width=2)

    y_label = OUTCOME_LABELS.get(y_key, TURNOUT_OUTCOME_LABEL if y_key == "turnout_pct" else VARIABLE_LABELS.get(y_key, y_key))
    draw.text((chart_left, height - 28), VARIABLE_LABELS[x_key], font=label_font, fill=TEXT_COLOR)
    draw.text((chart_right - 220, chart_top - 26), y_label, font=label_font, fill=TEXT_COLOR)

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path)
    return image


def render_image_fit(
    base_image: Image.Image,
    chart_image: Image.Image,
    left: int,
    top: int,
    max_width: int,
    max_height: int,
) -> None:
    scale = min(max_width / chart_image.width, max_height / chart_image.height)
    resized = chart_image.resize(
        (max(1, round(chart_image.width * scale)), max(1, round(chart_image.height * scale))),
        Image.Resampling.LANCZOS,
    )
    base_image.paste(resized, (left, top))


def render_cover_page(context: ReportContext) -> Image.Image:
    summary = build_summary_text(context)
    image, draw, y = make_base_page(
        "Malden Override Vote Report",
        "A readable precinct-level summary of what did and did not track with support for Questions 1A and 1B",
    )
    intro_font = load_font(28, bold=True)
    body_font = load_font(24)
    small_font = load_font(20)
    avg_q1a, avg_q1b, avg_turnout = summary["averages"]

    y = draw_wrapped_text(draw, summary["intro"], body_font, PAGE_MARGIN, y, PAGE_WIDTH - PAGE_MARGIN * 2, line_gap=10)
    y += 10
    draw.text((PAGE_MARGIN, y), "How to read the results", font=intro_font, fill=TEXT_COLOR)
    y += 46
    y = draw_wrapped_text(draw, summary["methods"], body_font, PAGE_MARGIN, y, PAGE_WIDTH - PAGE_MARGIN * 2, line_gap=10)

    box_top = PAGE_HEIGHT - 260
    box_width = (PAGE_WIDTH - PAGE_MARGIN * 2 - 40) / 3
    for index, (label, value, color) in enumerate(
        [
            ("Average Q1A yes share", f"{avg_q1a * 100:.1f}%", LIGHT_BLUE),
            ("Average Q1B yes share", f"{avg_q1b * 100:.1f}%", LIGHT_ORANGE),
            ("Average turnout", f"{avg_turnout * 100:.1f}%", LIGHT_GREEN),
        ]
    ):
        left = PAGE_MARGIN + index * (box_width + 20)
        right = left + box_width
        draw.rounded_rectangle((left, box_top, right, box_top + 130), radius=24, fill=color)
        draw.text((left + 24, box_top + 24), label, font=small_font, fill=MUTED_TEXT_COLOR)
        draw.text((left + 24, box_top + 62), value, font=load_font(34, bold=True), fill=TEXT_COLOR)
    return image


def render_analysis_page(context: ReportContext) -> Image.Image:
    summary = build_summary_text(context)
    image, draw, y = make_base_page(
        "Plain-English Findings",
        "What the precinct patterns suggest, stated cautiously and without overclaiming",
    )
    section_font = load_font(28, bold=True)
    body_font = load_font(24)
    draw.text((PAGE_MARGIN, y), "Key takeaways", font=section_font, fill=TEXT_COLOR)
    y += 46
    y = draw_bullet_list(draw, summary["key_findings"], body_font, PAGE_MARGIN + 8, y, PAGE_WIDTH - PAGE_MARGIN * 2)
    y += 10
    draw.text((PAGE_MARGIN, y), "Interpretation", font=section_font, fill=TEXT_COLOR)
    y += 46
    for paragraph in summary["analysis_paragraphs"]:
        y = draw_wrapped_text(draw, paragraph, body_font, PAGE_MARGIN, y, PAGE_WIDTH - PAGE_MARGIN * 2, line_gap=10)
        y += 8
    note = (
        "One practical way to read this: the same kinds of precincts tended to like both questions, and the difference "
        "between Q1A and Q1B was smaller than the broader yes-versus-no divide."
    )
    draw.rounded_rectangle((PAGE_MARGIN, PAGE_HEIGHT - 220, PAGE_WIDTH - PAGE_MARGIN, PAGE_HEIGHT - 90), radius=22, fill=(247, 248, 250))
    draw_wrapped_text(draw, note, load_font(22), PAGE_MARGIN + 28, PAGE_HEIGHT - 188, PAGE_WIDTH - PAGE_MARGIN * 2 - 56, fill=TEXT_COLOR, line_gap=8)
    return image


def render_correlation_overview_pages(
    context: ReportContext,
    chart_output_dir: Path = CHART_OUTPUT_DIR,
) -> tuple[list[Image.Image], list[Path]]:
    pages: list[Image.Image] = []
    paths: list[Path] = []
    for outcome in OUTCOME_LABELS:
        image, draw, _ = make_base_page(
            "Correlation Overview",
            f"Every checked variable for {OUTCOME_LABELS[outcome]}, sorted from most negative to most positive",
        )
        chart_path = chart_output_dir / f"{outcome}_all_correlation_bars.png"
        chart = create_correlation_bar_chart(
            context.correlations,
            outcome,
            chart_path,
            precinct_rows=context.precinct_rows,
            width=1110,
            height=1180,
            include_all_variables=True,
        )
        render_image_fit(image, chart, 82, 210, 1110, 1280)
        draw.text((PAGE_MARGIN, PAGE_HEIGHT - 62), "Read left as more negative correlation and right as more positive correlation.", font=load_font(18), fill=MUTED_TEXT_COLOR)
        pages.append(image)
        paths.append(chart_path)

    turnout_variables = [variable for variable in ANALYSIS_VARIABLES if variable != "turnout_pct"]
    turnout_correlations = compute_correlations(
        context.precinct_rows,
        variables=turnout_variables,
        outcomes={"turnout_pct": TURNOUT_OUTCOME_LABEL},
    )
    turnout_image, draw, _ = make_base_page(
        "Correlation Overview",
        "Every checked variable against precinct turnout, sorted from most negative to most positive",
    )
    turnout_chart_path = chart_output_dir / "turnout_pct_all_correlation_bars.png"
    turnout_chart = create_correlation_bar_chart(
        turnout_correlations,
        "turnout_pct",
        turnout_chart_path,
        precinct_rows=context.precinct_rows,
        width=1110,
        height=1180,
        include_all_variables=True,
        outcome_label=TURNOUT_OUTCOME_LABEL,
    )
    render_image_fit(turnout_image, turnout_chart, 82, 210, 1110, 1280)
    draw.text((PAGE_MARGIN, PAGE_HEIGHT - 62), "This page treats turnout as the outcome rather than vote share.", font=load_font(18), fill=MUTED_TEXT_COLOR)
    pages.append(turnout_image)
    paths.append(turnout_chart_path)
    return pages, paths


def render_example_graph_pages(
    context: ReportContext,
    chart_output_dir: Path = CHART_OUTPUT_DIR,
) -> tuple[list[Image.Image], list[Path]]:
    variables = example_graph_variables(context)
    rows_per_page = 2
    row_tops = [210, 820]
    left_position = (90, 210)
    right_position = (650, 210)
    turnout_variables = [variable for variable in variables if variable != "turnout_pct"]
    turnout_correlations = compute_correlations(
        context.precinct_rows,
        variables=turnout_variables,
        outcomes={"turnout_pct": TURNOUT_OUTCOME_LABEL},
    )
    turnout_lookup = {
        item.variable: item
        for item in correlation_rows_for_outcome(turnout_correlations, "turnout_pct")
    }
    pages: list[Image.Image] = []
    paths: list[Path] = []

    for page_start in range(0, len(variables), rows_per_page):
        page_variables = variables[page_start : page_start + rows_per_page]
        page_number = page_start // rows_per_page + 1
        image, draw, _ = make_base_page(
            "Example Graphs",
            f"Q1A yes share on the left, turnout on the right. p. {page_number}",
        )
        for variable, top in zip(page_variables, row_tops):
            q1a_correlation = correlation_for_variable(context.correlations, variable, "q1a_yes_pct")
            q1a_path = chart_output_dir / f"{variable}_q1a_yes_pct.png"
            q1a_chart = create_scatter_plot(
                context.precinct_rows,
                variable,
                "q1a_yes_pct",
                f"{VARIABLE_LABELS[variable]} vs {OUTCOME_LABELS['q1a_yes_pct']}",
                f"Spearman {q1a_correlation.spearman_rho:+.2f}",
                q1a_path,
            )
            image.paste(q1a_chart, (left_position[0], top))
            paths.append(q1a_path)

            if variable == "turnout_pct":
                continue

            turnout_correlation = turnout_lookup.get(variable)
            if turnout_correlation is None or not has_plot_data(context.precinct_rows, variable, "turnout_pct"):
                continue

            turnout_path = chart_output_dir / f"{variable}_turnout_pct.png"
            turnout_chart = create_scatter_plot(
                context.precinct_rows,
                variable,
                "turnout_pct",
                f"{VARIABLE_LABELS[variable]} vs {TURNOUT_OUTCOME_LABEL}",
                f"Spearman {turnout_correlation.spearman_rho:+.2f}",
                turnout_path,
            )
            image.paste(turnout_chart, (right_position[0], top))
            paths.append(turnout_path)
        draw.text((PAGE_MARGIN, PAGE_HEIGHT - 62), "Each row uses the same variable twice: Q1A on the left and turnout on the right. Turnout itself appears only once.", font=load_font(18), fill=MUTED_TEXT_COLOR)
        pages.append(image)
    return pages, paths


def render_conclusion_page(context: ReportContext) -> Image.Image:
    summary = build_summary_text(context)
    image, draw, y = make_base_page(
        "Conclusion",
        "What seems worth remembering after boiling the analysis down to the essentials",
    )
    section_font = load_font(28, bold=True)
    body_font = load_font(24)
    draw.text((PAGE_MARGIN, y), "Bottom line", font=section_font, fill=TEXT_COLOR)
    y += 46
    y = draw_bullet_list(draw, summary["conclusions"], body_font, PAGE_MARGIN + 8, y, PAGE_WIDTH - PAGE_MARGIN * 2)
    y += 10
    draw.text((PAGE_MARGIN, y), "Caveats", font=section_font, fill=TEXT_COLOR)
    y += 46
    caveats = [
        "These are precinct averages and estimates, not individual-level voter records.",
        "A strong correlation can still reflect several overlapping neighborhood traits at once.",
        "The city only has 27 precincts, so small changes in the data can move the rankings around.",
        "Foreign-born share and literal Walk Score are not in this version; the walkability story here is based on public proxies.",
    ]
    y = draw_bullet_list(draw, caveats, body_font, PAGE_MARGIN + 8, y, PAGE_WIDTH - PAGE_MARGIN * 2)
    return image


def append_sources_page(document: fitz.Document) -> None:
    page = document.new_page(width=612, height=792)
    title_rect = fitz.Rect(54, 42, 558, 88)
    subtitle_rect = fitz.Rect(54, 82, 558, 116)
    link_text_color = (0.08, 0.26, 0.58)
    link_fill_color = (0.90, 0.95, 1.0)
    link_border_color = (0.72, 0.84, 0.98)
    page.insert_textbox(title_rect, "Data Sources", fontsize=24, fontname="Times-Bold", color=(0.12, 0.13, 0.16))
    page.insert_textbox(
        subtitle_rect,
        "Public URLs for the official election, precinct-boundary, and Census sources used to assemble the analysis dataset.",
        fontsize=11.5,
        fontname="Helvetica",
        color=(0.36, 0.39, 0.44),
    )
    page.draw_line((54, 122), (558, 122), color=(0.82, 0.84, 0.86), width=1.5)

    y = 130
    for title, url, description in WEB_SOURCE_ENTRIES:
        page.insert_textbox(fitz.Rect(70, y, 558, y + 16), f"- {title}", fontsize=11.0, fontname="Helvetica-Bold", color=(0.12, 0.13, 0.16))
        y += 14
        url_box_rect = fitz.Rect(78, y - 1, 552, y + 21)
        page.draw_rect(url_box_rect, color=link_border_color, fill=link_fill_color, width=0.8)
        page.insert_text((88, y + 14), url, fontsize=10.0, fontname="Helvetica", color=link_text_color)
        page.insert_link({"kind": fitz.LINK_URI, "from": url_box_rect, "uri": url})
        y += 26
        desc_max_width = 546 - 84
        desc_words = description.split()
        desc_lines: list[str] = []
        current_line = ""
        for word in desc_words:
            candidate = word if not current_line else f"{current_line} {word}"
            if fitz.get_text_length(candidate, fontname="helv", fontsize=10.2) <= desc_max_width:
                current_line = candidate
            else:
                desc_lines.append(current_line)
                current_line = word
        if current_line:
            desc_lines.append(current_line)
        for index, line in enumerate(desc_lines):
            page.insert_text((84, y + 11 + index * 12), line, fontsize=10.2, fontname="Helvetica", color=(0.30, 0.33, 0.38))
        y += max(28, len(desc_lines) * 12 + 4)


def write_pdf_from_images(images: list[Image.Image], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    try:
        for image in images:
            image_bytes = io.BytesIO()
            image.save(image_bytes, format="PNG")
            page = document.new_page(width=612, height=792)
            page.insert_image(fitz.Rect(0, 0, 612, 792), stream=image_bytes.getvalue())
        append_sources_page(document)
        document.save(output_path)
    finally:
        document.close()


def generate_human_readable_pdf_report(
    output_path: Path = PDF_REPORT_OUTPUT_PATH,
) -> tuple[Path, list[Path]]:
    precinct_rows = build_precinct_covariates()
    correlations = compute_correlations(precinct_rows)
    context = ReportContext(precinct_rows=precinct_rows, correlations=correlations)
    CHART_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for existing_chart in CHART_OUTPUT_DIR.glob("*.png"):
        existing_chart.unlink()

    cover_page = render_cover_page(context)
    analysis_page = render_analysis_page(context)
    correlation_pages, bar_chart_paths = render_correlation_overview_pages(context, CHART_OUTPUT_DIR)
    scatter_pages, scatter_chart_paths = render_example_graph_pages(context, CHART_OUTPUT_DIR)
    conclusion_page = render_conclusion_page(context)

    write_pdf_from_images(
        [cover_page, analysis_page, *correlation_pages, *scatter_pages, conclusion_page],
        output_path,
    )
    return output_path, [*bar_chart_paths, *scatter_chart_paths]


def main() -> None:
    pdf_path, chart_paths = generate_human_readable_pdf_report()
    print(f"Wrote {pdf_path}")
    for chart_path in chart_paths:
        print(f"Wrote {chart_path}")


if __name__ == "__main__":
    main()
