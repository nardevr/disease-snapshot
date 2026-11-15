"""Pure functions that turn saved API responses into counts and tables. No network here."""
from __future__ import annotations

from collections import Counter

ACTIVE_STATUSES = {"RECRUITING", "NOT_YET_RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION"}

# Open Targets maxClinicalStage values, most advanced first. Unknown values sort last.
STAGE_ORDER = ["APPROVAL", "PHASE_4", "PHASE_3", "PHASE_2_3", "PHASE_2", "PHASE_1_2", "PHASE_1",
               "EARLY_PHASE_1", "PRECLINICAL", "UNKNOWN"]


def _get(d: dict, *path, default=None):
    for p in path:
        if not isinstance(d, dict):
            return default
        d = d.get(p)
    return default if d is None else d


def study_row(study: dict) -> dict:
    ps = study.get("protocolSection", {})
    phases = _get(ps, "designModule", "phases", default=[]) or []
    return {
        "nct_id": _get(ps, "identificationModule", "nctId", default=""),
        "title": _get(ps, "identificationModule", "briefTitle", default=""),
        "status": _get(ps, "statusModule", "overallStatus", default="UNKNOWN"),
        "start": _get(ps, "statusModule", "startDateStruct", "date", default=""),
        "study_type": _get(ps, "designModule", "studyType", default="UNKNOWN"),
        "phase": "/".join(phases) if phases else "NA",
        "sponsor": _get(ps, "sponsorCollaboratorsModule", "leadSponsor", "name", default=""),
        "sponsor_class": _get(ps, "sponsorCollaboratorsModule", "leadSponsor", "class", default="UNKNOWN"),
        "interventions": [i.get("name", "") for i in _get(ps, "armsInterventionsModule", "interventions", default=[]) or []],
    }


def trials_summary(studies: list[dict]) -> dict:
    rows = [study_row(s) for s in studies]
    # Count each NCT ID once, in case a page boundary repeats a study.
    seen, unique = set(), []
    for r in rows:
        if r["nct_id"] and r["nct_id"] in seen:
            continue
        seen.add(r["nct_id"])
        unique.append(r)
    return {
        "n": len(unique),
        "duplicates_dropped": len(rows) - len(unique),
        "by_status": Counter(r["status"] for r in unique),
        "by_phase": Counter(r["phase"] for r in unique),
        "by_type": Counter(r["study_type"] for r in unique),
        "by_sponsor_class": Counter(r["sponsor_class"] for r in unique),
        "n_active": sum(r["status"] in ACTIVE_STATUSES for r in unique),
        "rows": unique,
    }


def interventional_table(summary: dict) -> list[dict]:
    rows = [r for r in summary["rows"] if r["study_type"] == "INTERVENTIONAL"]
    return sorted(rows, key=lambda r: r["start"] or "", reverse=True)


def year_terms(base: str, since: int, until: int) -> list[tuple[int, str]]:
    return [(y, f"({base}) AND {y}[dp]") for y in range(since, until + 1)]


def range_term(base: str, since: int, until: int) -> str:
    return f'({base}) AND ("{since}"[dp] : "{until}"[dp])'


def resolve_disease(search_data: dict) -> tuple[dict | None, list[dict]]:
    hits = [h for h in _get(search_data, "search", "hits", default=[]) if h.get("entity") == "disease"]
    return (hits[0] if hits else None), hits[1:]


def stage_rank(stage: str) -> int:
    return STAGE_ORDER.index(stage) if stage in STAGE_ORDER else len(STAGE_ORDER)


def ot_summary(disease_data: dict) -> dict:
    d = disease_data.get("disease") or {}
    at = d.get("associatedTargets") or {}
    dc = d.get("drugAndClinicalCandidates") or {}
    targets = [{"symbol": _get(r, "target", "approvedSymbol", default=""),
                "name": _get(r, "target", "approvedName", default=""),
                "score": r.get("score")} for r in at.get("rows", [])]
    drugs = [{"name": _get(r, "drug", "name", default="(unnamed)"),
              "chembl": _get(r, "drug", "id", default=""),
              "type": _get(r, "drug", "drugType", default=""),
              "stage": r.get("maxClinicalStage", "UNKNOWN")} for r in dc.get("rows", [])]
    drugs.sort(key=lambda x: (stage_rank(x["stage"]), x["name"]))
    meta = disease_data.get("meta") or {}
    api = meta.get("apiVersion") or {}
    data = meta.get("dataVersion") or {}
    return {
        "id": d.get("id"), "name": d.get("name"),
        "targets_total": at.get("count"), "targets": targets,
        "drugs_total": dc.get("count"), "drugs": drugs,
        "by_stage": Counter(x["stage"] for x in drugs),
        "api_version": ".".join(str(api.get(k)) for k in ("x", "y", "z")) if api else "",
        "data_version": f"{data.get('year')}.{data.get('month')}" if data else "",
    }
