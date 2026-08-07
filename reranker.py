"""MedCPT-Cross-Encoder: second-stage reranker. Unlike the bi-encoder, this
reads the query and a candidate document TOGETHER (full cross-attention), so
it can't be precomputed/indexed - only run on the small shortlist Qdrant's
ANN search already narrowed down."""
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

_NAME = "ncbi/MedCPT-Cross-Encoder"
_cache = {}


def _load():
    if _NAME not in _cache:
        tok = AutoTokenizer.from_pretrained(_NAME)
        model = AutoModelForSequenceClassification.from_pretrained(_NAME)
        model.eval()
        _cache[_NAME] = (tok, model)
    return _cache[_NAME]


@torch.no_grad()
def rerank(query, candidates, top_k=8, batch_size=16):
    """candidates: list of dicts with at least 'title' and 'text' (payload
    from a Qdrant hit). Returns the same dicts, sliced to top_k, sorted by
    cross-encoder score desc, each with a 'rerank_score' field added.

    Mini-batched for the same reason as embedder.embed_articles: a full
    candidate_pool (e.g. 100) run through cross-attention in one forward
    pass risks a multi-GB single allocation on CPU."""
    if not candidates:
        return []
    tok, model = _load()
    scores = []
    for i in range(0, len(candidates), batch_size):
        batch = candidates[i:i + batch_size]
        pairs = [[query, f"{c['title']}. {c['text']}"] for c in batch]
        encoded = tok(pairs, truncation=True, padding=True, return_tensors="pt", max_length=512)
        batch_scores = model(**encoded).logits.squeeze(dim=1).tolist()
        scores.extend(batch_scores if isinstance(batch_scores, list) else [batch_scores])
    scored = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
    return [{**c, "rerank_score": s} for c, s in scored[:top_k]]


def demo():
    query = "risk factors for postoperative bleeding after laparoscopic cholecystectomy"
    candidates = [
        {"title": "Postoperative hemorrhage after laparoscopic cholecystectomy",
         "text": "This study reviews risk factors for postoperative bleeding following laparoscopic cholecystectomy, including anticoagulant use and cystic artery injury."},
        {"title": "Central diabetes insipidus diagnosis",
         "text": "Central diabetes insipidus is a rare endocrine condition caused by insufficient vasopressin secretion."},
    ]
    ranked = rerank(query, candidates, top_k=2)
    assert ranked[0]["title"].startswith("Postoperative hemorrhage")
    assert ranked[0]["rerank_score"] > ranked[1]["rerank_score"]
    print(f"OK: top result {ranked[0]['title']!r} score={ranked[0]['rerank_score']:.2f} "
          f"> {ranked[1]['rerank_score']:.2f}")


if __name__ == "__main__":
    demo()
