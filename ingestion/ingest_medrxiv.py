import random
import time
import uuid
from typing import List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor

import requests
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from core.chunking import chunk_text
from core.config import QDRANT_COLLECTION, NAMESPACE
from services.embedder import embed_articles
from services.fulltext import _text_from_pdf_url
from core.logsetup import get_logger
from ingestion.ingest import UPSERT_BATCH

log = get_logger(__name__)
# Lower than ingestion/ingest.py's 16 on purpose: that pool spans many
# different domains (PMC, Unpaywall, publishers), this one hits a single
# domain (medrxiv.org) per run - 16 concurrent requests to one host was
# tripping their rate limit (64 429s in one 10-day bootstrap), costing us
# full-text hits, not just being polite.
FULLTEXT_WORKERS = 4


def _fetch_preprint_pdf(doi: str, max_retries: int = 2) -> str:
    """Retries on 429 with backoff - unlike PMC embargoes (which are a "come
    back in a few months" problem), preprints are open immediately, so a
    failure here is transient (rate limit, network blip), worth a same-run
    retry rather than waiting for some future recheck job."""
    if not doi:
        return ""
    url = f"https://www.medrxiv.org/content/{doi}.full.pdf"
    for attempt in range(max_retries + 1):
        try:
            text = _text_from_pdf_url(url)
            return text if text else ""
        except requests.HTTPError as e:
            is_last = attempt == max_retries
            if e.response is not None and e.response.status_code == 429 and not is_last:
                wait = 2 * (attempt + 1) + random.uniform(0, 1)  # jitter - several workers hit 429 together
                log.debug(f"429 for medRxiv PDF {doi}, retrying in {wait:.1f}s ({attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue
            log.warning(f"Failed to fetch medRxiv PDF for {doi}: {e}")
            return ""
        except Exception as e:
            log.warning(f"Failed to fetch medRxiv PDF for {doi}: {e}")
            return ""
    return ""


def _payload_preprint(doc: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
    base = {
        "doc_type": "medrxiv_preprint",
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


def ingest_preprints(client: QdrantClient, preprints: List[Dict[str, Any]]) -> Tuple[int, int]:
    already_published = [d for d in preprints if d.get("already_published_as")]
    if already_published:
        log.info(f"skipping {len(already_published)} medRxiv preprints already published elsewhere "
                 f"(the published version will come in through the PubMed sync instead)")
    preprints = [d for d in preprints if not d.get("already_published_as")]

    with ThreadPoolExecutor(max_workers=FULLTEXT_WORKERS) as pool:
        full_texts = list(pool.map(lambda d: _fetch_preprint_pdf(d.get("doi", "")), preprints))

    entries = []

    for doc, ft_text in zip(preprints, full_texts):
        entries.append((doc, "abstract", doc["abstract"]))

        n_chunks = 0
        if ft_text:
            chunks = chunk_text(ft_text)
            n_chunks = len(chunks)
            for i, chunk in enumerate(chunks):
                entries.append((doc, f"fulltext_{i}", chunk))

        log.info(f"ingest medrxiv doi={doc['doi']} title={doc['title'][:60]!r} chunks={n_chunks}")

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
            payload=_payload_preprint(doc, section=section, text=text, source=doc["journal"],
                                        has_full_text=doc["doi"] in has_full_text),
        )
        for (doc, section, text), vector in zip(entries, vectors)
    ]

    for i in range(0, len(points), UPSERT_BATCH):
        client.upsert(collection_name=QDRANT_COLLECTION, points=points[i:i + UPSERT_BATCH])

    log.info(f"upserted {len(points)} points for {len(preprints)} preprints into {QDRANT_COLLECTION!r}")

    return len(points), len(preprints)
