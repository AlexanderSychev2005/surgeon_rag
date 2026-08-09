import datetime
import argparse
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Direction, FieldCondition, Filter, MatchValue, OrderBy

from core.config import QDRANT_COLLECTION, COMBINED_PUBMED_QUERY, MEDRXIV_CATEGORIES
from ingestion.ingest import ingest_articles
from core.logsetup import get_logger, record_event
from clients.pubmed_client import efetch_history_batch, esearch_history
from core.qdrant_setup import ensure_collection
from clients.preprint_client import fetch_by_category, parse_preprint
from ingestion.ingest_medrxiv import ingest_preprints

log = get_logger(__name__)
BATCH_SIZE = 200
LOOKBACK_DAYS = 1


def get_watermark(client: QdrantClient) -> Optional[str]:
    points, _ = client.scroll(
        collection_name=QDRANT_COLLECTION,
        scroll_filter=Filter(must=[
            FieldCondition(key="section", match=MatchValue(value="abstract")),
            FieldCondition(key="doc_type", match=MatchValue(value="pubmed_article"))
        ]),
        limit=1,
        order_by=OrderBy(key="edat", direction=Direction.DESC),
        with_payload=["edat"],
    )
    return points[0].payload.get("edat") if points else None


def run_sync(limit: Optional[int] = None, days: Optional[int] = None) -> int:
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
        COMBINED_PUBMED_QUERY, mindate=mindate, maxdate=maxdate, datetype="edat"
    )
    total = min(count, limit) if limit else count
    log.info(f"sync: {count} articles added to PubMed in window, processing {total}")

    written, points_written, with_full_text = 0, 0, 0
    total_ft_points = 0
    total_sources = {}
    for start in range(0, total, BATCH_SIZE):
        retmax = min(BATCH_SIZE, total - start)
        articles = efetch_history_batch(webenv, query_key, retstart=start, retmax=retmax)
        n_points, n_full, s_counts, ft_points = ingest_articles(client, articles)
        written += len(articles)
        points_written += n_points
        with_full_text += n_full
        total_ft_points += ft_points
        for k, v in s_counts.items():
            total_sources[k] = total_sources.get(k, 0) + v
        log.info(f"sync progress [{written}/{total}] (+{n_points} points, {n_full} with full text)")

    log.info(f"sync done: {written} articles processed")
    record_event(
        "sync", window=f"{mindate}..{maxdate}", watermark=watermark, matched=count,
        articles_written=written, points_written=points_written, with_full_text=with_full_text,
        full_text_points=total_ft_points, sources=total_sources
    )
    return written


def get_watermark_medrxiv(client: QdrantClient) -> Optional[str]:
    points, _ = client.scroll(
        collection_name=QDRANT_COLLECTION,
        scroll_filter=Filter(must=[
            FieldCondition(key="section", match=MatchValue(value="abstract")),
            FieldCondition(key="doc_type", match=MatchValue(value="medrxiv_preprint"))
        ]),
        limit=1,
        order_by=OrderBy(key="edat", direction=Direction.DESC),
        with_payload=["edat"],
    )
    return points[0].payload.get("edat") if points else None


def run_sync_medrxiv(limit: Optional[int] = None, days: Optional[int] = None) -> int:
    client = ensure_collection()
    watermark = get_watermark_medrxiv(client)
    if days is not None:
        mindate = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    else:
        anchor = datetime.date.fromisoformat(watermark) if watermark else datetime.date.today()
        mindate = (anchor - datetime.timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    maxdate = datetime.date.today().strftime("%Y-%m-%d")

    log.info(f"sync medRxiv: watermark={watermark}, querying {mindate}..{maxdate}")

    papers = fetch_by_category(mindate, maxdate, MEDRXIV_CATEGORIES)
    parsed_papers = [parse_preprint(p) for p in papers]

    if limit:
        parsed_papers = parsed_papers[:limit]

    n_points, n_papers = ingest_preprints(client, parsed_papers)

    log.info(f"sync medRxiv done: {n_papers} preprints processed")
    record_event(
        "sync_medrxiv", window=f"{mindate}..{maxdate}", watermark=watermark,
        preprints_written=n_papers, points_written=n_points
    )
    return n_papers


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="cap articles processed (quick tests)")
    parser.add_argument("--days", type=int, default=None, help="bootstrap window: today - days, ignores watermark")
    parser.add_argument("--medrxiv-only", action="store_true", help="only sync medRxiv preprints")
    args = parser.parse_args()

    if args.medrxiv_only:
        n_medrxiv = run_sync_medrxiv(limit=args.limit, days=args.days)
        print(f"OK: sync processed {n_medrxiv} medRxiv preprints")
    else:
        n = run_sync(limit=args.limit, days=args.days)
        print(f"OK: sync processed {n} articles")

        n_medrxiv = run_sync_medrxiv(limit=args.limit, days=args.days)
        print(f"OK: sync processed {n_medrxiv} medRxiv preprints")
