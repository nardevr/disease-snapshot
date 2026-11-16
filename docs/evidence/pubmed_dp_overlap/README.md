# Evidence: PubMed yearly counts exceed the whole-range count

Run on 16 Nov 2026 (UTC 03:32 to 03:34), shortly after the live sample run of the same day (UTC 03:26 to 03:27). That sample run produced these cross-check lines:

- `"dilated cardiomyopathy"[Title/Abstract]`, 2016 to 2026: sum of yearly counts 10,298, whole-range count 9,162.
- `"dilated cardiomyopathy"[Title/Abstract] AND LMNA[Title/Abstract]`, 2016 to 2026: sum of yearly counts 391, whole-range count 360.

PubMed's `[dp]` (publication date) field matches both a record's print date and its electronic date. A record e-published in one year and printed in another matches two yearly queries but counts once in the range.

`dp_overlap.py` uses the project's own `Client` to count `(base) AND Y[dp] AND Z[dp]` for every pair of years Y < Z from 2016 to 2026. Results:

- dilated cardiomyopathy: records matching two years = **1,136 = 10,298 - 9,162**
- dilated cardiomyopathy + LMNA: records matching two years = **31 = 391 - 360**

Both gaps are fully accounted for. The 110 raw responses and `manifest.json` are in `dp_overlap_out/raw/`.

## Mechanism check (16 Nov 2026)

`mechanism.py` uses the project's own `Client`. It takes the first 5 PMIDs that match `("dilated cardiomyopathy"[Title/Abstract]) AND 2016[dp] AND 2017[dp]` (120 records in all, the same as the 2016 & 2017 pair count above) and fetches their esummary records. Raw responses are in `mechanism/raw/`.

| PMID | pubdate (print) | epubdate (electronic) |
|---|---|---|
| 28373784 | 2017 Apr | 2016 Mar 11 |
| 28318762 | 2017 May | 2016 Dec 29 |
| 28289596 | 2016 Dec 1 | 2017 Mar 8 |
| 29759522 | 2017 Mar | 2016 Dec 21 |
| 28148779 | 2017 Feb | 2016 Oct 25 |

In all 5 records the print and electronic years differ, one 2016 and the other 2017.

To reproduce, run `python docs/evidence/pubmed_dp_overlap/dp_overlap.py <out_dir>` or `python docs/evidence/pubmed_dp_overlap/mechanism.py <out_dir>` from the repo root. PubMed changes daily, so later counts may differ a little.
