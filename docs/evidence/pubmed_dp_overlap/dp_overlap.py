"""Diagnostic only (not part of the repo): count PubMed records whose [dp] matches two different years."""
import sys
from pathlib import Path

sys.path.insert(0, "src")
from disease_snapshot.fetch import Client, Recorder  # noqa: E402

out = Path(sys.argv[1])
c = Client(Recorder(out))
bases = {"q1": '"dilated cardiomyopathy"[Title/Abstract]',
         "q2": '"dilated cardiomyopathy"[Title/Abstract] AND LMNA[Title/Abstract]'}
for q, base in bases.items():
    total = 0
    for y in range(2016, 2027):
        for z in range(y + 1, 2027):
            n = c.pubmed_count(f"({base}) AND {y}[dp] AND {z}[dp]", f"{q}_{y}_{z}")
            if n:
                print(f"{q} {y}&{z}: {n}")
            total += n
    print(f"{q} records counted in two years (sum over year pairs): {total}")
