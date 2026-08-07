"""MedCPT bi-encoder wrapper. Query and Article encoders are separate models
trained on real PubMed search-log pairs (asymmetric retrieval) - see
ncbi/MedCPT-Query-Encoder / ncbi/MedCPT-Article-Encoder on Hugging Face.
Both use CLS-token pooling of the last hidden state.
"""
import torch
from transformers import AutoModel, AutoTokenizer

_CACHE = {}


def _load(name):
    if name not in _CACHE:
        tok = AutoTokenizer.from_pretrained(name)
        model = AutoModel.from_pretrained(name)
        model.eval()
        _CACHE[name] = (tok, model)
    return _CACHE[name]


@torch.no_grad()
def embed_queries(queries):
    """queries: list[str] -> (N, 768) float32 array"""
    tok, model = _load("ncbi/MedCPT-Query-Encoder")
    enc = tok(queries, truncation=True, padding=True, return_tensors="pt", max_length=64)
    return model(**enc).last_hidden_state[:, 0, :].numpy()


@torch.no_grad()
def embed_articles(title_text_pairs, batch_size=16):
    """title_text_pairs: list[[title, text]] -> (N, 768) float32 array.
    `text` is the abstract for the main doc, or a full-text chunk when we
    embed chunks - keeping the [title, X] pair format matches how the model
    was trained, even though X isn't strictly "the abstract" for chunks.

    Mini-batched: a single article with full text can produce 50+ chunks, and
    a sync batch covers ~200 articles, so passing everything through in one
    forward pass can demand several GB for the attention matrices alone (hit
    an OOM on CPU at ~2000 pairs in practice) - batch_size caps that."""
    tok, model = _load("ncbi/MedCPT-Article-Encoder")
    chunks = []
    for i in range(0, len(title_text_pairs), batch_size):
        batch = title_text_pairs[i:i + batch_size]
        enc = tok(batch, truncation=True, padding=True, return_tensors="pt", max_length=512)
        chunks.append(model(**enc).last_hidden_state[:, 0, :])
    return torch.cat(chunks, dim=0).numpy()


def demo():
    q = embed_queries(["what causes postoperative bleeding after cholecystectomy"])
    a = embed_articles([[
        "Postoperative bleeding after laparoscopic cholecystectomy",
        "This retrospective study reviews risk factors for postoperative hemorrhage...",
    ]])
    assert q.shape == (1, 768) and a.shape == (1, 768)
    # sanity: a genuinely related query/article pair should score higher than noise
    import numpy as np
    unrelated = embed_articles([["Diabetes insipidus diagnosis", "Central diabetes insipidus is a rare condition..."]])
    sim_related = float(q[0] @ a[0] / (np.linalg.norm(q[0]) * np.linalg.norm(a[0])))
    sim_unrelated = float(q[0] @ unrelated[0] / (np.linalg.norm(q[0]) * np.linalg.norm(unrelated[0])))
    assert sim_related > sim_unrelated, (sim_related, sim_unrelated)
    print(f"OK: shapes {q.shape}/{a.shape}, sim(related)={sim_related:.3f} > sim(unrelated)={sim_unrelated:.3f}")


if __name__ == "__main__":
    demo()
