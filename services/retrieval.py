from typing import List, Dict, Any, Optional
from qdrant_client.models import Filter

from core.config import QDRANT_COLLECTION
from core.qdrant_setup import get_client
from services.embedder import embed_queries
from services.reranker import rerank


def retrieve(question: str, top_k: int = 8, candidate_pool: int = 100, qdrant_filter: Optional[Filter] = None) -> List[Dict[str, Any]]:
    client = get_client()
    query_vector = embed_queries([question])[0].tolist()

    hits = client.query_points(
        collection_name=QDRANT_COLLECTION,
        query=query_vector,
        limit=candidate_pool,
        query_filter=qdrant_filter,
        with_payload=True,
    ).points

    candidates = [{**h.payload, "score": h.score} for h in hits]
    return rerank(question, candidates, top_k=top_k)
