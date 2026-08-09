"""One-off sizing check: how big would a neurobiology/neurosurgery corpus be
next to what we already have for surgery? Count-only queries (esearch with
retmax=0), no fetching/embedding/writing anywhere - purely informational.
Run: uv run python scratch/check_neuro_scope.py
"""
import datetime
import sys

sys.path.insert(0, ".")

import requests

from clients.pubmed_client import esearch_history
from core.config import PUBMED_QUERY as SURGERY_QUERY

# Narrow: clinically/translationally adjacent to neurosurgery - what a
# neurosurgeon would actually care about, not basic molecular neuroscience.
NEURO_NARROW = (
    '("Neurosurgical Procedures"[MeSH] '
    'OR "Neurosurgery"[MeSH] '
    'OR "Craniocerebral Trauma"[MeSH] '
    'OR "Brain Injuries"[MeSH] '
    'OR "Spinal Cord Injuries"[MeSH] '
    'OR "Brain Neoplasms"[MeSH] '
    'OR "Intracranial Hemorrhages"[MeSH] '
    'OR "Neuronal Plasticity"[MeSH] '
    'OR "Drug Resistant Epilepsy"[MeSH] '
    'OR "Stroke"[MeSH]) '
    'NOT "Retracted Publication"[pt]'
)

# Broad: general neuroscience, including basic/molecular research that has
# little to do with surgery in practice.
NEURO_BROAD = (
    '("Neurosciences"[MeSH] '
    'OR "Neurons"[MeSH] '
    'OR "Nervous System Physiological Phenomena"[MeSH] '
    'OR "Neuronal Plasticity"[MeSH] '
    'OR "Neurodegenerative Diseases"[MeSH] '
    'OR "Synaptic Transmission"[MeSH] '
    'OR "Neural Pathways"[MeSH] '
    'OR "Central Nervous System"[MeSH]) '
    'NOT "Retracted Publication"[pt]'
)

BIORXIV_API = "https://api.biorxiv.org/details/biorxiv"
NEURO_PREPRINT_TERMS = ["neuroscience", "neuron", "brain", "neural", "synap", "neurosurg"]


def window(days):
    today = datetime.date.today()
    return (today - datetime.timedelta(days=days)).strftime("%Y/%m/%d"), today.strftime("%Y/%m/%d")


def count_pubmed(query, days, label):
    mindate, maxdate = window(days)
    _, _, count = esearch_history(query, mindate=mindate, maxdate=maxdate, datetype="pdat")
    print(f"  {label:<28} last {days:>4}d: {count:>7,}")
    return count


def count_biorxiv_sample(days=14):
    """bioRxiv has no server-side keyword search - has to page through
    everything and filter client-side by title/abstract, like medrxiv_client
    does. Sampling a short window to estimate rate rather than paging months."""
    mindate, maxdate = window(days)
    mindate, maxdate = mindate.replace("/", "-"), maxdate.replace("/", "-")
    cursor, total_seen, neuro_matches, total_available = 0, 0, 0, None
    lower_terms = [t.lower() for t in NEURO_PREPRINT_TERMS]
    while True:
        url = f"{BIORXIV_API}/{mindate}/{maxdate}/{cursor}"
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as e:
            print(f"  bioRxiv API error at cursor {cursor}: {e}")
            break
        msg = (data.get("messages") or [{}])[0]
        total_available = int(msg.get("total", 0))
        collection = data.get("collection", [])
        if not collection:
            break
        total_seen += len(collection)
        for paper in collection:
            text = ((paper.get("title") or "") + " " + (paper.get("abstract") or "")).lower()
            if any(t in text for t in lower_terms):
                neuro_matches += 1
        cursor += len(collection)
        if cursor >= total_available or cursor > 6000:  # safety cap
            break
    return total_seen, neuro_matches, total_available


def main():
    print("=== PubMed MeSH counts (pdat, not edat - point-in-time sizing) ===\n")
    surgery_1y = count_pubmed(SURGERY_QUERY, 365, "surgery (current)")
    print()
    narrow_1y = count_pubmed(NEURO_NARROW, 365, "neuro NARROW")
    count_pubmed(NEURO_NARROW, 7, "neuro NARROW")
    print()
    broad_1y = count_pubmed(NEURO_BROAD, 365, "neuro BROAD")
    count_pubmed(NEURO_BROAD, 7, "neuro BROAD")
    print()

    overlap_query = f"({SURGERY_QUERY.rsplit('NOT', 1)[0]}) AND ({NEURO_NARROW.rsplit('NOT', 1)[0]})"
    overlap_1y = count_pubmed(overlap_query, 365, "overlap (surgery AND narrow)")

    print(f"\n=== Ratios (1-year window) ===")
    print(f"  neuro NARROW / surgery: {narrow_1y / surgery_1y:.2f}x")
    print(f"  neuro BROAD  / surgery: {broad_1y / surgery_1y:.2f}x")
    print(f"  overlap already in surgery corpus: {overlap_1y:,} articles "
          f"({overlap_1y / narrow_1y * 100:.1f}% of neuro NARROW)")

    print(f"\n=== bioRxiv preprints (14-day window, keyword match not MeSH) ===")
    seen, matched, total_available = count_biorxiv_sample(days=14)
    print(f"  {total_available} total preprints on bioRxiv in window, scanned {seen}, "
          f"{matched} neuro-keyword matches (~{matched/14:.1f}/day, "
          f"~{total_available/14:.0f}/day all categories)")
    print("  note: medRxiv (clinical preprints) is already wired up; bioRxiv (basic-science "
          "preprints, more common for neuroscience) is not - this is a candidate new source, "
          "not yet integrated.")


if __name__ == "__main__":
    main()
