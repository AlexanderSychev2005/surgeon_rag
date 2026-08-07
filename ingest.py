"""Embed abstracts (+ full-text chunks when available) and upsert into Qdrant.
One PointStruct per abstract (id = int(pmid)) plus one per full-text chunk
(deterministic uuid5 id, so re-running ingest on the same article is a no-op
upsert, not a duplicate)."""
import uuid

from qdrant_client.models import PointStruct

from chunking import chunk_text
from config import QDRANT_COLLECTION
from embedder import embed_articles
from fulltext import get_full_text
from logsetup import get_logger

log = get_logger(__name__)
NAMESPACE = uuid.NAMESPACE_DNS
UPSERT_BATCH = 64  # a full ingest batch (~200 articles) can be 1000s of chunk
                    # points; upserting them in one HTTP call risks the server
                    # dropping the connection mid-request (seen in practice)


def _payload(doc, **extra):
    base = {
        "pmid": int(doc["pmid"]),
        "title": doc["title"],
        "mesh_terms": doc["mesh_terms"],
        "pub_types": doc["pub_types"],
        "journal": doc["journal"],
        "doi": doc["doi"],
        "pmcid": doc["pmcid"],
        "edat": doc["edat"],
        "is_preprint": doc.get("is_preprint", False),
    }
    base.update(extra)
    return base


def ingest_articles(client, articles, fetch_full_text=True):
    """Returns (points_written, articles_with_full_text)."""
    entries = []  # (doc, section, text, source)
    for doc in articles:
        entries.append((doc, "abstract", doc["abstract"], "pubmed_abstract"))
        n_chunks, ft_source = 0, None
        if fetch_full_text and (doc.get("pmcid") or doc.get("doi")):
            full_text, ft_source = get_full_text(pmcid=doc.get("pmcid"), doi=doc.get("doi"))
            if full_text:
                chunks = chunk_text(full_text)
                n_chunks = len(chunks)
                for i, chunk in enumerate(chunks):
                    entries.append((doc, f"fulltext_{i}", chunk, ft_source))
        log.info(
            f"ingest pmid={doc['pmid']} title={doc['title'][:60]!r} "
            f"full_text={'yes:' + ft_source if n_chunks else 'no'} chunks={n_chunks}"
        )

    if not entries:
        log.info("ingest_articles: nothing to write (empty input)")
        return 0, 0

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
    return len(points), len(has_full_text)


def demo():
    from config import SURGERY_MESH_QUERY
    from pubmed_client import efetch_articles, esearch_pmids
    from qdrant_setup import ensure_collection

    client = ensure_collection()
    pmids = esearch_pmids(SURGERY_MESH_QUERY, retmax=5)
    articles = efetch_articles(pmids)
    n_points, n_full = ingest_articles(client, articles)
    assert n_points >= len(articles), (n_points, len(articles))
    count = client.count(QDRANT_COLLECTION).count
    print(f"OK: wrote {n_points} points ({n_full}/{len(articles)} articles had full text), "
          f"collection now has {count} points total")


if __name__ == "__main__":
    demo()
