import math
import requests
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from qdrant_client.models import Filter, FieldCondition, MatchValue

from services.retrieval import retrieve

app = FastAPI(title="Surgeon RAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SearchFilters(BaseModel):
    # "all", "pubmed_article", "clinical_trial", "medrxiv_preprint", "biorxiv_preprint"
    doc_type: str = "all"
    full_text_only: bool = False

class SearchRequest(BaseModel):
    query: str
    filters: SearchFilters
    top_k: int = 5

@app.post("/api/search")
def search(req: SearchRequest) -> Dict[str, Any]:
    qdrant_filter = None
    must_conditions = []
    
    if req.filters.doc_type != "all":
        must_conditions.append(
            FieldCondition(
                key="doc_type",
                match=MatchValue(value=req.filters.doc_type)
            )
        )
    
    if req.filters.full_text_only:
        must_conditions.append(
            FieldCondition(
                key="has_full_text",
                match=MatchValue(value=True)
            )
        )
        
    if must_conditions:
        qdrant_filter = Filter(must=must_conditions)
        
    candidate_pool = max(50, req.top_k * 10)
        
    try:
        results = retrieve(req.query, top_k=req.top_k, candidate_pool=candidate_pool, qdrant_filter=qdrant_filter)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    context_text = ""
    for idx, r in enumerate(results):
        text = r.get("text", "")
        raw_score = r.get("rerank_score", 0)
        relevance_pct = int((1 / (1 + math.exp(-raw_score))) * 100)
        
        raw_doc_type = r.get("doc_type")
        if raw_doc_type == "clinical_trial":
            doc_type_label = "Clinical Trial"
        elif raw_doc_type in ("medrxiv_preprint", "biorxiv_preprint"):
            doc_type_label = "Preprint (Not Peer-Reviewed)"
        else:
            doc_type_label = "PubMed Article"
            
        context_text += f"\n\nSource [{idx+1}] (Type: {doc_type_label}, Relevance: {relevance_pct}%, Title: {r.get('title')}):\n{text[:800]}..."
        
    prompt = f"""You are an advanced, helpful surgical assistant AI designed to answer complex medical questions based strictly on provided scientific literature.
Please answer the user's question using only the sources below. 
- You MUST reference the source numbers in your answer (e.g., [1], [2]).
- Pay close attention to the "Type" and "Relevance" score of each source. Prioritize sources with higher relevance. 
- Clinical trials usually provide higher quality of evidence than standard articles.
- Note that Preprints are not peer-reviewed and should be interpreted with caution.
- Use clean Markdown formatting. If you cannot answer it from the sources, explicitly say so. Do not invent information.

Question: {req.query}

Sources:
{context_text}
"""

    llm_response = ""
    try:
        ollama_res = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "qwen2.5",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_ctx": 8192
                }
            },
            timeout=120
        )
        if ollama_res.status_code == 200:
            llm_response = ollama_res.json().get("response", "")
        else:
            llm_response = f"LLM Error: {ollama_res.text}"
    except Exception as e:
        llm_response = "Error connecting to local Ollama (qwen2.5). Please ensure Ollama is installed and running with 'ollama run qwen2.5'."

    return {
        "results": results,
        "llm_response": llm_response
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
