from functools import cache
from typing import Any

import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
DTYPE = torch.float16 if DEVICE == "cuda" else torch.float32


@cache
def _load(name: str) -> tuple[Any, Any]:
    tok = AutoTokenizer.from_pretrained(name)
    model = AutoModel.from_pretrained(name).to(DEVICE, dtype=DTYPE)
    model.eval()
    return tok, model


@torch.no_grad()
def embed_queries(queries: list[str]) -> np.ndarray:
    tok, model = _load("ncbi/MedCPT-Query-Encoder")
    enc = tok(
        queries, truncation=True, padding=True, return_tensors="pt", max_length=64
    ).to(DEVICE)
    return model(**enc).last_hidden_state[:, 0, :].float().cpu().numpy()


@torch.no_grad()
def embed_articles(
    title_text_pairs: list[list[str]], batch_size: int = 256
) -> np.ndarray:
    tok, model = _load("ncbi/MedCPT-Article-Encoder")
    chunks = []
    for i in range(0, len(title_text_pairs), batch_size):
        batch = title_text_pairs[i : i + batch_size]
        enc = tok(
            batch, truncation=True, padding=True, return_tensors="pt", max_length=512
        ).to(DEVICE)
        chunks.append(model(**enc).last_hidden_state[:, 0, :].float().cpu())
    return torch.cat(chunks, dim=0).numpy()
