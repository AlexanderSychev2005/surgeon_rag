import os
import time
from typing import Any, List, Optional, Tuple

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import Distance, PayloadSchemaType, Record, VectorParams

from core.config import QDRANT_COLLECTION, VECTOR_SIZE

load_dotenv()

INDEXED_FIELDS = {
    "doc_type": PayloadSchemaType.KEYWORD,
    "category": PayloadSchemaType.KEYWORD,
    "pmid": PayloadSchemaType.INTEGER,
    "pub_types": PayloadSchemaType.KEYWORD,
    "mesh_terms": PayloadSchemaType.KEYWORD,
    "edat": PayloadSchemaType.DATETIME,
    "pub_date": PayloadSchemaType.DATETIME,
    "journal": PayloadSchemaType.KEYWORD,
    "has_full_text": PayloadSchemaType.BOOL,
    "source": PayloadSchemaType.KEYWORD,
    "is_preprint": PayloadSchemaType.BOOL,
    "section": PayloadSchemaType.KEYWORD,
}


def get_client() -> QdrantClient:
    return QdrantClient(url=os.environ["QDRANT_URL"], api_key=os.environ["QDRANT_API_KEY"])


def scroll_with_retry(client: QdrantClient, max_retries: int = 3, **kwargs: Any) -> Tuple[List[Record], Optional[Any]]:
    """Retries on transient Qdrant Cloud 502s - same reasoning as the NCBI
    efetch retry (clients/pubmed_client.py): a same-call retry is enough,
    no rate limit involved."""
    for attempt in range(max_retries + 1):
        try:
            return client.scroll(**kwargs)
        except UnexpectedResponse:
            if attempt == max_retries:
                raise
            time.sleep(2 * (attempt + 1))


def ensure_collection() -> QdrantClient:
    client = get_client()
    if not client.collection_exists(QDRANT_COLLECTION):
        client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        print(f"created collection {QDRANT_COLLECTION!r}")
    else:
        print(f"collection {QDRANT_COLLECTION!r} already exists")

    for field, schema in INDEXED_FIELDS.items():
        client.create_payload_index(QDRANT_COLLECTION, field_name=field, field_schema=schema)
    print(f"payload indexes ensured: {list(INDEXED_FIELDS)}")
    return client


if __name__ == "__main__":
    client = ensure_collection()
    info = client.get_collection(QDRANT_COLLECTION)
    print(f"OK: collection status={info.status}, points={info.points_count}")
