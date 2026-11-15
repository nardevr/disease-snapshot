import gzip
import json

import pytest
import requests

from disease_snapshot import analyse as A
from disease_snapshot import cli
from disease_snapshot.fetch import Client, FetchError, Recorder
from disease_snapshot.render import render

from conftest import DISEASE_PAGE1, DISEASE_PAGE2, FakeResponse, FakeSession, load, study


def client(tmp_path, session=None):
    return Client(Recorder(tmp_path), session=session or FakeSession(), sleep=lambda s: None)


# ---- analyse ---------------------------------------------------------------

def test_trials_summary_counts_and_dedupes():
    s = A.trials_summary(DISEASE_PAGE1 + DISEASE_PAGE2)
    assert s["n"] == 3 and s["duplicates_dropped"] == 1
    assert s["by_status"] == {"RECRUITING": 1, "COMPLETED": 1, "TERMINATED": 1}
    assert s["by_phase"] == {"PHASE1/PHASE2": 1, "NA": 1, "PHASE3": 1}
    assert s["by_sponsor_class"] == {"INDUSTRY": 2, "OTHER": 1}
    assert s["n_active"] == 1


def test_study_row_tolerates_missing_modules():
    r = A.study_row({"protocolSection": {"identificationModule": {"nctId": "NCT1"}}})
    assert r["status"] == "UNKNOWN" and r["phase"] == "NA" and r["sponsor_class"] == "UNKNOWN"
    assert r["interventions"] == []


def test_interventional_table_newest_first_and_excludes_observational():
    rows = A.interventional_table(A.trials_summary(DISEASE_PAGE1 + DISEASE_PAGE2))
    assert [r["nct_id"] for r in rows] == ["NCT90000001", "NCT90000003"]


def test_year_and_range_terms():
    assert A.year_terms("x", 2024, 2025) == [(2024, "(x) AND 2024[dp]"), (2025, "(x) AND 2025[dp]")]
    assert A.range_term("x", 2024, 2026) == '(x) AND ("2024"[dp] : "2026"[dp])'


def test_resolve_disease_returns_top_hit_and_alternatives():
    chosen, alts = A.resolve_disease(load("ot_search.json")["data"])
    assert chosen["id"] == "MONDO_0005021"
    assert [a["id"] for a in alts] == ["MONDO_0016333", "MONDO_0700335"]


def test_resolve_disease_no_hits():
    assert A.resolve_disease({"search": {"hits": []}}) == (None, [])


def test_ot_summary_from_real_fixture():
    s = A.ot_summary(load("ot_disease.json")["data"])
    assert s["id"] == "MONDO_0005021" and s["targets_total"] == 6187
    assert [t["symbol"] for t in s["targets"]] == ["LMNA", "TTN", "DES", "RBM20", "MYH7"]
    assert s["drugs_total"] == 29 and len(s["drugs"]) == 29
    assert sum(s["by_stage"].values()) == 29
    assert s["by_stage"]["PHASE_3"] == 8 and s["by_stage"]["UNKNOWN"] == 7
    assert s["drugs"][0]["stage"] == "PHASE_3"  # most advanced first
    assert s["drugs"][-1]["stage"] == "UNKNOWN"
    assert s["data_version"] == "26.09"


def test_stage_rank_unknown_value_sorts_last():
    assert A.stage_rank("SOMETHING_NEW") > A.stage_rank("UNKNOWN") > A.stage_rank("PHASE_3")


# ---- fetch -------------------------------------------------------------------

def test_ct_paging_and_raw_saves(tmp_path):
    c = client(tmp_path)
    studies, total = c.ct_studies("dilated cardiomyopathy", None, "disease")
    assert total == 3 and len(studies) == 4
    manifest = json.loads((tmp_path / "raw" / "manifest.json").read_text())
    assert [m["file"] for m in manifest] == ["001_ct_disease_p1.json.gz", "002_ct_disease_p2.json.gz"]
    assert manifest[1]["params"]["pageToken"] == "tok2"
    with gzip.open(tmp_path / "raw" / manifest[0]["file"], "rt") as fh:
        assert json.load(fh)["totalCount"] == 3


def test_pubmed_email_never_written_to_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("DS_CONTACT_EMAIL", "someone@example.com")
    s = FakeSession()
    c = client(tmp_path, s)
    c.pubmed_count('"x"[Title/Abstract]', "t")
    assert s.calls[0][2]["email"] == "someone@example.com"  # sent to NCBI
    assert "example.com" not in (tmp_path / "raw" / "manifest.json").read_text()


