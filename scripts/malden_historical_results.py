from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = ROOT / "RawData"

PDF_SPECS = [
    {
        "election_key": "malden_state_election_2022_11_08",
        "election_date": "2022-11-08",
        "election_type": "state",
        "pdf_path": RAW_DATA_DIR / "malden_state_election_2022_11_08_results.pdf",
        "csv_path": RAW_DATA_DIR / "malden_state_election_2022_11_08_candidate_results.csv",
    },
    {
        "election_key": "malden_municipal_election_2023_11_07",
        "election_date": "2023-11-07",
        "election_type": "municipal",
        "pdf_path": RAW_DATA_DIR / "malden_municipal_election_2023_11_07_results.pdf",
        "csv_path": RAW_DATA_DIR / "malden_municipal_election_2023_11_07_candidate_results.csv",
    },
    {
        "election_key": "malden_state_election_2024_11_05",
        "election_date": "2024-11-05",
        "election_type": "state",
        "pdf_path": RAW_DATA_DIR / "malden_state_election_2024_11_05_results.pdf",
        "csv_path": RAW_DATA_DIR / "malden_state_election_2024_11_05_candidate_results.csv",
    },
    {
        "election_key": "malden_municipal_election_2025_11_04",
        "election_date": "2025-11-04",
        "election_type": "municipal",
        "pdf_path": RAW_DATA_DIR / "malden_municipal_election_2025_11_04_results.pdf",
        "csv_path": RAW_DATA_DIR / "malden_municipal_election_2025_11_04_candidate_results.csv",
    },
]

CSV_FIELDNAMES = [
    "election_key",
    "election_date",
    "election_type",
    "contest",
    "contest_slug",
    "contest_order",
    "candidate",
    "candidate_party",
    "candidate_order",
    "precinct",
    "ward",
    "votes",
]

PRECINCT_TOKEN_RE = re.compile(r"^\d-\dA?$")
INTEGER_TOKEN_RE = re.compile(r"^\d+$")
PERCENT_TOKEN_RE = re.compile(r"^\d+(?:\.\d+)?%$")
ROW_Y_TOLERANCE = 1.0
COLUMN_X_TOLERANCE = 13.0

SUMMARY_LABELS = {
    "REGISTERED VOTERS",
    "VOTERS",
    "TOTAL VOTES",
    "TURN OUT PERCENTAGE",
    "TURNOUT",
    "TOTAL NUMBER OF WRITE-INS",
    "TIMES BLANK VOTED",
    "TOTAL BALLOTS",
    "TOTAL COUNT",
    "YES",
    "NO",
}

IGNORED_HEADING_LABELS = {
    "MUNICIPAL ELECTION",
    "FINAL RESULTS",
    "FINAL RESULTS STATE ELECTION NOVEMBER 5, 2024",
    "MUNICIPAL ELECTION NOVEMBER 4, 2025 FINAL RESULTS",
}

