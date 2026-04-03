from __future__ import annotations

import math
import os
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import MultiPolygon, Polygon

try:
    from scripts.malden_override_map import (
        OUTPUT_DIR,
        LegendSpec,
        build_basemap,
        interpolate_between_stops,
        load_precinct_geometries,
        render_map,
        validate_join,
    )
except ModuleNotFoundError:
    from malden_override_map import (  # type: ignore
        OUTPUT_DIR,
        LegendSpec,
        build_basemap,
        interpolate_between_stops,
        load_precinct_geometries,
        render_map,
        validate_join,
    )


ROOT = Path(__file__).resolve().parent.parent
GRAPHICS_DIR = ROOT / "Graphics"
TURNOUT_PDF_PATH = ROOT / "RawData" / "malden_special_municipal_election_2026_unofficial_results.pdf"
TURNOUT_PDF_URL = "https://www.cityofmalden.org/DocumentCenter/View/11460/March-31-2026-Unofficial-Results"
USER_AGENT = "Prop2.5OverrideData/1.0 (side-project local turnout chart generator)"

TURNOUT_COLOR_STOPS = [
    (0.05, (219, 234, 254)),
    (0.15, (96, 165, 250)),
    (0.25, (29, 78, 216)),
    (0.35, (30, 64, 175)),
]


@dataclass(frozen=True)
class PrecinctTurnout:
    precinct: str
    registered_voters: int
    ballots_cast: int

    @property
    def turnout_pct(self) -> float:
        return self.ballots_cast / self.registered_voters

    @property
    def ward(self) -> str:
        return self.precinct.split("-")[0]


