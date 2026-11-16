# disease-snapshot

A small command-line tool that writes a short Markdown snapshot of a disease from three public sources:

1. **ClinicalTrials.gov** (API v2). Registered studies for the condition, counted by status, phase and lead sponsor class, plus a table of interventional studies that also mention a gene you choose.
2. **PubMed** (NCBI E-utilities). Publication counts per year, and the ten most recent records.
3. **Open Targets Platform** (GraphQL API). The top associated targets by overall association score, and drugs and clinical candidates grouped by maximum clinical stage.

Every number comes from code, from saved API responses. There is no language model in v0.1. Each run saves the raw responses under `raw/`, with the query and fetch time in `raw/manifest.json`, so you can trace any figure back to its source.

## Run it

Python 3.10 or later. Continuous integration tests 3.10 and 3.12.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
pytest -q                      # offline, no network needed
python snapshot.py --disease "dilated cardiomyopathy" --gene LMNA --since 2016 --out examples/dcm_lmna
```

Then open `examples/dcm_lmna/report.md` in any text editor or Markdown viewer.

Options:

- `--gene` is optional. Without it you get the disease-level view only.
- `--since` sets the first publication year (default: ten years ago).
- `--efo` sets the Open Targets disease ID directly, e.g. `--efo MONDO_0005021`. Use it when the top search hit is the wrong disease. Without `--efo`, the report lists any other search hits, so you can check the match.
- `DS_CONTACT_EMAIL` (environment variable, optional) is passed to NCBI as the contact email. The tool removes it before writing `raw/manifest.json`.

If a source fails, its section says so and the others still render. The exit code is then 1.

## Sample output

See [`examples/dcm_lmna/report.md`](examples/dcm_lmna/report.md): dilated cardiomyopathy with LMNA.

## What the numbers mean, and what they don't

- Every count depends on the query wording printed in the report. A different synonym or gene spelling gives different numbers.
- ClinicalTrials.gov lists registered studies. It is not a complete development pipeline, and statuses depend on sponsors keeping records up to date.
- PubMed counts records. A record whose print and electronic publication dates fall in different years can count in both years, so the yearly counts can add up to more than the whole-range count. The report's cross-check line shows the difference.
- Open Targets association scores weigh the evidence for a link between a target and a disease. They do not say whether any drug works.
- The report is for orientation. It is not medical advice or investment advice.

## Sources and credits

- ClinicalTrials.gov, U.S. National Library of Medicine.
- PubMed, via NCBI E-utilities. The tool keeps to NCBI's guidance of no more than three requests per second without an API key ([E-utilities introduction](https://www.ncbi.nlm.nih.gov/books/NBK25497/)).
- Open Targets Platform. Its data is marked CC0 1.0 ([licence](https://platform-docs.opentargets.org/licence)).

This project is not affiliated with or endorsed by the National Library of Medicine, NCBI or Open Targets.

## How it was built

Built with Claude Code from a frozen spec ([`docs/SPEC.md`](docs/SPEC.md)), with a separate AI reviewer checking the work before release. Open Targets test fixtures are real responses captured on 15 Nov 2026. ClinicalTrials.gov and PubMed fixtures are synthetic, with fake IDs.

## Licence

MIT for the code. See [LICENSE](LICENSE).
