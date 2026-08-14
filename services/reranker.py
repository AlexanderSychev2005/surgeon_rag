from functools import lru_cache

import torch
from typing import List, Dict, Any, Tuple
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from services.embedder import DEVICE, DTYPE

_NAME = "ncbi/MedCPT-Cross-Encoder"


@lru_cache(maxsize=1)
def _load() -> Tuple[Any, Any]:
    tok = AutoTokenizer.from_pretrained(_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(_NAME).to(DEVICE, dtype=DTYPE)
    model.eval()
    return tok, model


@torch.no_grad()
def rerank(query: str, candidates: List[Dict[str, Any]], top_k: int = 8, batch_size: int = 64) -> List[Dict[str, Any]]:
    if not candidates:
        return []
    tok, model = _load()
    scores = []
    for i in range(0, len(candidates), batch_size):
        batch = candidates[i:i + batch_size]
        pairs = [[query, f"{c['title']}. {c['text']}"] for c in batch]
        encoded = tok(pairs, truncation=True, padding=True, return_tensors="pt", max_length=512).to(DEVICE)
        batch_scores = model(**encoded).logits.float().squeeze(dim=1).cpu().tolist()
        scores.extend(batch_scores)
    scored = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)

    dedup_map = {}
    ordered_ids = []

    for c, s in scored:
        doc_id = c.get('pmid') or c.get('doi') or c.get('title')
        if doc_id not in dedup_map:
            dedup_map[doc_id] = {**c, "rerank_score": s}
            ordered_ids.append(doc_id)
        else:
            existing = dedup_map[doc_id]
            if len(existing['text']) < 3000:
                existing['text'] += "\n... " + c.get('text', '')
                
    return [dedup_map[doc_id] for doc_id in ordered_ids[:top_k]]
