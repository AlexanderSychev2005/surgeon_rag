import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Tuple, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from core.chunking import chunk_text
from core.config import QDRANT_COLLECTION, NAMESPACE
from services.embedder import embed_articles
from services.fulltext import get_full_text
from core.logsetup import get_logger

log = get_logger(__name__)
UPSERT_BATCH = 64
FULLTEXT_WORKERS = 16


def _fetch_full_text(doc: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    if doc.get("pmcid") or doc.get("doi"):
        return get_full_text(pmcid=doc.get("pmcid"), doi=doc.get("doi"))
    return None, None


def _payload(doc: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
    base = {
        "doc_type": "pubmed_article",
        "pmid": int(doc["pmid"]),
        "title": doc["title"],
        "mesh_terms": doc["mesh_terms"],
        "pub_types": doc["pub_types"],
        "journal": doc["journal"],
        "doi": doc["doi"],
        "pmcid": doc["pmcid"],
        "edat": doc["edat"],
        "pub_date": doc.get("pub_date"),
        "is_preprint": doc.get("is_preprint", False),
    }
    base.update(extra)
    return base


def ingest_articles(client: QdrantClient, articles: List[Dict[str, Any]]) -> Tuple[int, int, Dict[str, int], int]:
    with ThreadPoolExecutor(max_workers=FULLTEXT_WORKERS) as pool:
        full_text_results = list(pool.map(_fetch_full_text, articles))

    entries = []
    for doc, (full_text, ft_source) in zip(articles, full_text_results):
        entries.append((doc, "abstract", doc["abstract"], "pubmed_abstract"))
        n_chunks = 0
        if full_text:
            chunks = chunk_text(full_text)
            n_chunks = len(chunks)
            for i, chunk in enumerate(chunks):
                entries.append((doc, f"fulltext_{i}", chunk, ft_source))
        log.info(
            f"ingest pmid={doc['pmid']} title={doc['title'][:60]!r} "
            f"full_text={'yes:' + str(ft_source) if n_chunks else 'no'} chunks={n_chunks}"
        )

    if not entries:
        log.info("ingest_articles: nothing to write (empty input)")
        return 0, 0, {}, 0

    pairs = [[doc["title"], text] for doc, _, text, _ in entries]
    vectors = embed_articles(pairs)

    has_full_text = {doc["pmid"] for doc, section, _, _ in entries if section != "abstract"}

    points = [
        PointStruct(
            id=int(doc["pmid"]) if section == "abstract" else str(uuid.uuid5(NAMESPACE, f"pmid:{doc['pmid']}:{section}")),
            vector=vector.tolist(),
            payload=_payload(doc, section=section, text=text,
                              has_full_text=doc["pmid"] in has_full_text, source=source),
        )
        for (doc, section, text, source), vector in zip(entries, vectors)
    ]
    for i in range(0, len(points), UPSERT_BATCH):
        client.upsert(collection_name=QDRANT_COLLECTION, points=points[i:i + UPSERT_BATCH])
    log.info(
        f"upserted {len(points)} points for {len(articles)} articles "
        f"({len(has_full_text)} with full text) into {QDRANT_COLLECTION!r}"
    )
    source_counts = {}
    for _, ft_source in full_text_results:
        if ft_source:
            source_counts[ft_source] = source_counts.get(ft_source, 0) + 1
    
    fulltext_points = sum(1 for _, section, _, _ in entries if section != "abstract")
    return len(points), len(has_full_text), source_counts, fulltext_points
