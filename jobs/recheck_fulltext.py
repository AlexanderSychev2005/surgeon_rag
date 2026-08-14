import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Tuple, Optional

from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
)

from core.config import QDRANT_COLLECTION, NAMESPACE
from core.chunking import chunk_text
from services.embedder import embed_articles
from services.fulltext import get_full_text
from ingestion.ingest import FULLTEXT_WORKERS, UPSERT_BATCH
from core.logsetup import get_logger, record_event
from core.qdrant_setup import get_client, scroll_with_retry

log = get_logger(__name__)

PENDING_FILTER = Filter(
    must=[
        FieldCondition(key="section", match=MatchValue(value="abstract")),
        FieldCondition(key="has_full_text", match=MatchValue(value=False)),
        # PubMed only: this uses get_full_text (PMC/Europe PMC/Unpaywall by
        # pmcid/doi), which doesn't understand preprint DOIs and would try to
        # build a point id from payload["pmid"], a field medRxiv/bioRxiv
        # points don't have at all - a medRxiv-specific recheck (its own PDF
        # fetch, see ingestion/ingest_medrxiv.py) doesn't exist yet.
        FieldCondition(key="doc_type", match=MatchValue(value="pubmed_article")),
    ]
)


def recheck(batch_size: int = 50, max_batches: Optional[int] = None) -> Tuple[int, int]:
    client = get_client()
    upgraded, checked, offset, batches = 0, 0, None, 0
    source_counts = {}
    ft_points = 0

    while True:
        points, offset = scroll_with_retry(
            client,
            collection_name=QDRANT_COLLECTION,
            scroll_filter=PENDING_FILTER,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        if not points:
            break

        with ThreadPoolExecutor(max_workers=FULLTEXT_WORKERS) as pool:
            full_text_results = list(pool.map(
                lambda p: get_full_text(pmcid=p.payload.get("pmcid"), doi=p.payload.get("doi")), points
            ))

        new_points = []
        for point, (full_text, source) in zip(points, full_text_results):
            checked += 1
            payload = point.payload
            if not full_text:
                continue
                
            source_counts[source] = source_counts.get(source, 0) + 1

            chunks = chunk_text(full_text)
            ft_points += len(chunks)
            pairs = [[payload["title"], c] for c in chunks]
            vectors = embed_articles(pairs)
            for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
                cid = str(uuid.uuid5(NAMESPACE, f"pmid:{payload['pmid']}:fulltext_{i}"))
                new_points.append(PointStruct(
                    id=cid,
                    vector=vector.tolist(),
                    payload={**payload, "section": f"fulltext_{i}", "text": chunk,
                              "has_full_text": True, "source": source},
                ))
            new_points.append(PointStruct(
                id=point.id, vector=point.vector, payload={**payload, "has_full_text": True},
            ))
            upgraded += 1
            log.info(f"recheck upgraded pmid={payload['pmid']} title={payload['title'][:60]!r} "
                      f"via {source} ({len(chunks)} chunks)")

        for i in range(0, len(new_points), UPSERT_BATCH):
            client.upsert(collection_name=QDRANT_COLLECTION, points=new_points[i:i + UPSERT_BATCH])

        batches += 1
        log.info(f"recheck batch {batches}: checked {checked} so far, {upgraded} upgraded")
        if offset is None or (max_batches and batches >= max_batches):
            break

    log.info(f"recheck done: checked {checked}, upgraded {upgraded}")
    record_event("recheck", checked=checked, upgraded=upgraded, sources=source_counts, full_text_points=ft_points)
    return checked, upgraded


if __name__ == "__main__":
    checked, upgraded = recheck(batch_size=50)
    print(f"OK: checked {checked} pending docs, upgraded {upgraded} to full text")
