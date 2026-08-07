"""End-to-end retrieval: question -> MedCPT query embedding -> Qdrant ANN
(candidate pool) -> MedCPT cross-encoder rerank (precise top_k)."""
from config import QDRANT_COLLECTION
from embedder import embed_queries
from qdrant_setup import get_client
from reranker import rerank


def retrieve(question, top_k=8, candidate_pool=100, qdrant_filter=None):
    """qdrant_filter: optional qdrant_client.models.Filter, e.g. to boost/
    restrict by pub_types or mesh_terms before reranking even runs."""
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


def demo():
    question = "what are the risk factors for postoperative bleeding after liver transplant"
    results = retrieve(question, top_k=3, candidate_pool=50)
    assert results, "no candidates found - is the Qdrant collection populated?"
    for r in results:
        print(f"[{r['rerank_score']:.2f}] PMID {r['pmid']} — {r['title'][:70]}")
    print(f"OK: {len(results)} reranked results")


if __name__ == "__main__":
    demo()
