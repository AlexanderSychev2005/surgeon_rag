from qdrant_setup import get_client
from config import QDRANT_COLLECTION
from qdrant_client.models import Filter, FieldCondition, MatchValue, PointStruct
from logsetup import get_logger

log = get_logger("backfill_payload")
client = get_client()

offset = None
updated = 0
while True:
    points, offset = client.scroll(
        collection_name=QDRANT_COLLECTION,
        limit=500,
        offset=offset,
        with_payload=True,
        with_vectors=False
    )
    if not points:
        break
        
    for p in points:
        if "doc_type" not in p.payload:
            client.set_payload(
                collection_name=QDRANT_COLLECTION,
                payload={"doc_type": "pubmed_article"},
                points=[p.id]
            )
            updated += 1
            if updated % 1000 == 0:
                print(f"Updated {updated} points...")

    if offset is None:
        break

print(f"Done. Updated {updated} points with doc_type.")
