"""Render the short Markdown report from analysed data."""
from __future__ import annotations

from . import __version__

TITLE_MAX = 90


def _md(text: str) -> str:
    return str(text).replace("|", "/").replace("\n", " ").strip()


def _trim(text: str, n: int = TITLE_MAX) -> str:
    text = _md(text)
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _counter_table(title: str, counter, label: str) -> list[str]:
    lines = [f"**{title}**", "", f"| {label} | Studies |", "|---|---:|"]
    for k, v in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"| {_md(k)} | {v} |")
    return lines + [""]


def _check(label: str, a, b, a_name: str, b_name: str) -> str:
    if a is None or b is None:
        return f"Cross-check ({label}): {a_name} {a}, {b_name} {b}. **Could not compare.**"
    status = "match" if a == b else "**MISMATCH**"
    return f"Cross-check ({label}): {a_name} {a}, {b_name} {b}. {status}."


def _pubmed_check(label: str, yearly_sum: int, range_total: int) -> str:
    # The range count is the union of the yearly sets, so the yearly sum can only be equal or larger.
    if yearly_sum == range_total:
        status = "match"
    elif yearly_sum > range_total:
        status = (f"consistent: yearly counts exceed the range by {yearly_sum - range_total}, as expected when a "
                  "record's print and electronic publication dates fall in different years")
    else:
        status = "**MISMATCH**"
    return (f"Cross-check ({label}): sum of yearly counts {yearly_sum}, "
            f"count for the whole range {range_total}. {status}.")


def _failed(reason: str) -> list[str]:
    return [f"> **Section failed:** {_md(reason)}", ""]


def trials_section(sec: dict) -> list[str]:
    out = ["## 1. Registered studies (ClinicalTrials.gov)", ""]
    if sec.get("error"):
        return out + _failed(sec["error"])
    q = f"Queries: condition `{_md(sec['cond'])}` for all studies"
    if sec.get("term"):
        q += f", and the same condition with other terms `{_md(sec['term'])}` for the gene subset"
    out += [q + f". Retrieved {sec['fetched_at']}.", ""]
    d, g = sec["disease"], sec.get("gene")
    for label, part in (("disease query", d), ("gene query", g)):
        if not part:
            continue
        out.append(_check(label, part["total"], part["summary"]["n"], "registry totalCount", "unique studies fetched"))
        if part["summary"]["duplicates_dropped"]:
            out.append(f"{part['summary']['duplicates_dropped']} repeated record(s) across pages were counted once.")
        out.append("")
    s = d["summary"]
    out += [f"Studies registered for the condition: **{s['n']}**, of which **{s['n_active']}** have an active status "
            "(recruiting, not yet recruiting, active not recruiting or enrolling by invitation).", ""]
    out += _counter_table("By overall status", s["by_status"], "Status")
    out += _counter_table("By phase (NA = not applicable or not given)", s["by_phase"], "Phase")
    out += _counter_table("By study type", s["by_type"], "Study type")
    out += _counter_table("By lead sponsor class", s["by_sponsor_class"], "Sponsor class")
    if g:
        gs = g["summary"]
        rows = sec["gene_table"]
        out += [f"### Studies that also mention `{_md(sec['term'])}`: {gs['n']}", "",
                f"Interventional studies among them: **{len(rows)}**, newest start date first.", ""]
        if rows:
            out += ["| NCT ID | Title | Phase | Status | Lead sponsor | Start |", "|---|---|---|---|---|---|"]
            for r in rows:
                out.append(f"| [{r['nct_id']}](https://clinicaltrials.gov/study/{r['nct_id']}) | {_trim(r['title'])} | "
                           f"{_md(r['phase'])} | {_md(r['status'])} | {_trim(r['sponsor'], 40)} | {_md(r['start'])} |")
            out.append("")
    return out


