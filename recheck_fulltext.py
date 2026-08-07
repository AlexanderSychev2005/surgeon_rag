"""Periodic job: some articles have no full text at ingest time because the
publisher's PMC deposit is embargoed (common: 6-12 months post-publication).
This scrolls Qdrant for abstract points still flagged has_full_text=false,
retries the resolution chain, and upserts newly-found full-text chunks."""
import uuid

from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
)

from config import QDRANT_COLLECTION
from chunking import chunk_text
from embedder import embed_articles
from fulltext import get_full_text
from ingest import UPSERT_BATCH
from logsetup import get_logger, record_event
from qdrant_setup import get_client

log = get_logger(__name__)
NAMESPACE = uuid.NAMESPACE_DNS

PENDING_FILTER = Filter(
    must=[
        FieldCondition(key="section", match=MatchValue(value="abstract")),
        FieldCondition(key="has_full_text", match=MatchValue(value=False)),
    ]
)


def recheck(batch_size=50, max_batches=None):
    client = get_client()
    upgraded, checked, offset, batches = 0, 0, None, 0

    while True:
        points, offset = client.scroll(
            collection_name=QDRANT_COLLECTION,
            scroll_filter=PENDING_FILTER,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        if not points:
            break

        new_points = []
        for point in points:
            checked += 1
            payload = point.payload
            full_text, source = get_full_text(pmcid=payload.get("pmcid"), doi=payload.get("doi"))
            if not full_text:
                continue

            chunks = chunk_text(full_text)
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
    record_event("recheck", checked=checked, upgraded=upgraded)
    return checked, upgraded


def demo():
    checked, upgraded = recheck(batch_size=50, max_batches=1)
    print(f"OK: checked {checked} pending docs, upgraded {upgraded} to full text")


if __name__ == "__main__":
    # full run (no max_batches cap) - this is what the daily cron calls
    checked, upgraded = recheck(batch_size=50)
    print(f"OK: checked {checked} pending docs, upgraded {upgraded} to full text")