STATE_CANDIDATE_PARTIES = {
    ("malden_state_election_2022_11_08", "DIEHL AND ALLEN"): "Republican",
    ("malden_state_election_2022_11_08", "HEALEY AND DRISCOLL"): "Democratic",
    ("malden_state_election_2022_11_08", "REED AND EVERETT"): "Libertarian",
    ("malden_state_election_2022_11_08", "ANDREA JOY CAMPBELL"): "Democratic",
    ("malden_state_election_2022_11_08", "JAMES R. MCMAHON, III"): "Republican",
    ("malden_state_election_2022_11_08", "WILLIAM FRANCIS GALVIN"): "Democratic",
    ("malden_state_election_2022_11_08", "RAYLA CAMPBELL"): "Republican",
    ("malden_state_election_2022_11_08", "JUAN SANCHEZ"): "Green-Rainbow Party",
    ("malden_state_election_2022_11_08", "DEBORAH B. GOLDBERG"): "Democratic",
    ("malden_state_election_2022_11_08", "CRISTINA CRAWFORD"): "Libertarian",
    ("malden_state_election_2022_11_08", "ANTHONY AMORE"): "Republican",
    ("malden_state_election_2022_11_08", "DIANA DIZOGLIO"): "Democratic",
    ("malden_state_election_2022_11_08", "GLORIA A. CABALLERO-ROCA"): "Green-Rainbow Party",
    ("malden_state_election_2022_11_08", "DOMINIC GIANNONE, III"): "Workers Party",
    ("malden_state_election_2022_11_08", "DANIEL RIEK"): "Libertarian",
    ("malden_state_election_2022_11_08", "KATHERINE M. CLARK"): "Democratic",
    ("malden_state_election_2022_11_08", "CAROLINE COLARUSSO"): "Republican",
    ("malden_state_election_2022_11_08", "TERRENCE W. KENNEDY"): "Democratic",
    ("malden_state_election_2022_11_08", "JASON M. LEWIS"): "Democratic",
    ("malden_state_election_2022_11_08", "EDWARD F. DOMBROSKI, JR."): "Republican",
    ("malden_state_election_2022_11_08", "KATE LIPPER-GARABEDIAN"): "Democratic",
    ("malden_state_election_2022_11_08", "STEVEN ULTRINO"): "Democratic",
    ("malden_state_election_2022_11_08", "PAUL J. DONATO"): "Democratic",
    ("malden_state_election_2022_11_08", "MARIAN T. RYAN"): "Democratic",
    ("malden_state_election_2022_11_08", "PETER J. KOUTOUJIAN"): "Democratic",
    ("malden_state_election_2024_11_05", "AYYADURAI AND ELLIS"): "Independent",
    ("malden_state_election_2024_11_05", "DE LA CRUZ AND GARCIA"): "Socialism and Liberation",
    ("malden_state_election_2024_11_05", "HARRIS AND WALZ"): "Democratic",
    ("malden_state_election_2024_11_05", "OLIVER AND TER MAAT"): "Libertarian",
    ("malden_state_election_2024_11_05", "STEIN AND CABALLERO-ROCA"): "Green-Rainbow Party",
    ("malden_state_election_2024_11_05", "TRUMP AND VANCE"): "Republican",
    ("malden_state_election_2024_11_05", "ELIZABETH ANN WARREN"): "Democratic",
    ("malden_state_election_2024_11_05", "JOHN DEATON"): "Republican",
    ("malden_state_election_2024_11_05", "KATHERINE M. CLARK"): "Democratic",
    ("malden_state_election_2024_11_05", "TERRENCE W. KENNEDY"): "Democratic",
    ("malden_state_election_2024_11_05", "JASON M. LEWIS"): "Democratic",
    ("malden_state_election_2024_11_05", "KATE LIPPER-GARABEDIAN"): "Democratic",
    ("malden_state_election_2024_11_05", "STEVEN ULTRINO"): "Democratic",
    ("malden_state_election_2024_11_05", "PAUL J. DONATO"): "Democratic",
    ("malden_state_election_2024_11_05", "MICHAEL A. SULLIVAN"): "Democratic",
    ("malden_state_election_2024_11_05", "MARIA C. CURTATONE"): "Democratic",
    ("malden_state_election_2024_11_05", "WILLIAM \"BILLY\" TAURO"): "Independent",
}


@dataclass(frozen=True)
class CandidateResult:
    election_key: str
    election_date: str
    election_type: str
    contest: str
    contest_slug: str
    contest_order: int
    candidate: str
    candidate_party: str
    candidate_order: int
    precinct: str
    ward: str
    votes: int

    def to_csv_row(self) -> dict[str, str | int]:
        return {
            "election_key": self.election_key,
            "election_date": self.election_date,
            "election_type": self.election_type,
            "contest": self.contest,
            "contest_slug": self.contest_slug,
            "contest_order": self.contest_order,
            "candidate": self.candidate,
            "candidate_party": self.candidate_party,
            "candidate_order": self.candidate_order,
            "precinct": self.precinct,
            "ward": self.ward,
            "votes": self.votes,
        }


def normalize_text(value: str) -> str:
    normalized = value.replace("\u2019", "'").replace("\u2018", "'").replace("\ufffd", "'").replace("�", "'")
    normalized = normalized.replace("\xa0", " ")
    return " ".join(normalized.split()).strip()


def normalize_lookup(value: str) -> str:
    normalized = normalize_text(value).upper()
    normalized = normalized.replace("DIZOGLIO", "DIZOGLIO")
    return normalized


def slugify(value: str) -> str:
    slug = normalize_lookup(value)
    slug = re.sub(r"[^A-Z0-9]+", "_", slug).strip("_")
    return slug.lower()


def build_rows(page: fitz.Page) -> list[list[tuple[float, str]]]:
    rows: list[list[tuple[float, float, str]]] = []
    for x0, y0, x1, _y1, text, *_rest in sorted(page.get_text("words"), key=lambda item: (item[1], item[0])):
        cleaned = normalize_text(str(text))
        if not cleaned:
            continue
        x_center = (x0 + x1) / 2
        if not rows:
            rows.append([(x_center, y0, cleaned)])
            continue
        previous = rows[-1]
        average_y = sum(item[1] for item in previous) / len(previous)
        if abs(y0 - average_y) <= ROW_Y_TOLERANCE:
            previous.append((x_center, y0, cleaned))
        else:
            rows.append([(x_center, y0, cleaned)])

    grouped: list[list[tuple[float, str]]] = []
    for row in rows:
        grouped.append([(x0, text) for x0, _y0, text in sorted(row, key=lambda item: item[0])])
    return grouped


def precinct_columns_from_row(row: list[tuple[float, str]]) -> list[tuple[str, float]]:
    precinct_cells = [(text, x0) for x0, text in row if PRECINCT_TOKEN_RE.fullmatch(text) or text == "TOTAL"]
    if len(precinct_cells) < 5:
        return []
    return precinct_cells