@dataclass(frozen=True)
class WardTurnout:
    ward: str
    registered_voters: int
    ballots_cast: int

    @property
    def turnout_pct(self) -> float:
        return self.ballots_cast / self.registered_voters


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_dirs: list[Path] = []
    for env_var in ("WINDIR", "SystemRoot"):
        base_dir = os.environ.get(env_var)
        if not base_dir:
            continue
        font_dir = Path(base_dir) / "Fonts"
        if font_dir not in font_dirs:
            font_dirs.append(font_dir)
    candidates = [
        font_dir / filename
        for font_dir in font_dirs
        for filename in ("arialbd.ttf", "Arialbd.ttf", "segoeuib.ttf")
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def interpolate_between_stops(
    value: float, stops: list[tuple[float, tuple[int, int, int]]]
) -> tuple[int, int, int]:
    if value <= stops[0][0]:
        return stops[0][1]
    if value >= stops[-1][0]:
        return stops[-1][1]

    for (left_value, left_color), (right_value, right_color) in zip(stops, stops[1:]):
        if left_value <= value <= right_value:
            fraction = (value - left_value) / (right_value - left_value)
            return tuple(
                round(left_channel + (right_channel - left_channel) * fraction)
                for left_channel, right_channel in zip(left_color, right_color)
            )
    return stops[-1][1]


def download_turnout_pdf(
    pdf_path: Path = TURNOUT_PDF_PATH,
    pdf_url: str = TURNOUT_PDF_URL,
) -> Path:
    if pdf_path.exists():
        return pdf_path

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(pdf_url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        pdf_path.write_bytes(response.read())
    return pdf_path


def extract_pdf_text(pdf_path: Path = TURNOUT_PDF_PATH) -> str:
    document = fitz.open(download_turnout_pdf(pdf_path))
    try:
        return "\n".join(page.get_text() for page in document)
    finally:
        document.close()


def parse_precinct_turnout(pdf_text: str) -> dict[str, PrecinctTurnout]:
    precinct_section, remainder = pdf_text.split("Registered voters", 1)
    registered_section, remainder = remainder.split("Voters", 1)
    voters_section, _ = remainder.split("Turnout", 1)

    precinct_names = re.findall(r"\b(?:[1-8]-[1-3]A?|TOTAL)\b", precinct_section)
    registered_values = [int(value) for value in re.findall(r"\b\d+\b", registered_section)]
    voter_values = [int(value) for value in re.findall(r"\b\d+\b", voters_section)]

    if not (len(precinct_names) == len(registered_values) == len(voter_values)):
        raise ValueError(
            "Malformed turnout PDF parse: "
            f"{len(precinct_names)} precinct labels, "
            f"{len(registered_values)} registered-voter values, "
            f"{len(voter_values)} voter values"
        )

    turnout: dict[str, PrecinctTurnout] = {}
    for precinct_name, registered_voters, ballots_cast in zip(
        precinct_names, registered_values, voter_values
    ):
        if precinct_name == "TOTAL":
            continue
        turnout[precinct_name] = PrecinctTurnout(
            precinct=precinct_name,
            registered_voters=registered_voters,
            ballots_cast=ballots_cast,
        )
    return turnout


def load_precinct_turnout(pdf_path: Path = TURNOUT_PDF_PATH) -> dict[str, PrecinctTurnout]:
    return parse_precinct_turnout(extract_pdf_text(pdf_path))


def aggregate_ward_turnout(
    precinct_turnout: dict[str, PrecinctTurnout],
) -> list[WardTurnout]:
    ward_totals: dict[str, tuple[int, int]] = {}
    for turnout in precinct_turnout.values():
        registered_voters, ballots_cast = ward_totals.get(turnout.ward, (0, 0))
        ward_totals[turnout.ward] = (
            registered_voters + turnout.registered_voters,
            ballots_cast + turnout.ballots_cast,
        )

    return [
        WardTurnout(ward=ward, registered_voters=totals[0], ballots_cast=totals[1])
        for ward, totals in sorted(ward_totals.items(), key=lambda item: int(item[0]))
    ]


def format_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def turnout_color(turnout_pct: float) -> tuple[int, int, int]:
    return interpolate_between_stops(turnout_pct, TURNOUT_COLOR_STOPS)


def build_turnout_legend() -> LegendSpec:
    levels = [0.05, 0.15, 0.25, 0.35]
    return LegendSpec(
        title="Turnout",
        items=[(f"{round(level * 100):.0f}%", turnout_color(level)) for level in levels],
        position="bottom-right",
    )


def render_turnout_map(
    precinct_turnout: dict[str, PrecinctTurnout],
    geometries: dict[str, Polygon | MultiPolygon] | None = None,
    output_stem: Path | None = None,
) -> None:
    geometries = geometries or load_precinct_geometries()
    missing, extra = validate_join(precinct_turnout, geometries)
    if missing or extra:
        raise ValueError(f"join mismatch: missing={missing}, extra={extra}")

    basemap = build_basemap(geometries)
    render_map(
        "Malden special election turnout by precinct",
        lambda turnout: turnout.turnout_pct,
        precinct_turnout,
        geometries,
        basemap,
        output_stem or OUTPUT_DIR / "malden_turnout_precinct_map",
        turnout_color,
        build_turnout_legend(),
    )


def render_turnout_chart(
    question_label: str,
    ward_turnout: list[WardTurnout],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    width = 1400
    height = 900
    header_height = 150
    footer_height = 130
    left_margin = 120
    right_margin = 80
    chart_top = header_height
    chart_bottom = height - footer_height
    chart_height = chart_bottom - chart_top
    chart_width = width - left_margin - right_margin

    max_turnout_pct = max(item.turnout_pct for item in ward_turnout)
    y_max = max(0.25, math.ceil((max_turnout_pct * 100) / 5) * 5 / 100)

    image = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)

    title_font = load_font(40)
    subtitle_font = load_font(22)
    axis_font = load_font(20)
    label_font = load_font(24)
    note_font = load_font(18)

    title = f"Malden {question_label} turnout by ward"
    subtitle = "Turnout = total ballots cast / registered voters"
    note = (
        "Source: City of Malden unofficial March 31, 2026 results. "
        "These Q1A and Q1B turnout charts are identical because both questions were on the same ballot."
    )

    draw.text((width / 2, 38), title, anchor="ma", fill=(38, 38, 38), font=title_font)
    draw.text((width / 2, 90), subtitle, anchor="ma", fill=(82, 82, 82), font=subtitle_font)
    draw.line((40, 120, width - 40, 120), fill=(205, 205, 205), width=2)

    for step in range(0, int(y_max * 100) + 1, 5):
        y_value = step / 100
        y = chart_bottom - (y_value / y_max) * chart_height
        draw.line((left_margin, y, width - right_margin, y), fill=(232, 232, 232), width=2)
        draw.text(
            (left_margin - 18, y),
            f"{step}%",
            anchor="rm",
            fill=(96, 96, 96),
            font=axis_font,
        )

    draw.line((left_margin, chart_top, left_margin, chart_bottom), fill=(110, 110, 110), width=3)
    draw.line((left_margin, chart_bottom, width - right_margin, chart_bottom), fill=(110, 110, 110), width=3)

    slot_width = chart_width / len(ward_turnout)
    bar_width = slot_width * 0.58
    for index, ward in enumerate(ward_turnout):
        center_x = left_margin + slot_width * (index + 0.5)
        bar_left = center_x - bar_width / 2
        bar_right = center_x + bar_width / 2
        bar_top = chart_bottom - (ward.turnout_pct / y_max) * chart_height

        draw.rounded_rectangle(
            (bar_left, bar_top, bar_right, chart_bottom),
            radius=18,
            fill=(*turnout_color(ward.turnout_pct), 255),
            outline=(67, 67, 67),
            width=2,
        )
        draw.text(
            (center_x, bar_top - 16),
            format_pct(ward.turnout_pct),
            anchor="ms",
            fill=(45, 45, 45),
            font=label_font,
        )
        draw.text(
            (center_x, chart_bottom + 32),
            f"Ward {ward.ward}",
            anchor="ma",
            fill=(60, 60, 60),
            font=axis_font,
        )
        draw.text(
            (center_x, chart_bottom + 62),
            f"{ward.ballots_cast:,} / {ward.registered_voters:,}",
            anchor="ma",
            fill=(96, 96, 96),
            font=note_font,
        )

    draw.text(
        (width / 2, height - 44),
        note,
        anchor="ma",
        fill=(100, 100, 100),
        font=note_font,
    )

    image.save(output_path)


def generate_all_turnout_charts() -> None:
    ward_turnout = aggregate_ward_turnout(load_precinct_turnout())
    render_turnout_chart("Question 1A", ward_turnout, GRAPHICS_DIR / "malden_q1a_turnout_by_ward.png")
    render_turnout_chart("Question 1B", ward_turnout, GRAPHICS_DIR / "malden_q1b_turnout_by_ward.png")


def generate_turnout_map() -> None:
    render_turnout_map(load_precinct_turnout())


if __name__ == "__main__":
    generate_turnout_map()
