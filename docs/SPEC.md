# disease-snapshot: engineer spec v1.0.1 (frozen 15 Nov 2026; v1.0.1 fixes the acceptance command, audit B1)

Owner: Nardev Ramanathan. Engineer: Claude. Auditor: ChatGPT. The owner relays messages and decides.
Goal: a public MVP within one to two days, to show a working scientific intelligence tool. Speed over polish.

## What it does
A command-line tool. You give it a disease name (and optionally a gene). It pulls three public sources and writes a one-page Markdown report.

1. **ClinicalTrials.gov (API v2).** Registered studies for the disease, plus the subset that mention the gene. Counts by overall status, phase, study type and lead sponsor class. A table of the gene-mentioning interventional studies.
2. **PubMed (NCBI E-utilities).** Publication counts per year for the disease (and disease plus gene), and the ten most recent records.
3. **Open Targets Platform (GraphQL API).** The resolved disease ID, the top ten associated targets by overall association score, and drugs and clinical candidates for the disease grouped by maximum clinical stage.

Sample run for the README: `--disease "dilated cardiomyopathy" --gene LMNA --since 2016`.

## Non-negotiable behaviours
1. **Every number in the report comes from code, from saved API responses.** No LLM anywhere in v0.1.
2. **Save every raw response** (gzipped) under `<out>/raw/`, with its URL or query, parameters and fetch time in `raw/manifest.json`.
3. **Cross-checks shown, not hidden.** ClinicalTrials.gov `totalCount` against studies fetched. Open Targets `count` against rows fetched. PubMed sum of yearly counts against the count for the whole range. A mismatch is printed in the report.
4. **Failures are visible.** A failed source becomes a "Section failed: <reason>" block. Other sections still render. Exit code 1 if any section failed.
5. **Show query wording and ambiguity.** The report prints the exact query used for each source. For Open Targets it prints the chosen disease ID and the other top search hits, so a wrong match is obvious. `--efo` overrides the search.
6. **No causal, efficacy, ranking or investment language.** Association scores are described as evidence strength for a target–disease link. Drug stages are as reported by Open Targets. Counts depend on query wording.
7. **Polite API use.** PubMed calls at most 3 per second, with `tool` and optional `email` parameters (email from `DS_CONTACT_EMAIL`). ClinicalTrials.gov paging capped at 10 pages of 1,000.
8. **Offline tests.** `pytest -q` passes with no network. Fixtures: Open Targets responses are real (captured 15 Nov 2026). ClinicalTrials.gov and PubMed fixtures are synthetic, shaped per the public API docs, with fake IDs.
9. **Python 3.10 or later. Dependencies: `requests`, `pytest` only.**
10. **README** credits each source, states the limitations and says the tool is not affiliated with or endorsed by NLM, NCBI or Open Targets, and is not medical or investment advice.

## Gate (lean, one gate before public)
- **Gate 1 (pre-release).** Evidence: repo zip and SHA-256, `pytest` output, the owner's live sample report and its `raw/` folder. Auditor checks: tests pass offline, three numbers traced to raw files (one per source), cross-checks present, failure path tested, no overclaiming, no secrets, licence and credits present.
- The owner's live run is the first contact with the real ClinicalTrials.gov and PubMed APIs. If a field name is wrong, that is a repair item, not a redesign.

## Do not build yet (v0.2 or later)
LLM summaries. HTML or charts. Patents. Multiple diseases per run. Caching. Packaging with `pyproject.toml`. Company or sponsor name cleaning.

## Acceptance test
In WSL: `pip install -r requirements.txt`, `pytest -q` passes, then
`python snapshot.py --disease "dilated cardiomyopathy" --gene LMNA --since 2016 --out examples/dcm_lmna`
writes `report.md` with three sections, each with source, query, retrieval time and cross-check line, and exits 0.