def test_retry_then_fail_is_fetch_error(tmp_path):
    waits = []
    c = Client(Recorder(tmp_path), session=FakeSession(fail_hosts=["opentargets"]), sleep=waits.append)
    with pytest.raises(FetchError, match="HTTP 500"):
        c.ot("query { x }", {}, "x")
    assert waits == [1, 2, 4]


def test_client_error_is_not_retried(tmp_path):
    class S(FakeSession):
        def request(self, *a, **k):
            self.calls.append(a)
            return FakeResponse(400, {})
    s = S()
    c = Client(Recorder(tmp_path), session=s, sleep=lambda x: None)
    with pytest.raises(FetchError, match="HTTP 400"):
        c.ct_studies("x", None, "d")
    assert len(s.calls) == 1


def test_bad_json_is_fetch_error(tmp_path):
    class S(FakeSession):
        def request(self, *a, **k):
            return FakeResponse(200, ValueError("not json"))
    c = Client(Recorder(tmp_path), session=S(), sleep=lambda x: None)
    with pytest.raises(FetchError):
        c.pubmed_count("x", "t")


def test_connection_error_is_fetch_error(tmp_path):
    class S(FakeSession):
        def request(self, *a, **k):
            raise requests.ConnectionError("down")
    c = Client(Recorder(tmp_path), session=S(), sleep=lambda x: None)
    with pytest.raises(FetchError, match="ConnectionError"):
        c.pubmed_count("x", "t")


def test_graphql_errors_raise(tmp_path):
    class S(FakeSession):
        def request(self, *a, **k):
            return FakeResponse(200, {"errors": [{"message": "Cannot query field"}]})
    c = Client(Recorder(tmp_path), session=S(), sleep=lambda x: None)
    with pytest.raises(FetchError, match="Cannot query field"):
        c.ot("query { x }", {}, "x")


# ---- end to end ------------------------------------------------------------

def run(tmp_path, *extra, session=None):
    s = session or FakeSession()
    code = cli.main(["--disease", "dilated cardiomyopathy", "--gene", "LMNA", "--since", "2024",
                     "--out", str(tmp_path), *extra],
                    client_factory=lambda rec: Client(rec, session=s, sleep=lambda x: None))
    return code, (tmp_path / "report.md").read_text(), s


def test_end_to_end_report(tmp_path):
    code, md, _ = run(tmp_path)
    assert code == 0
    assert "(disease query): registry totalCount 3, unique studies fetched 3. match." in md
    assert "1 repeated record(s) across pages were counted once." in md
    assert "Studies registered for the condition: **3**" in md
    assert "Studies that also mention `LMNA`: 2" in md
    assert "[NCT90000001](https://clinicaltrials.gov/study/NCT90000001)" in md
    assert "(dilated cardiomyopathy): sum of yearly counts 300, count for the whole range 300. match" in md
    assert "sum of yearly counts 21, count for the whole range 22. **MISMATCH" in md
    assert "`MONDO_0005021`), top search hit" in md
    assert "Other search hits: familial dilated cardiomyopathy" in md
    assert "reported count 29, rows fetched 29. match" in md
    assert "| LMNA | lamin A/C | 0.903 |" in md
    assert "PMID 99000001" in md
    assert "## Limitations" in md and "not medical advice or investment advice" in md
    assert "Section failed" not in md


def test_efo_override_skips_search(tmp_path):
    code, md, s = run(tmp_path, "--efo", "MONDO_0005021")
    assert code == 0 and "set with --efo" in md
    assert not any(c[3] and "search(" in c[3]["query"] for c in s.calls)


def test_one_source_down_still_renders_others(tmp_path):
    code, md, _ = run(tmp_path, session=FakeSession(fail_hosts=["eutils"]))
    assert code == 1
    assert "## 2. Publications (PubMed)\n\n> **Section failed:**" in md
    assert "## 1. Registered studies" in md and "Section failed" not in md.split("## 2.")[0]
    assert "| LMNA | lamin A/C | 0.903 |" in md


def test_render_has_no_banned_claims(tmp_path):
    _, md, _ = run(tmp_path)
    low = md.lower()
    for phrase in ["safest", "most promising", "best target", "efficacy of", "will succeed", "recommend investing"]:
        assert phrase not in low


def test_since_out_of_range_rejected(tmp_path):
    with pytest.raises(SystemExit):
        cli.main(["--disease", "x", "--since", "1800", "--out", str(tmp_path)])


def test_render_escapes_pipes():
    sec = {"error": "a | b"}
    md = render({"disease": "x | y", "gene": None, "since": 2020}, sec, sec, sec, "t")
    assert "x / y" in md and "a / b" in md
