"""Daily incremental sync: read back the newest edat already in Qdrant,
pull everything PubMed has added since then (datetype=edat - catches
articles by indexing date, not publish date, so nothing is missed to
PubMed's own indexing lag), ingest it. Meant to run on a cron (see
.github/workflows/daily_sync.yml)."""
import datetime

from qdrant_client.models import Direction, FieldCondition, Filter, MatchValue, OrderBy

from config import QDRANT_COLLECTION, SURGERY_MESH_QUERY
from ingest import ingest_articles
from logsetup import get_logger, record_event
from pubmed_client import efetch_history_batch, esearch_history
from qdrant_setup import ensure_collection

log = get_logger(__name__)
BATCH_SIZE = 200
LOOKBACK_DAYS = 1  # small overlap buffer (EDAT is day-granularity); upsert is
                    # idempotent so re-touching a day is harmless, but a wider
                    # margin means needlessly re-fetching/re-embedding articles
                    # already ingested on every single run


def get_watermark(client):
    points, _ = client.scroll(
        collection_name=QDRANT_COLLECTION,
        scroll_filter=Filter(must=[FieldCondition(key="section", match=MatchValue(value="abstract"))]),
        limit=1,
        order_by=OrderBy(key="edat", direction=Direction.DESC),
        with_payload=["edat"],
    )
    return points[0].payload.get("edat") if points else None


def run_sync(limit=None, days=None):
    """limit: cap the number of articles processed this run - handy for a
    quick test without waiting out a full window.
    days: override the window to `today - days`, ignoring the watermark -
    for bootstrapping a fresh collection where there's no watermark yet to
    follow. Normal incremental runs should leave this as None."""
    client = ensure_collection()
    watermark = get_watermark(client)
    if days is not None:
        mindate = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y/%m/%d")
    else:
        anchor = datetime.date.fromisoformat(watermark) if watermark else datetime.date.today()
        mindate = (anchor - datetime.timedelta(days=LOOKBACK_DAYS)).strftime("%Y/%m/%d")
    maxdate = datetime.date.today().strftime("%Y/%m/%d")

    log.info(f"sync: watermark={watermark}, querying edat {mindate}..{maxdate}")
    webenv, query_key, count = esearch_history(
        SURGERY_MESH_QUERY, mindate=mindate, maxdate=maxdate, datetype="edat"
    )
    total = min(count, limit) if limit else count
    log.info(f"sync: {count} articles added to PubMed in window, processing {total}")

    written, points_written, with_full_text = 0, 0, 0
    for start in range(0, total, BATCH_SIZE):
        retmax = min(BATCH_SIZE, total - start)
        articles = efetch_history_batch(webenv, query_key, retstart=start, retmax=retmax)
        n_points, n_full = ingest_articles(client, articles)
        written += len(articles)
        points_written += n_points
        with_full_text += n_full
        log.info(f"sync progress [{written}/{total}] (+{n_points} points, {n_full} with full text)")

    log.info(f"sync done: {written} articles processed")
    record_event(
        "sync", window=f"{mindate}..{maxdate}", watermark=watermark, matched=count,
        articles_written=written, points_written=points_written, with_full_text=with_full_text,
    )
    return written


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="cap articles processed (quick tests)")
    parser.add_argument("--days", type=int, default=None, help="bootstrap window: today - days, ignores watermark")
    args = parser.parse_args()
    n = run_sync(limit=args.limit, days=args.days)
    print(f"OK: sync processed {n} articles")
