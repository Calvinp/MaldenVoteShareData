# AGENTS.md

## Purpose
- This folder contains Malden election map work built from a local results workbook and an official precinct geometry file.
- The current renderer does not recolor the old PDF map directly.
- Instead, it draws official precinct polygons over a clipped grayscale street basemap, then labels precincts and ward boundaries.

## Key Files
- [scripts/malden_override_map.py](scripts/malden_override_map.py): Main generator for all output maps.
- [scripts/malden_turnout_graphs.py](scripts/malden_turnout_graphs.py): Generator for turnout visuals, including the precinct turnout map and optional ward charts.
- [scripts/malden_precinct_analysis.py](scripts/malden_precinct_analysis.py): Precinct-level Census/turnout covariate builder and vote-share correlation report generator.
- [scripts/malden_precinct_pdf_report.py](scripts/malden_precinct_pdf_report.py): Human-readable PDF report generator with narrative pages and charts built from the precinct analysis.
- [tests/test_malden_override_map.py](tests/test_malden_override_map.py): Parsing, join, and color-scale tests.
- [tests/test_malden_turnout_graphs.py](tests/test_malden_turnout_graphs.py): Turnout PDF parsing, aggregation, and chart rendering tests.
- [tests/test_malden_precinct_analysis.py](tests/test_malden_precinct_analysis.py): Overlay, Census parsing, covariate derivation, and correlation-report tests.
- [tests/test_malden_precinct_pdf_report.py](tests/test_malden_precinct_pdf_report.py): PDF page rendering, chart generation, and report assembly tests.
- [RawData/malden_override_results_verified.xlsx](RawData/malden_override_results_verified.xlsx): Source vote totals by precinct and ward.
- [RawData/malden_special_municipal_election_2026_unofficial_results.pdf](RawData/malden_special_municipal_election_2026_unofficial_results.pdf): Official Malden PDF with registered-voter and voter-count denominators for turnout.
- [RawData/malden_subprecincts_official.geojson](RawData/malden_subprecincts_official.geojson): Official Malden precinct polygons used for rendering.
- [Output](Output): Generated PNG and SVG maps.
- [Graphics](Graphics): Generated chart graphics, including vote-share and turnout bar charts.

## How To Color A New Election Map
1. Put the new workbook in `RawData`.
2. Make sure it has a precinct-level sheet equivalent to `By Precinct` with precinct ids that match the geometry names.
3. Update `load_precinct_results()` in [scripts/malden_override_map.py](scripts/malden_override_map.py) if the column layout or question names changed.
4. Keep precinct ids normalized to the same format as the geometry file, for example `3-1A` and `7-3A`.
5. Use `render_map()` with:
   - a baked-in title for the final PNG and SVG
   - a value getter for the metric you want to color by
   - a color function that maps that metric to RGB
   - a `LegendSpec` for every public-facing map so the colors are self-explanatory
6. Regenerate outputs with:
   - `py -3 scripts/malden_override_map.py`
7. Run tests with:
   - `py -3 -m pytest -q`

## How To Rebuild The Correlation Analysis
1. Make sure the existing election workbook, turnout PDF, and precinct GeoJSON are present in `RawData`.
2. Run:
   - `py -3 scripts/malden_precinct_analysis.py`
3. The script will cache Census API and TIGER geometry responses under `.cache/precinct_analysis`.
4. Review outputs in `Output`:
   - `malden_precinct_covariates.csv`
   - `malden_vote_correlation_report.md`
5. To generate the human-readable PDF report with charts, run:
   - `py -3 scripts/malden_precinct_pdf_report.py`
6. Review additional outputs in `Output`:
   - `malden_vote_correlation_report_human.pdf`
   - `malden_vote_correlation_report_charts/`
7. Re-run tests with:
   - `py -3 -m pytest -q`

## Correlation Analysis Notes
- The analysis estimates precinct demographics by spatially intersecting precinct polygons with Census blocks and block groups; these are modeled precinct covariates, not official precinct-published Census tables.
- Race and Hispanic-share estimates come from 2020 Census redistricting tables at block level.
- Most socioeconomic variables come from 2024 ACS 5-year estimates at block-group level.
- The analysis now includes distance to the nearest MBTA rapid-transit stop, measured in straight-line miles from a precinct population-weighted block-overlap center when possible, with precinct centroid fallback otherwise.
- Literal Walk Score is not currently included; use transit share, walk share, no-car share, and density as the public walkability proxies in this repo.
- Turnout is included from the local city results PDF parser, so no turnout download is needed for the analysis pipeline.
- In the PDF report's correlation bar charts, long variable labels can collide with the numeric correlation text; keep the dynamic label/value spacing in `create_correlation_bar_chart()` so new covariates do not reintroduce that overlap.

## Color Guidance
- Use a colorblind-considerate palette by default, but follow explicit user direction if they want a different visual emphasis.
- For yes-percentage maps, the current default is a red-to-neutral-to-blue scheme where:
  - lower yes share trends red
  - the midpoint is a light neutral off-white
  - higher yes share trends blue
- Clamp vote-share maps to a fixed symmetric range of 25% to 75% yes unless the user asks for a different range.
- For difference maps, use a legend-backed diverging scale.
- If the metric is `Q1A - Q1B yes %`, warm colors should mean Q1A ran stronger and cool colors should mean Q1B ran stronger.
- If the actual data range is entirely positive or entirely negative, normalize the legend and colors to the observed range instead of forcing a symmetric zero-centered scale.

## Basemap And Layout Guidance
- The street background comes from OpenStreetMap tiles cached under `.cache/tiles`.
- The renderer clips the basemap to the city outline so outside-city clutter does not appear.
- Ward boundaries should stay darker and thicker than precinct boundaries.
- Precinct labels should stay dark with a light stroke for readability.
- Put the title in a header area above the map so it is baked into the exported image.
- Put the legend in a low-conflict area, currently the bottom-right footer space, so it does not block important map features.
- For turnout maps, use the official `Registered voters` and `Voters` counts from the city PDF and render turnout as a sequential scale, not a question-specific diverging scale.

## Updating For The Next Census / Redistricting Cycle
- Do not assume the current precinct geometry file is still valid after redistricting.
- Replace [RawData/malden_subprecincts_official.geojson](RawData/malden_subprecincts_official.geojson) with a fresh official geometry export from the City of Malden GIS or another authoritative municipal source.
- The geometry file must contain the post-redistricting precincts actually used in the election you are mapping.
- Before rendering:
  - inspect the new geometry names
  - inspect the workbook precinct ids
  - update `normalize_precinct_name()` or the workbook parser if the naming changed
  - rerun the join validation tests
- If ward boundaries changed but precinct names did not, the renderer should still work after swapping in the new geometry file because ward outlines are rebuilt from the precinct polygons.
- If the city switches to a new layer or schema:
  - update the geometry loader in `load_precinct_geometries()`
  - keep the rest of the rendering pipeline unchanged if possible

## When To Keep Or Ignore The Old PDF
- The file [Ward and Precinct 2020 Map.pdf](Ward%20and%20Precinct%202020%20Map.pdf) is useful as a visual reference only.
- Do not rely on it as authoritative precinct geometry for recoloring.
- If future agents want to compare old and new district layouts, use the PDF as a historical reference, not as the source for polygon boundaries.
