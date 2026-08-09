import uuid
from typing import List, Dict, Any, Tuple

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from core.chunking import chunk_text
from core.config import QDRANT_COLLECTION
from core.domains import classify_keyword_domains
from services.embedder import embed_articles
from core.logsetup import get_logger
from ingestion.ingest import UPSERT_BATCH

log = get_logger(__name__)
NAMESPACE = uuid.NAMESPACE_DNS

def _payload_ct(doc: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
    base = {
        "doc_type": "clinical_trial",
        "domains": classify_keyword_domains(f"{doc['title']} {doc['abstract']} {' '.join(doc['mesh_terms'])}"),
        "nctId": doc["nctId"],
        "title": doc["title"],
        "mesh_terms": doc["mesh_terms"],
        "pub_types": doc["pub_types"],
        "journal": doc["journal"],
        "edat": doc["edat"],
    }
    base.update(extra)
    return base

def ingest_trials(client: QdrantClient, trials: List[Dict[str, Any]]) -> Tuple[int, int]:
    entries = []
    for doc in trials:
        entries.append((doc, "abstract", doc["abstract"]))
        n_chunks = 0
        if doc["full_text"]:
            chunks = chunk_text(doc["full_text"])
            n_chunks = len(chunks)
            for i, chunk in enumerate(chunks):
                entries.append((doc, f"fulltext_{i}", chunk))
        log.info(
            f"ingest CT nctId={doc['nctId']} title={doc['title'][:60]!r} "
            f"chunks={n_chunks}"
        )

    if not entries:
        log.info("ingest_trials: nothing to write (empty input)")
        return 0, 0

    pairs = [[doc["title"], text] for doc, section, text in entries]
    vectors = embed_articles(pairs)

    has_full_text = {doc["nctId"] for doc, section, _ in entries if section != "abstract"}

    points = [
        PointStruct(
            id=str(uuid.uuid5(NAMESPACE, f"nctId:{doc['nctId']}:{section}")),
            vector=vector.tolist(),
            payload=_payload_ct(doc, section=section, text=text, source="clinicaltrials.gov",
                                  has_full_text=doc["nctId"] in has_full_text),
        )
        for (doc, section, text), vector in zip(entries, vectors)
    ]
    
    for i in range(0, len(points), UPSERT_BATCH):
        client.upsert(collection_name=QDRANT_COLLECTION, points=points[i:i + UPSERT_BATCH])
        
    log.info(f"upserted {len(points)} points for {len(trials)} trials into {QDRANT_COLLECTION!r}")
    
    return len(points), len(trials)
