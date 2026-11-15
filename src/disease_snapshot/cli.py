"""Command-line entry point. From the repo root run: python snapshot.py --disease ... [--gene ...]"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from . import analyse as A
from .fetch import OT_DISEASE, OT_SEARCH, Client, FetchError, Recorder, now_utc
from .render import render

N_TARGETS = 10
N_RECENT = 10


def build_trials(c: Client, disease: str, gene: str | None) -> dict:
    sec = {"cond": disease, "term": gene, "fetched_at": now_utc()}
    try:
        studies, total = c.ct_studies(disease, None, "disease")
        sec["disease"] = {"total": total, "summary": A.trials_summary(studies)}
        if gene:
            gstudies, gtotal = c.ct_studies(disease, gene, "gene")
            gsum = A.trials_summary(gstudies)
            sec["gene"] = {"total": gtotal, "summary": gsum}
            sec["gene_table"] = A.interventional_table(gsum)
    except FetchError as e:
        sec["error"] = str(e)
    return sec


def pubmed_base(disease: str, gene: str | None) -> list[tuple[str, str]]:
    bases = [(disease, f'"{disease}"[Title/Abstract]')]
    if gene:
        bases.append((f"{disease} + {gene}", f'"{disease}"[Title/Abstract] AND {gene}[Title/Abstract]'))
    return bases


def build_pubmed(c: Client, disease: str, gene: str | None, since: int, until: int) -> dict:
    sec = {"fetched_at": now_utc(), "queries": []}
    try:
        for i, (label, base) in enumerate(pubmed_base(disease, gene)):
            by_year = {y: c.pubmed_count(t, f"q{i + 1}_{y}") for y, t in A.year_terms(base, since, until)}
            rng = A.range_term(base, since, until)
            sec["queries"].append({"label": label, "term": base, "by_year": by_year,
                                   "range_total": c.pubmed_count(rng, f"q{i + 1}_range")})
        last = sec["queries"][-1]
        sec["recent"] = c.pubmed_recent(last["term"], N_RECENT, "recent")
    except FetchError as e:
        sec["error"] = str(e)
    return sec


def build_ot(c: Client, disease: str, efo: str | None) -> dict:
    sec = {"fetched_at": now_utc()}
    try:
        if efo:
            chosen, alts, note = {"id": efo}, [], "set with --efo"
        else:
            chosen, alts = A.resolve_disease(c.ot(OT_SEARCH, {"q": disease}, "search"))
            note = "top search hit"
            if not chosen:
                raise FetchError(f"no Open Targets disease found for '{disease}'")
        data = c.ot(OT_DISEASE, {"id": chosen["id"], "n": N_TARGETS}, "disease")
        if not data.get("disease"):
            raise FetchError(f"Open Targets has no disease record for {chosen['id']}")
        sec.update(summary=A.ot_summary(data), alternatives=alts, match_note=note)
    except FetchError as e:
        sec["error"] = str(e)
    return sec


def main(argv: list[str] | None = None, client_factory=None) -> int:
    p = argparse.ArgumentParser(prog="disease_snapshot", description="One-page public-data snapshot of a disease.")
    p.add_argument("--disease", required=True, help='e.g. "dilated cardiomyopathy"')
    p.add_argument("--gene", help="optional gene symbol, e.g. LMNA")
    p.add_argument("--since", type=int, default=dt.date.today().year - 10, help="first publication year")
    p.add_argument("--efo", help="Open Targets disease ID to use instead of searching, e.g. MONDO_0005021")
    p.add_argument("--out", default="out", help="output folder")
    a = p.parse_args(argv)
    until = dt.date.today().year
    if not 1900 <= a.since <= until:
        p.error(f"--since must be between 1900 and {until}")

    out = Path(a.out)
    rec = Recorder(out)
    c = (client_factory or Client)(rec)
    trials = build_trials(c, a.disease, a.gene)
    pubmed = build_pubmed(c, a.disease, a.gene, a.since, until)
    ot = build_ot(c, a.disease, a.efo)
    report = render({"disease": a.disease, "gene": a.gene, "since": a.since}, trials, pubmed, ot, now_utc())
    (out / "report.md").write_text(report, encoding="utf-8")
    failed = [n for n, s in (("trials", trials), ("pubmed", pubmed), ("open targets", ot)) if s.get("error")]
    print(f"Report written to {out / 'report.md'}")
    if failed:
        print("Sections failed: " + ", ".join(failed), file=sys.stderr)
        return 1
    return 0