def row_label_and_tokens(
    row: list[tuple[float, str]],
    precinct_columns: list[tuple[str, float]],
) -> tuple[str, list[tuple[float, str]]]:
    first_precinct_x = min(x0 for precinct, x0 in precinct_columns if precinct != "TOTAL")
    label_cutoff = first_precinct_x - 12.0
    label_words = [text for x0, text in row if x0 < label_cutoff]
    number_tokens = [(x0, text) for x0, text in row if x0 >= label_cutoff and (INTEGER_TOKEN_RE.fullmatch(text) or PERCENT_TOKEN_RE.fullmatch(text))]
    return normalize_text(" ".join(label_words)), number_tokens


def nearest_precinct(x_position: float, precinct_columns: list[tuple[str, float]]) -> tuple[str, float]:
    return min(precinct_columns, key=lambda item: abs(item[1] - x_position))


def parse_numeric_row(
    row_tokens: list[tuple[float, str]],
    precinct_columns: list[tuple[str, float]],
) -> tuple[dict[str, int], int | None]:
    values: dict[str, int] = {}
    total_value: int | None = None
    for x0, token in row_tokens:
        precinct, precinct_x = nearest_precinct(x0, precinct_columns)
        if abs(x0 - precinct_x) > COLUMN_X_TOLERANCE:
            continue
        value = int(token)
        if precinct == "TOTAL":
            total_value = value
        else:
            values[precinct] = value
    return values, total_value


def is_summary_row(label: str) -> bool:
    return normalize_lookup(label) in SUMMARY_LABELS


def is_ignored_heading(label: str) -> bool:
    normalized = normalize_lookup(label)
    return not normalized or normalized in IGNORED_HEADING_LABELS


def parse_candidate_results(
    election_key: str,
    election_date: str,
    election_type: str,
    pdf_path: Path,
) -> list[CandidateResult]:
    document = fitz.open(pdf_path)
    precinct_columns: list[tuple[str, float]] = []
    current_contest: str | None = None
    contest_order_lookup: dict[str, int] = {}
    candidate_order_lookup: dict[str, dict[str, int]] = {}
    results: list[CandidateResult] = []

    for page in document:
        for row in build_rows(page):
            maybe_precinct_columns = precinct_columns_from_row(row)
            if maybe_precinct_columns:
                precinct_columns = maybe_precinct_columns
                continue
            if not precinct_columns:
                continue

            label, numeric_tokens = row_label_and_tokens(row, precinct_columns)
            normalized_label = normalize_lookup(label)

            if not label and not numeric_tokens:
                continue
            if normalized_label in {"FINAL RESULTS", "NOVEMBER 7, 2023 MUNICIPAL ELECTION"}:
                continue

            if label and not numeric_tokens:
                if not is_ignored_heading(label) and not is_summary_row(label):
                    current_contest = label
                continue

            if not current_contest or not label or is_summary_row(label):
                continue

            contest = current_contest
            precinct_votes, total_value = parse_numeric_row(numeric_tokens, precinct_columns)
            if not precinct_votes:
                continue
            if total_value is not None and sum(precinct_votes.values()) != total_value:
                raise ValueError(
                    f"Candidate totals do not match precinct sum for {election_key} / {contest} / {label}: "
                    f"{sum(precinct_votes.values())} != {total_value}"
                )

            if contest not in contest_order_lookup:
                contest_order_lookup[contest] = len(contest_order_lookup) + 1
                candidate_order_lookup[contest] = {}
            if label not in candidate_order_lookup[contest]:
                candidate_order_lookup[contest][label] = len(candidate_order_lookup[contest]) + 1

            party = STATE_CANDIDATE_PARTIES.get((election_key, normalize_lookup(label)), "")
            contest_slug = slugify(contest)
            contest_order = contest_order_lookup[contest]
            candidate_order = candidate_order_lookup[contest][label]

            for precinct in sorted(precinct_votes):
                results.append(
                    CandidateResult(
                        election_key=election_key,
                        election_date=election_date,
                        election_type=election_type,
                        contest=contest,
                        contest_slug=contest_slug,
                        contest_order=contest_order,
                        candidate=label,
                        candidate_party=party,
                        candidate_order=candidate_order,
                        precinct=precinct,
                        ward=precinct.split("-")[0],
                        votes=precinct_votes[precinct],
                    )
                )

    return results


def write_candidate_results_csv(rows: list[CandidateResult], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_csv_row())
    return output_path


def generate_all_historical_candidate_csvs() -> list[Path]:
    output_paths: list[Path] = []
    for spec in PDF_SPECS:
        rows = parse_candidate_results(
            election_key=spec["election_key"],
            election_date=spec["election_date"],
            election_type=spec["election_type"],
            pdf_path=spec["pdf_path"],
        )
        output_paths.append(write_candidate_results_csv(rows, spec["csv_path"]))
    return output_paths


if __name__ == "__main__":
    for output_path in generate_all_historical_candidate_csvs():
        print(f"Wrote {output_path}")
