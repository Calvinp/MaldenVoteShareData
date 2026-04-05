import csv

from scripts.malden_historical_results import (
    PDF_SPECS,
    generate_all_historical_candidate_csvs,
    parse_candidate_results,
    write_candidate_results_csv,
)


def load_rows(election_key: str):
    spec = next(item for item in PDF_SPECS if item["election_key"] == election_key)
    return parse_candidate_results(
        election_key=spec["election_key"],
        election_date=spec["election_date"],
        election_type=spec["election_type"],
        pdf_path=spec["pdf_path"],
    )


def test_parse_2022_state_results_includes_party_labels_and_precinct_votes():
    rows = load_rows("malden_state_election_2022_11_08")

    healey_rows = [row for row in rows if row.contest == "GOVERNOR & LT. GOVERNOR" and row.candidate == "HEALEY and DRISCOLL"]
    assert len(healey_rows) == 27
    assert healey_rows[0].candidate_party == "Democratic"
    assert next(row for row in healey_rows if row.precinct == "1-1").votes == 365
    assert next(row for row in healey_rows if row.precinct == "8-3").votes == 320

    auditor_row = next(
        row
        for row in rows
        if row.contest == "AUDITOR" and row.candidate == "GLORIA A. CABALLERO-ROCA" and row.precinct == "3-1A"
    )
    assert auditor_row.candidate_party == "Green-Rainbow Party"
    assert auditor_row.votes == 23


def test_parse_2024_state_results_handles_subset_districts_and_nonpartisan_blank_parties():
    rows = load_rows("malden_state_election_2024_11_05")

    lipper_rows = [
        row
        for row in rows
        if row.contest == "REPRESENTATIVE IN GENERAL COURT THIRTY-SECOND MIDDLESEX DISTRICT"
        and row.candidate == "KATE LIPPER-GARABEDIAN"
    ]
    assert {(row.precinct, row.votes) for row in lipper_rows} == {("5-2", 951), ("5-3A", 406)}
    assert {row.candidate_party for row in lipper_rows} == {"Democratic"}

    tauro_row = next(
        row
        for row in rows
        if row.contest == "REGISTER OF DEEDS MIDDLESEX SOUTHERN DISTRICT"
        and row.candidate == 'WILLIAM "BILLY" TAURO'
        and row.precinct == "7-3A"
    )
    assert tauro_row.candidate_party == "Independent"
    assert tauro_row.votes == 79

    holland_row = next(
        row
        for row in rows
        if row.contest == "REGIONAL SCHOOL COMMITTEE NORTHEAST METROPOLITAN MALDEN"
        and row.candidate == "JAMES J. HOLLAND"
        and row.precinct == "1-1"
    )
    assert holland_row.candidate_party == ""
    assert holland_row.votes == 504


def test_parse_2023_municipal_results_handles_citywide_and_ward_contests():
    rows = load_rows("malden_municipal_election_2023_11_07")

    mayor_row = next(
        row for row in rows if row.contest == "MAYOR" and row.candidate == "GARY J. CHRISTENSON" and row.precinct == "5-2"
    )
    assert mayor_row.candidate_party == ""
    assert mayor_row.votes == 492

    ward_two_rows = [
        row
        for row in rows
        if row.contest == "CITY COUNCILLOR - W 2" and row.candidate == "SHEILA RACHELS"
    ]
    assert {row.precinct for row in ward_two_rows} == {"2-1", "2-2", "2-3"}
    assert {(row.precinct, row.votes) for row in ward_two_rows} == {("2-1", 115), ("2-2", 94), ("2-3", 153)}


def test_parse_2025_municipal_results_handles_page_breaks():
    rows = load_rows("malden_municipal_election_2025_11_04")

    winslow_rows = [
        row
        for row in rows
        if row.contest == "CITY COUNCILLOR WARD 6" and row.candidate == "STEPHEN PATRICK WINSLOW"
    ]
    assert {(row.precinct, row.votes) for row in winslow_rows} == {("6-1", 309), ("6-2", 117), ("6-3", 141)}

    school_row = next(
        row
        for row in rows
        if row.contest == "SCHOOL COMMITTEE WARD 8" and row.candidate == "SHARYN ROSE-ZEIBERG" and row.precinct == "8-2"
    )
    assert school_row.votes == 93
    assert school_row.candidate_party == ""


def test_generate_historical_candidate_csvs_writes_parseable_csvs(tmp_path):
    rows = load_rows("malden_state_election_2024_11_05")
    output_path = tmp_path / "historical.csv"

    written_path = write_candidate_results_csv(rows, output_path)

    with written_path.open(encoding="utf-8", newline="") as handle:
        parsed = list(csv.DictReader(handle))

    assert len(parsed) == len(rows)
    assert parsed[0]["election_key"] == "malden_state_election_2024_11_05"
    assert parsed[0]["contest_slug"]


def test_generate_all_historical_candidate_csvs_returns_all_expected_paths():
    output_paths = generate_all_historical_candidate_csvs()

    assert len(output_paths) == 4
    for output_path in output_paths:
        assert output_path.exists()
