import datetime
import argparse
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Direction, FieldCondition, Filter, MatchValue, OrderBy

from core.config import QDRANT_COLLECTION, SURGERY_MESH_QUERY
from ingestion.ingest import ingest_articles
from core.logsetup import get_logger, record_event
from clients.pubmed_client import efetch_history_batch, esearch_history
from core.qdrant_setup import ensure_collection
from clients.clinicaltrials_client import search_ct_history, parse_ct_study
from ingestion.ingest_ct import ingest_trials

log = get_logger(__name__)
BATCH_SIZE = 200
LOOKBACK_DAYS = 1


def get_watermark(client: QdrantClient) -> Optional[str]:
    points, _ = client.scroll(
        collection_name=QDRANT_COLLECTION,
        scroll_filter=Filter(must=[FieldCondition(key="section", match=MatchValue(value="abstract"))]),
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
        SURGERY_MESH_QUERY, mindate=mindate, maxdate=maxdate, datetype="edat"
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


def get_watermark_ct(client: QdrantClient) -> Optional[str]:
    points, _ = client.scroll(
        collection_name=QDRANT_COLLECTION,
        scroll_filter=Filter(must=[
            FieldCondition(key="section", match=MatchValue(value="abstract")),
            FieldCondition(key="doc_type", match=MatchValue(value="clinical_trial"))
        ]),
        limit=1,
        order_by=OrderBy(key="edat", direction=Direction.DESC),
        with_payload=["edat"],
    )
    return points[0].payload.get("edat") if points else None


def run_sync_ct(limit: Optional[int] = None, days: Optional[int] = None) -> int:
    client = ensure_collection()
    watermark = get_watermark_ct(client)
    if days is not None:
        mindate = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    else:
        anchor = datetime.date.fromisoformat(watermark) if watermark else datetime.date.today()
        mindate = (anchor - datetime.timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    maxdate = datetime.date.today().strftime("%Y-%m-%d")

    log.info(f"sync CT: watermark={watermark}, querying {mindate}..{maxdate}")
    
    page_token = None
    total_written = 0
    total_points = 0
    
    while True:
        studies, next_page = search_ct_history(mindate, maxdate, page_token=page_token)
        if not studies:
            break
            
        if limit and total_written >= limit:
            break
            
        parsed_trials = [parse_ct_study(s) for s in studies]
        if limit:
            parsed_trials = parsed_trials[:limit - total_written]
            
        n_points, n_trials = ingest_trials(client, parsed_trials)
        total_written += n_trials
        total_points += n_points
        
        log.info(f"sync CT progress: +{n_points} points for {n_trials} trials")
        
        page_token = next_page
        if not page_token:
            break

    log.info(f"sync CT done: {total_written} trials processed")
    record_event(
        "sync_ct", window=f"{mindate}..{maxdate}", watermark=watermark, 
        trials_written=total_written, points_written=total_points
    )
    return total_written


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="cap articles processed (quick tests)")
    parser.add_argument("--days", type=int, default=None, help="bootstrap window: today - days, ignores watermark")
    parser.add_argument("--ct-only", action="store_true", help="only sync clinical trials")
    args = parser.parse_args()
    
    if not args.ct_only:
        n = run_sync(limit=args.limit, days=args.days)
        print(f"OK: sync processed {n} articles")
        
    n_ct = run_sync_ct(limit=args.limit, days=args.days)
    print(f"OK: sync processed {n_ct} clinical trials")
