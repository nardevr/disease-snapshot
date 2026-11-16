"""Evidence only: show print and electronic dates for 5 records that match both 2016[dp] and 2017[dp].

Run from the repo root: python docs/evidence/pubmed_dp_overlap/mechanism.py <out_dir>
"""
import sys
from pathlib import Path

sys.path.insert(0, "src")
from disease_snapshot.fetch import Client, Recorder  # noqa: E402

c = Client(Recorder(Path(sys.argv[1])))
term = '("dilated cardiomyopathy"[Title/Abstract]) AND 2016[dp] AND 2017[dp]'
ids = c._pubmed("esearch", {"term": term, "retmax": 5}, "both_2016_2017_ids")["esearchresult"]["idlist"]
res = c._pubmed("esummary", {"id": ",".join(ids)}, "both_2016_2017_summary")["result"]
print(f"term: {term}")
print("PMID | pubdate | epubdate")
for uid in res["uids"]:
    print(f"{uid} | {res[uid].get('pubdate', '')} | {res[uid].get('epubdate', '')}")
