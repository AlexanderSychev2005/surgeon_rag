import sys
import time
import argparse
from typing import Optional

from core.config import SURGERY_MESH_QUERY
from ingestion.ingest import ingest_articles
from core.logsetup import get_logger
from clients.pubmed_client import efetch_history_batch, esearch_history
from core.qdrant_setup import ensure_collection

log = get_logger(__name__)
BATCH_SIZE = 200


def count_window(mindate: str, maxdate: str) -> int:
    _, _, count = esearch_history(SURGERY_MESH_QUERY, mindate=mindate, maxdate=maxdate)
    return count


def run_backfill(mindate: str, maxdate: str, limit: Optional[int] = None, batch_size: int = BATCH_SIZE) -> int:
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["count", "run"])
    parser.add_argument("--mindate", default="2025/08/08")
    parser.add_argument("--maxdate", default="2026/08/08")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    if args.action == "count":
        print(count_window(args.mindate, args.maxdate))
    elif args.action == "run":
        run_backfill(mindate=args.mindate, maxdate=args.maxdate, limit=args.limit)
