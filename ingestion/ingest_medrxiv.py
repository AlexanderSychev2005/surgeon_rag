import uuid
from typing import List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from core.chunking import chunk_text
from core.config import QDRANT_COLLECTION
from core.domains import classify_keyword_domains, classify_medrxiv_category_domains
from services.embedder import embed_articles
from services.fulltext import _text_from_pdf_url
from core.logsetup import get_logger
from ingestion.ingest import UPSERT_BATCH

log = get_logger(__name__)
NAMESPACE = uuid.NAMESPACE_DNS
# Lower than ingestion/ingest.py's 16 on purpose: that pool spans many
# different domains (PMC, Europe PMC, Unpaywall, publishers), this one hits
# a single domain (biorxiv.org or medrxiv.org) per run - 16 concurrent
# requests to one host was tripping their rate limit (64 429s in one 10-day
# bootstrap), costing us full-text hits, not just being polite.
FULLTEXT_WORKERS = 4


def _fetch_preprint_pdf(doi: str, domain: str) -> str:
    """Attempts to fetch the PDF text for a preprint DOI. domain: 'medrxiv.org' or 'biorxiv.org'."""
    if not doi:
        return ""
    url = f"https://www.{domain}/content/{doi}.full.pdf"
    try:
        text = _text_from_pdf_url(url)
        return text if text else ""
    except Exception as e:
        log.warning(f"Failed to fetch {domain} PDF for {doi}: {e}")
        return ""


def _payload_preprint(doc: Dict[str, Any], doc_type: str, server: str, **extra: Any) -> Dict[str, Any]:
    domains = (
        classify_medrxiv_category_domains(doc.get("category", ""))
        if server == "medrxiv"
        else classify_keyword_domains(f"{doc['title']} {doc['abstract']}")
    )
    base = {
        "doc_type": doc_type,
        "domains": domains,
        "doi": doc["doi"],
        "title": doc["title"],
        "mesh_terms": doc["mesh_terms"],
        "category": doc.get("category", ""),
        "pub_types": doc["pub_types"],
        "journal": doc["journal"],
        "edat": doc["edat"],
        "is_preprint": doc["is_preprint"],
    }
    base.update(extra)
    return base


def ingest_preprints(client: QdrantClient, preprints: List[Dict[str, Any]], fetch_full_text: bool = True, server: str = "medrxiv") -> Tuple[int, int]:
    """server: 'medrxiv' or 'biorxiv' - controls doc_type and which domain's PDF URL to try."""
    doc_type = f"{server}_preprint"
    domain = f"{server}.org"

    already_published = [d for d in preprints if d.get("already_published_as")]
    if already_published:
        log.info(f"skipping {len(already_published)} {server} preprints already published elsewhere "
                 f"(the published version will come in through the PubMed sync instead)")
    preprints = [d for d in preprints if not d.get("already_published_as")]

    if fetch_full_text:
        with ThreadPoolExecutor(max_workers=FULLTEXT_WORKERS) as pool:
            full_texts = list(pool.map(lambda d: _fetch_preprint_pdf(d.get("doi", ""), domain), preprints))
    else:
        full_texts = [""] * len(preprints)

    entries = []
    has_full_text_count = 0
    
    for doc, ft_text in zip(preprints, full_texts):
        # We always ingest the abstract
        entries.append((doc, "abstract", doc["abstract"]))
        
        n_chunks = 0
        if ft_text:
            chunks = chunk_text(ft_text)
            n_chunks = len(chunks)
            for i, chunk in enumerate(chunks):
                entries.append((doc, f"fulltext_{i}", chunk))
            has_full_text_count += 1
                
        log.info(f"ingest {server} doi={doc['doi']} title={doc['title'][:60]!r} chunks={n_chunks}")

    if not entries:
        log.info("ingest_preprints: nothing to write")
        return 0, 0

    pairs = [[doc["title"], text] for doc, section, text in entries]
    vectors = embed_articles(pairs)

    has_full_text = {doc["doi"] for doc, section, text in entries if section != "abstract"}

    points = [
        PointStruct(
            id=str(uuid.uuid5(NAMESPACE, f"doi:{doc['doi']}:{section}")),
            vector=vector.tolist(),
            payload=_payload_preprint(doc, doc_type, server, section=section, text=text, source=doc["journal"],
                                        has_full_text=doc["doi"] in has_full_text),
        )
        for (doc, section, text), vector in zip(entries, vectors)
    ]
    
    for i in range(0, len(points), UPSERT_BATCH):
        client.upsert(collection_name=QDRANT_COLLECTION, points=points[i:i + UPSERT_BATCH])
        
    log.info(f"upserted {len(points)} points for {len(preprints)} preprints into {QDRANT_COLLECTION!r}")
    
    return len(points), len(preprints)
