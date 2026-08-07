"""Daily incremental sync: read back the newest edat already in Qdrant,
pull everything PubMed has added since then (datetype=edat - catches
articles by indexing date, not publish date, so nothing is missed to
PubMed's own indexing lag), ingest it. Meant to run on a cron (see
.github/workflows/daily_sync.yml)."""
import datetime

from qdrant_client.models import Direction, FieldCondition, Filter, MatchValue, OrderBy

from config import QDRANT_COLLECTION, SURGERY_MESH_QUERY
from ingest import ingest_articles
from logsetup import get_logger
from pubmed_client import efetch_history_batch, esearch_history
from qdrant_setup import ensure_collection

log = get_logger(__name__)
BATCH_SIZE = 200
LOOKBACK_DAYS = 3  # overlap safety margin if a run was skipped/failed; upsert is idempotent


def get_watermark(client):
    points, _ = client.scroll(
        collection_name=QDRANT_COLLECTION,
        scroll_filter=Filter(must=[FieldCondition(key="section", match=MatchValue(value="abstract"))]),
        limit=1,
        order_by=OrderBy(key="edat", direction=Direction.DESC),
        with_payload=["edat"],
    )
    return points[0].payload.get("edat") if points else None


def run_sync():
    client = ensure_collection()
    watermark = get_watermark(client)
    anchor = datetime.date.fromisoformat(watermark) if watermark else datetime.date.today()
    mindate = (anchor - datetime.timedelta(days=LOOKBACK_DAYS)).strftime("%Y/%m/%d")
    maxdate = datetime.date.today().strftime("%Y/%m/%d")

    log.info(f"sync: watermark={watermark}, querying edat {mindate}..{maxdate}")
    webenv, query_key, count = esearch_history(
        SURGERY_MESH_QUERY, mindate=mindate, maxdate=maxdate, datetype="edat"
    )
    log.info(f"sync: {count} articles added to PubMed in window")

    written = 0
    for start in range(0, count, BATCH_SIZE):
        articles = efetch_history_batch(webenv, query_key, retstart=start, retmax=min(BATCH_SIZE, count - start))
        n_points, n_full = ingest_articles(client, articles)
        written += len(articles)
        log.info(f"sync progress [{written}/{count}] (+{n_points} points, {n_full} with full text)")

    log.info(f"sync done: {written} articles processed")
    return written


if __name__ == "__main__":
    n = run_sync()
    print(f"OK: sync processed {n} articles")
