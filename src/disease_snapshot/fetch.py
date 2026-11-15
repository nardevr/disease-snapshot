"""Fetch data from ClinicalTrials.gov, PubMed and Open Targets.

Every response is saved gzipped under <out>/raw/ and logged in raw/manifest.json,
so any number in the report can be traced to a saved file.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import os
import time
from pathlib import Path

import requests

CT_URL = "https://clinicaltrials.gov/api/v2/studies"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
OT_URL = "https://api.platform.opentargets.org/api/v4/graphql"
USER_AGENT = "disease-snapshot/0.1 (+https://github.com/nardevr/disease-snapshot)"
CT_PAGE_SIZE = 1000
CT_MAX_PAGES = 10
PUBMED_MIN_INTERVAL = 0.34  # seconds, keeps us under 3 requests per second
RETRY_WAITS = (1, 2, 4)


class FetchError(RuntimeError):
    pass


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Recorder:
    """Saves raw responses and keeps a manifest."""

    def __init__(self, out_dir: Path):
        self.raw_dir = Path(out_dir) / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.entries: list[dict] = []

    def save(self, name: str, url: str, params: dict | None, payload: dict | str, body: object) -> str:
        fname = f"{len(self.entries) + 1:03d}_{name}.json.gz"
        with gzip.open(self.raw_dir / fname, "wt", encoding="utf-8") as fh:
            json.dump(body, fh)
        self.entries.append({"file": fname, "url": url, "params": params, "payload": payload, "fetched_at": now_utc()})
        self.write_manifest()
        return fname

    def write_manifest(self) -> None:
        (self.raw_dir / "manifest.json").write_text(json.dumps(self.entries, indent=2), encoding="utf-8")


class Client:
    def __init__(self, recorder: Recorder, session: requests.Session | None = None, sleep=time.sleep):
        self.rec = recorder
        self.s = session or requests.Session()
        self.s.headers.update({"User-Agent": USER_AGENT})
        self.sleep = sleep
        self._last_pubmed = 0.0

    def _request(self, method: str, url: str, **kw) -> dict:
        last_err = None
        for wait in (0,) + RETRY_WAITS:
            if wait:
                self.sleep(wait)
            try:
                r = self.s.request(method, url, timeout=60, **kw)
                if r.status_code == 200:
                    return r.json()
                last_err = f"HTTP {r.status_code}"
                if r.status_code < 500 and r.status_code != 429:
                    break  # client errors don't get better with retries
            except (requests.RequestException, ValueError) as e:
                last_err = type(e).__name__
        raise FetchError(f"{method} {url} failed: {last_err}")

    # ---- ClinicalTrials.gov -------------------------------------------------
    def ct_studies(self, cond: str, term: str | None, label: str) -> tuple[list[dict], int | None]:
        params = {"query.cond": cond, "pageSize": CT_PAGE_SIZE, "countTotal": "true", "format": "json"}
        if term:
            params["query.term"] = term
        studies: list[dict] = []
        total = None
        for page in range(CT_MAX_PAGES):
            body = self._request("GET", CT_URL, params=params)
            self.rec.save(f"ct_{label}_p{page + 1}", CT_URL, dict(params), "", body)
            if total is None:
                total = body.get("totalCount")
            studies.extend(body.get("studies", []))
            token = body.get("nextPageToken")
            if not token:
                break
            params["pageToken"] = token
        return studies, total

    # ---- PubMed -------------------------------------------------------------
    def _pubmed(self, endpoint: str, params: dict, label: str) -> dict:
        gap = time.monotonic() - self._last_pubmed
        if gap < PUBMED_MIN_INTERVAL:
            self.sleep(PUBMED_MIN_INTERVAL - gap)
        p = {"db": "pubmed", "retmode": "json", "tool": "disease-snapshot", **params}
        email = os.environ.get("DS_CONTACT_EMAIL")
        if email:
            p["email"] = email
        url = f"{EUTILS}/{endpoint}.fcgi"
        body = self._request("GET", url, params=p)
        self._last_pubmed = time.monotonic()
        logged = {k: v for k, v in p.items() if k != "email"}  # don't write the email into public files
        self.rec.save(f"pubmed_{label}", url, logged, "", body)
        return body

    def pubmed_count(self, term: str, label: str) -> int:
        body = self._pubmed("esearch", {"term": term, "retmax": 0}, label)
        try:
            return int(body["esearchresult"]["count"])
        except (KeyError, ValueError, TypeError) as e:
            raise FetchError(f"PubMed count missing for {label}") from e

    def pubmed_recent(self, term: str, n: int, label: str) -> list[dict]:
        body = self._pubmed("esearch", {"term": term, "retmax": n, "sort": "pub_date"}, f"{label}_ids")
        ids = body.get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []
        summ = self._pubmed("esummary", {"id": ",".join(ids)}, f"{label}_summary")
        res = summ.get("result", {})
        out = []
        for uid in res.get("uids", []):
            r = res.get(uid, {})
            out.append({"pmid": uid, "title": r.get("title", ""), "journal": r.get("source", ""),
                        "pubdate": r.get("pubdate", "")})
        return out

    # ---- Open Targets -------------------------------------------------------
    def ot(self, query: str, variables: dict, label: str) -> dict:
        payload = {"query": query, "variables": variables}
        body = self._request("POST", OT_URL, json=payload)
        self.rec.save(f"ot_{label}", OT_URL, None, payload, body)
        if body.get("errors"):
            raise FetchError(f"Open Targets error: {body['errors'][0].get('message', 'unknown')}")
        return body.get("data") or {}


OT_SEARCH = """query S($q: String!) {
  search(queryString: $q, entityNames: ["disease"], page: {index: 0, size: 5}) {
    hits { id name entity }
  }
}"""

OT_DISEASE = """query D($id: String!, $n: Int!) {
  meta { apiVersion { x y z } dataVersion { year month } }
  disease(efoId: $id) {
    id name
    associatedTargets(page: {index: 0, size: $n}) {
      count
      rows { score target { id approvedSymbol approvedName } }
    }
    drugAndClinicalCandidates {
      count
      rows { maxClinicalStage drug { id name drugType } }
    }
  }
}"""
