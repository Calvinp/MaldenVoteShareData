from __future__ import annotations

import io
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean

import fitz
import numpy as np
from PIL import Image, ImageDraw, ImageFont

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


@dataclass(frozen=True)
class ReportContext:
    precinct_rows: list[dict[str, float | str | None]]
    correlations: list[CorrelationResult]


def load_font(size: int, *, bold: bool = False, serif: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if serif:
        candidates = [
            Path("C:/Windows/Fonts/georgiab.ttf" if bold else "C:/Windows/Fonts/georgia.ttf"),
            Path("C:/Windows/Fonts/timesbd.ttf" if bold else "C:/Windows/Fonts/times.ttf"),
        ]
    else:
        candidates = [
            Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/Arialbd.ttf" if bold else "C:/Windows/Fonts/Arial.ttf"),
            Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
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


def create_correlation_bar_chart(
    correlations: list[CorrelationResult],
    outcome: str,
    output_path: Path | None = None,
    *,
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
    draw.text((30, 58), "Bars show Spearman correlation. Blue means more support as the variable rises; orange means less.", font=axis_font, fill=MUTED_TEXT_COLOR)

    chart_left = 360 if include_all_variables else 300
    chart_top = 110
    chart_right = width - 70
    chart_bottom = height - 55
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
            label = VARIABLE_LABELS[item.variable]
            label_bbox = draw.textbbox((0, 0), label, font=label_font)
            draw.text((chart_left - label_bbox[2] - 16, bar_center_y - 10), label, font=label_font, fill=TEXT_COLOR)
            x_end = zero_x + item.spearman_rho * ((chart_right - chart_left) / 2)
            x0, x1 = sorted([zero_x, x_end])
            draw.rounded_rectangle((x0, bar_center_y - 12, x1, bar_center_y + 12), radius=10, fill=BLUE if item.spearman_rho > 0 else ORANGE)
            value_label = f"{item.spearman_rho:+.2f}"
            value_width = draw.textbbox((0, 0), value_label, font=label_font)[2]
            text_x = x_end + 8 if item.spearman_rho > 0 else x_end - value_width - 8
            draw.text((text_x, bar_center_y - 10), value_label, font=label_font, fill=TEXT_COLOR)

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

    draw.text((chart_left, height - 28), VARIABLE_LABELS[x_key], font=label_font, fill=TEXT_COLOR)
    draw.text((chart_right - 220, chart_top - 26), OUTCOME_LABELS[y_key], font=label_font, fill=TEXT_COLOR)

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
    variables = ordered_variables(context)
    cards_per_page = 4
    positions = [(90, 210), (650, 210), (90, 820), (650, 820)]
    pages: list[Image.Image] = []
    paths: list[Path] = []

    for page_start in range(0, len(variables), cards_per_page):
        page_variables = variables[page_start : page_start + cards_per_page]
        page_number = page_start // cards_per_page + 1
        image, draw, _ = make_base_page(
            "Example Graphs",
            f"Every checked variable appears below, graphed against the outcome where it had the strongest absolute correlation (page {page_number})",
        )
        for variable, (left, top) in zip(page_variables, positions):
            outcome = best_outcome_for_variable(context.correlations, variable)
            if outcome is None:
                continue
            correlation = correlation_for_variable(context.correlations, variable, outcome)
            subtitle = (
                f"Best match: {OUTCOME_LABELS[outcome]} "
                f"(Spearman {correlation.spearman_rho:+.2f})"
            )
            path = chart_output_dir / f"{variable}_{outcome}.png"
            chart = create_scatter_plot(
                context.precinct_rows,
                variable,
                outcome,
                f"{VARIABLE_LABELS[variable]} vs {OUTCOME_LABELS[outcome]}",
                subtitle,
                path,
            )
            image.paste(chart, (left, top))
            paths.append(path)
        draw.text((PAGE_MARGIN, PAGE_HEIGHT - 62), "Green lines are simple trend lines added only to make the general direction easier to see.", font=load_font(18), fill=MUTED_TEXT_COLOR)
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


def write_pdf_from_images(images: list[Image.Image], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    try:
        for image in images:
            image_bytes = io.BytesIO()
            image.save(image_bytes, format="PNG")
            page = document.new_page(width=612, height=792)
            page.insert_image(fitz.Rect(0, 0, 612, 792), stream=image_bytes.getvalue())
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
