"""One-time historical backfill: page through the full result set for
SURGERY_MESH_QUERY within a date window via esearch history + efetch retstart,
ingesting (embed + upsert, with full-text resolution) as we go.

Bounded by pub_date (pdat), not edat - EDAT freshness only matters for the
separate daily incremental sync (see pubmed_client.esearch_pmids datetype='edat')."""
import sys
import time

from config import SURGERY_MESH_QUERY
from ingest import ingest_articles
from logsetup import get_logger
from pubmed_client import efetch_history_batch, esearch_history
from qdrant_setup import ensure_collection

log = get_logger(__name__)
BATCH_SIZE = 200


def count_window(mindate, maxdate):
    """Cheap: just asks how many articles match, doesn't fetch them."""
    _, _, count = esearch_history(SURGERY_MESH_QUERY, mindate=mindate, maxdate=maxdate)
    return count


def run_backfill(mindate, maxdate, limit=None, batch_size=BATCH_SIZE):
    client = ensure_collection()
    webenv, query_key, count = esearch_history(SURGERY_MESH_QUERY, mindate=mindate, maxdate=maxdate)
    total = min(count, limit) if limit else count
    log.info(f"backfill window {mindate}..{maxdate}: {count} total matches, processing {total}")

    written = 0
    start_time = time.time()
    for start in range(0, total, batch_size):
        retmax = min(batch_size, total - start)
        articles = efetch_history_batch(webenv, query_key, retstart=start, retmax=retmax)
        n_points, n_full, sources, ft_points = ingest_articles(client, articles)
        written += len(articles)
        elapsed = time.time() - start_time
        rate = written / elapsed if elapsed > 0 else 0
        log.info(f"backfill progress [{written}/{total}] +{n_points} points "
                 f"({n_full}/{len(articles)} full text) — {rate:.1f} articles/s")
    log.info(f"backfill done: wrote {written} articles from window {mindate}..{maxdate}")
    return written


def demo():
    checked, upgraded = None, None  # not applicable here
    n = run_backfill(mindate="2024/01/01", maxdate="2024/01/31", limit=10, batch_size=10)
    assert n == 10
    print(f"OK: backfilled {n} articles from a bounded test window")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["count", "run", "demo"])
    parser.add_argument("--mindate", default="2025/08/08")
    parser.add_argument("--maxdate", default="2026/08/08")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    if args.action == "count":
        print(count_window(args.mindate, args.maxdate))
    elif args.action == "run":
        run_backfill(mindate=args.mindate, maxdate=args.maxdate, limit=args.limit)
    else:
        demo()