def pubmed_section(sec: dict) -> list[str]:
    out = ["## 2. Publications (PubMed)", ""]
    if sec.get("error"):
        return out + _failed(sec["error"])
    out += [f"Retrieved {sec['fetched_at']}. Counts use the publication date field `[dp]`. "
            f"The current year is partial.", ""]
    for q in sec["queries"]:
        out += [f"Query: `{_md(q['term'])}`", "",
                _pubmed_check(q["label"], sum(q["by_year"].values()), q["range_total"]), ""]
    labels = [q["label"] for q in sec["queries"]]
    out += ["| Year | " + " | ".join(labels) + " |", "|---|" + "---:|" * len(labels)]
    years = sorted(sec["queries"][0]["by_year"])
    for y in years:
        out.append(f"| {y} | " + " | ".join(str(q["by_year"][y]) for q in sec["queries"]) + " |")
    out.append("")
    last = sec["queries"][-1]
    if sec.get("recent"):
        out += [f"**Most recent records for `{_md(last['label'])}`** (PubMed sort by publication date)", ""]
        for r in sec["recent"]:
            out.append(f"- {_trim(r['title'], 140)} *{_md(r['journal'])}*, {_md(r['pubdate'])}. "
                       f"[PMID {r['pmid']}](https://pubmed.ncbi.nlm.nih.gov/{r['pmid']}/)")
        out.append("")
    return out


def ot_section(sec: dict) -> list[str]:
    out = ["## 3. Targets and drugs (Open Targets Platform)", ""]
    if sec.get("error"):
        return out + _failed(sec["error"])
    s = sec["summary"]
    out += [f"Disease matched: **{_md(s['name'])}** (`{s['id']}`), {sec['match_note']}. "
            f"Platform data version {s['data_version'] or 'not reported'}. Retrieved {sec['fetched_at']}.", ""]
    if sec.get("alternatives"):
        alts = ", ".join(f"{_md(a['name'])} (`{a['id']}`)" for a in sec["alternatives"])
        out += [f"Other search hits: {alts}. Rerun with `--efo <ID>` if the match is wrong.", ""]
    out += [_check("drugs", s["drugs_total"], len(s["drugs"]), "reported count", "rows fetched"), ""]
    out += [f"**Top {len(s['targets'])} of {s['targets_total']} associated targets** by overall association score "
            "(0 to 1). The score summarises evidence for a target-disease link. It is not a measure of druggability "
            "or of any treatment effect.", "",
            "| Target | Name | Score |", "|---|---|---:|"]
    for t in s["targets"]:
        score = "" if t["score"] is None else f"{t['score']:.3f}"
        out.append(f"| {_md(t['symbol'])} | {_trim(t['name'], 60)} | {score} |")
    out.append("")
    out += [f"**Drugs and clinical candidates: {len(s['drugs'])}**, by maximum clinical stage as reported by "
            "Open Targets for this disease.", "", "| Stage | Drugs |", "|---|---:|"]
    from .analyse import stage_rank
    for stage, n in sorted(s["by_stage"].items(), key=lambda kv: stage_rank(kv[0])):
        out.append(f"| {_md(stage)} | {n} |")
    out.append("")
    if s["drugs"]:
        out += ["| Drug | Type | Max stage | ChEMBL |", "|---|---|---|---|"]
        for d in s["drugs"]:
            out.append(f"| {_md(d['name'])} | {_md(d['type'])} | {_md(d['stage'])} | {_md(d['chembl'])} |")
        out.append("")
    return out


LIMITATIONS = """## Limitations

- Every count depends on the query wording shown above. A different synonym or gene spelling gives different numbers.
- ClinicalTrials.gov lists registered studies. It is not a complete development pipeline, and statuses depend on sponsors updating their records.
- PubMed counts records, not distinct findings. A record whose print and electronic publication dates fall in different years can count in both years, so the yearly counts can add up to more than the whole-range count.
- Open Targets association scores weigh evidence for a link between a target and a disease. They say nothing about whether a drug works. Drug stages come from the Open Targets data release shown above and can lag the registries.
- This report is for orientation. It is not medical advice or investment advice.

Data sources: ClinicalTrials.gov (U.S. National Library of Medicine), PubMed via NCBI E-utilities, and the Open Targets Platform. This tool is not affiliated with or endorsed by any of them.
"""


def render(inputs: dict, trials: dict, pubmed: dict, ot: dict, generated_at: str) -> str:
    gene = f", gene `{_md(inputs['gene'])}`" if inputs.get("gene") else ""
    out = [f"# Disease snapshot: {_md(inputs['disease'])}", "",
           f"Inputs: disease `{_md(inputs['disease'])}`{gene}, publications from {inputs['since']}. "
           f"Generated {generated_at} by disease-snapshot v{__version__}. Raw responses are in `raw/`.", ""]
    out += trials_section(trials) + pubmed_section(pubmed) + ot_section(ot)
    out.append(LIMITATIONS)
    return "\n".join(out)
