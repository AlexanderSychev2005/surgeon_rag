import uuid
from qdrant_client.models import PointStruct
from chunking import chunk_text
from config import QDRANT_COLLECTION
from embedder import embed_articles
from logsetup import get_logger
from ingest import UPSERT_BATCH

log = get_logger(__name__)
NAMESPACE = uuid.NAMESPACE_DNS

def _payload_ct(doc, **extra):
    base = {
        "doc_type": "clinical_trial",
        "nctId": doc["nctId"],
        "title": doc["title"],
        "mesh_terms": doc["mesh_terms"],
        "pub_types": doc["pub_types"],
        "journal": doc["journal"],
        "edat": doc["edat"],
    }
    base.update(extra)
    return base

def ingest_trials(client, trials):
    """
    Takes parsed trial dicts.
    Returns (points_written, articles_written)
    """
    entries = []  # (doc, section, text)
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

    points = [
        PointStruct(
            id=str(uuid.uuid5(NAMESPACE, f"nctId:{doc['nctId']}:{section}")),
            vector=vector.tolist(),
            payload=_payload_ct(doc, section=section, text=text, source="clinicaltrials.gov"),
        )
        for (doc, section, text), vector in zip(entries, vectors)
    ]
    
    for i in range(0, len(points), UPSERT_BATCH):
        client.upsert(collection_name=QDRANT_COLLECTION, points=points[i:i + UPSERT_BATCH])
        
    log.info(f"upserted {len(points)} points for {len(trials)} trials into {QDRANT_COLLECTION!r}")
    
    return len(points), len(trials)
