# Malden Vote Share Data

This repository contains code and source data for analyzing and mapping the March 31, 2026 Malden, Massachusetts special election on ballot questions 1A and 1B.

The project includes:

- precinct-level election results and turnout source files in `RawData/`
- Python scripts for rendering precinct maps, turnout visuals, and precinct-level correlation analysis in `scripts/`
- automated tests for the parsing, rendering, and analysis pipeline in `tests/`

## Main scripts

- `scripts/malden_override_map.py`: renders precinct vote-share maps for Questions 1A and 1B
- `scripts/malden_turnout_graphs.py`: renders turnout graphics and turnout-by-ward charts
- `scripts/malden_precinct_analysis.py`: builds precinct covariates and a markdown correlation report
- `scripts/malden_precinct_pdf_report.py`: generates a human-readable PDF version of the correlation report

## Data sources included

- `RawData/malden_override_results_verified.xlsx`
- `RawData/malden_special_municipal_election_2026_unofficial_results.pdf`
- `RawData/malden_subprecincts_official.geojson`

`Ward and Precinct 2020 Map.pdf` is included as a visual reference only and is not used as authoritative precinct geometry.

## Running the project

Use the local Python install already configured for this project:

```powershell
C:\Users\calvi\AppData\Local\Python\bin\python.exe scripts\malden_override_map.py
C:\Users\calvi\AppData\Local\Python\bin\python.exe scripts\malden_turnout_graphs.py
C:\Users\calvi\AppData\Local\Python\bin\python.exe scripts\malden_precinct_analysis.py
C:\Users\calvi\AppData\Local\Python\bin\python.exe scripts\malden_precinct_pdf_report.py
```

Run the test suite with:

```powershell
C:\Users\calvi\AppData\Local\Python\bin\python.exe -m pytest -q
```

## Notes

- Generated outputs under `Graphics/`, `Output/`, and cache directories are intentionally gitignored because they can be rebuilt from the included sources.
- The analysis caches Census API and TIGER responses under `.cache/` when rebuilding the correlation outputs.
