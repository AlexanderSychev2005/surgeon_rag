import datetime
import argparse
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Direction, FieldCondition, Filter, MatchValue, OrderBy

from core.config import QDRANT_COLLECTION, COMBINED_PUBMED_QUERY, PUBMED_QUERY, NEURO_NARROW_QUERY
from ingestion.ingest import ingest_articles
from core.logsetup import get_logger, record_event
from clients.pubmed_client import efetch_history_batch, esearch_history, esearch_pmids
from core.qdrant_setup import ensure_collection
from clients.clinicaltrials_client import search_ct_history, parse_ct_study
from ingestion.ingest_ct import ingest_trials
from clients.medrxiv_client import fetch_medrxiv_history, parse_medrxiv_paper
from clients.biorxiv_client import fetch_biorxiv_history, parse_biorxiv_paper
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

    # Domain membership by which query actually matched the PMID (PubMed's own
    # MeSH tree explosion), not by re-checking the article's own mesh_terms
    # against our flat term lists after the fact - a term like "Osteotomy" is
    # what gets indexed on the article, but it only matches our search because
    # it's a *narrower* MeSH term under "Surgical Procedures, Operative"; a
    # literal string match against our term list misses that relationship
    # entirely (found this the hard way: ~half the corpus came back untagged).
    surgery_ids = set(esearch_pmids(PUBMED_QUERY, retmax=20000, mindate=mindate, maxdate=maxdate, datetype="edat"))
    neuro_ids = set(esearch_pmids(NEURO_NARROW_QUERY, retmax=20000, mindate=mindate, maxdate=maxdate, datetype="edat"))
    log.info(f"sync: domain membership - surgery={len(surgery_ids)}, neurobiology={len(neuro_ids)}, "
             f"overlap={len(surgery_ids & neuro_ids)}")

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
        for article in articles:
            pmid = article["pmid"]
            domains = []
            if pmid in surgery_ids:
                domains.append("surgery")
            if pmid in neuro_ids:
                domains.append("neurobiology")
            if not domains:
                log.warning(f"pmid={pmid} matched combined query but neither domain sub-query - check date/window consistency")
            article["domains"] = domains
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
    
    papers = fetch_medrxiv_history(mindate, maxdate)
    parsed_papers = [parse_medrxiv_paper(p) for p in papers]
    
    if limit:
        parsed_papers = parsed_papers[:limit]
        
    n_points, n_papers = ingest_preprints(client, parsed_papers)
    
    log.info(f"sync medRxiv done: {n_papers} preprints processed")
    record_event(
        "sync_medrxiv", window=f"{mindate}..{maxdate}", watermark=watermark, 
        preprints_written=n_papers, points_written=n_points
    )
    return n_papers


def get_watermark_biorxiv(client: QdrantClient) -> Optional[str]:
    points, _ = client.scroll(
        collection_name=QDRANT_COLLECTION,
        scroll_filter=Filter(must=[
            FieldCondition(key="section", match=MatchValue(value="abstract")),
            FieldCondition(key="doc_type", match=MatchValue(value="biorxiv_preprint"))
        ]),
        limit=1,
        order_by=OrderBy(key="edat", direction=Direction.DESC),
        with_payload=["edat"],
    )
    return points[0].payload.get("edat") if points else None


def run_sync_biorxiv(limit: Optional[int] = None, days: Optional[int] = None) -> int:
    client = ensure_collection()
    watermark = get_watermark_biorxiv(client)
    if days is not None:
        mindate = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    else:
        anchor = datetime.date.fromisoformat(watermark) if watermark else datetime.date.today()
        mindate = (anchor - datetime.timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    maxdate = datetime.date.today().strftime("%Y-%m-%d")

    log.info(f"sync bioRxiv: watermark={watermark}, querying {mindate}..{maxdate}")

    papers = fetch_biorxiv_history(mindate, maxdate)
    parsed_papers = [parse_biorxiv_paper(p) for p in papers]

    if limit:
        parsed_papers = parsed_papers[:limit]

    n_points, n_papers = ingest_preprints(client, parsed_papers, server="biorxiv")

    log.info(f"sync bioRxiv done: {n_papers} preprints processed")
    record_event(
        "sync_biorxiv", window=f"{mindate}..{maxdate}", watermark=watermark,
        preprints_written=n_papers, points_written=n_points
    )
    return n_papers


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="cap articles processed (quick tests)")
    parser.add_argument("--days", type=int, default=None, help="bootstrap window: today - days, ignores watermark")
    parser.add_argument("--ct-only", action="store_true", help="only sync clinical trials")
    parser.add_argument("--medrxiv-only", action="store_true", help="only sync medRxiv preprints")
    parser.add_argument("--biorxiv-only", action="store_true", help="only sync bioRxiv preprints")
    args = parser.parse_args()

    if args.ct_only:
        n_ct = run_sync_ct(limit=args.limit, days=args.days)
        print(f"OK: sync processed {n_ct} clinical trials")
    elif args.medrxiv_only:
        n_medrxiv = run_sync_medrxiv(limit=args.limit, days=args.days)
        print(f"OK: sync processed {n_medrxiv} medRxiv preprints")
    elif args.biorxiv_only:
        n_biorxiv = run_sync_biorxiv(limit=args.limit, days=args.days)
        print(f"OK: sync processed {n_biorxiv} bioRxiv preprints")
    else:
        # default run: PubMed + medRxiv only. CT.gov and bioRxiv didn't pan out
        # for RAG (see conversation) - kept available via --ct-only/--biorxiv-only
        # in case that changes, just not run automatically.
        n = run_sync(limit=args.limit, days=args.days)
        print(f"OK: sync processed {n} articles")

        n_medrxiv = run_sync_medrxiv(limit=args.limit, days=args.days)
        print(f"OK: sync processed {n_medrxiv} medRxiv preprints")
