"""Offline test helpers.

Open Targets fixtures are real responses captured on 15 Nov 2026.
ClinicalTrials.gov and PubMed fixtures are synthetic, shaped like the public API
responses, with fake NCT IDs and PMIDs.
"""
import json
import re
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text())


def study(nct, title, status="RECRUITING", phases=("PHASE2",), stype="INTERVENTIONAL",
          sponsor="Example Bio", sclass="INDUSTRY", start="2024-01", interventions=("Drug A",)):
    ps = {
        "identificationModule": {"nctId": nct, "briefTitle": title},
        "statusModule": {"overallStatus": status, "startDateStruct": {"date": start}},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": sponsor, "class": sclass}},
        "designModule": {"studyType": stype},
        "armsInterventionsModule": {"interventions": [{"type": "DRUG", "name": i} for i in interventions]},
    }
    if phases is not None:
        ps["designModule"]["phases"] = list(phases)
    return {"protocolSection": ps}


DISEASE_PAGE1 = [
    study("NCT90000001", "Gene therapy in LMNA cardiomyopathy", phases=("PHASE1", "PHASE2"), start="2025-03"),
    study("NCT90000002", "Registry of dilated cardiomyopathy", status="COMPLETED", phases=None,
          stype="OBSERVATIONAL", sponsor="Example Hospital", sclass="OTHER", start="2019-06"),
]
DISEASE_PAGE2 = [
    study("NCT90000003", "Kinase inhibitor in LMNA DCM", status="TERMINATED", phases=("PHASE3",), start="2018-05"),
    study("NCT90000002", "Registry of dilated cardiomyopathy", status="COMPLETED", phases=None,
          stype="OBSERVATIONAL", sponsor="Example Hospital", sclass="OTHER", start="2019-06"),  # repeated on purpose
]
GENE_PAGE = [DISEASE_PAGE1[0], DISEASE_PAGE2[0]]

PUBMED_YEARLY = {"dcm": 100, "gene": 7}
PUBMED_RANGE_EXTRA = {"dcm": 0, "gene": 1}  # gene range total deliberately off by one to test the mismatch line


class FakeResponse:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class FakeSession:
    """Routes requests to fixtures. Set fail_hosts to make a source return HTTP 500."""

    def __init__(self, fail_hosts=()):
        self.headers = {}
        self.calls = []
        self.fail_hosts = set(fail_hosts)

    def request(self, method, url, timeout=None, params=None, json=None):
        self.calls.append((method, url, dict(params or {}), json))
        for h in self.fail_hosts:
            if h in url:
                return FakeResponse(500, {})
        if "clinicaltrials.gov" in url:
            return FakeResponse(200, self._ct(params))
        if "eutils" in url:
            return FakeResponse(200, self._pubmed(url, params))
        if "opentargets" in url:
            q = json["query"]
            return FakeResponse(200, load("ot_search.json") if "search(" in q else load("ot_disease.json"))
        raise AssertionError(f"unexpected URL {url}")

    def _ct(self, p):
        if p.get("query.term"):
            return {"totalCount": 2, "studies": GENE_PAGE}
        if p.get("pageToken") == "tok2":
            return {"studies": DISEASE_PAGE2}
        return {"totalCount": 3, "studies": DISEASE_PAGE1, "nextPageToken": "tok2"}

    def _pubmed(self, url, p):
        if url.endswith("esummary.fcgi"):
            ids = p["id"].split(",")
            res = {"uids": ids}
            for i in ids:
                res[i] = {"uid": i, "title": f"Synthetic paper {i}", "source": "J Example", "pubdate": "2026 Oct"}
            return {"result": res}
        term = p["term"]
        key = "gene" if "AND LMNA" in term else "dcm"
        if p.get("retmax"):
            return {"esearchresult": {"count": "2", "idlist": ["99000001", "99000002"]}}
        m = re.search(r'"(\d{4})"\[dp\] : "(\d{4})"\[dp\]', term)
        if m:
            years = int(m.group(2)) - int(m.group(1)) + 1
            return {"esearchresult": {"count": str(PUBMED_YEARLY[key] * years + PUBMED_RANGE_EXTRA[key])}}
        return {"esearchresult": {"count": str(PUBMED_YEARLY[key])}}


@pytest.fixture
def no_sleep():
    return lambda s: None
