from qdrant_setup import get_client
from config import QDRANT_COLLECTION
from qdrant_client.models import Filter, FieldCondition, MatchValue

client = get_client()

points, _ = client.scroll(
    collection_name=QDRANT_COLLECTION,
    scroll_filter=Filter(must=[
        FieldCondition(key="doc_type", match=MatchValue(value="clinical_trial")),
        FieldCondition(key="section", match=MatchValue(value="abstract"))
    ]),
    limit=10,
    with_payload=["nctId", "title", "mesh_terms", "pub_types"]
)

print(f"Found {len(points)} sample trial points:\\n")
for p in points:
    print(f"NCT ID: {p.payload.get('nctId')}")
    print(f"Title: {p.payload.get('title')}")
    print(f"Conditions: {p.payload.get('mesh_terms')}")
    print("-" * 80)
