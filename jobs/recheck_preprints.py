from concurrent.futures import ThreadPoolExecutor
from typing import Tuple, Optional

import requests
from qdrant_client.models import FieldCondition, Filter, MatchValue

from core.config import QDRANT_COLLECTION
from core.logsetup import get_logger, record_event
from core.qdrant_setup import get_client

log = get_logger(__name__)
WORKERS = 4

PREPRINT_FILTER = Filter(
    must=[
        FieldCondition(key="section", match=MatchValue(value="abstract")),
        FieldCondition(key="doc_type", match=MatchValue(value="medrxiv_preprint")),
    ]
)


def _is_now_published(doi: str) -> bool:
    """Single-DOI lookup (not a date-range page scan) - returns every version
    of the preprint, each carrying its own `published` field."""
    try:
        r = requests.get(f"https://api.biorxiv.org/details/medrxiv/{doi}", timeout=30)
        r.raise_for_status()
        versions = r.json().get("collection", [])
    except requests.RequestException as e:
        log.warning(f"recheck_preprints: lookup failed for doi={doi}: {e}")
        return False
    return any(v.get("published", "NA") not in ("", "NA") for v in versions)


def recheck(batch_size: int = 50, max_batches: Optional[int] = None) -> Tuple[int, int]:
    """Drops preprints that have since been published elsewhere - the
    published version comes in through the normal PubMed sync instead, same
    reasoning as the already_published_as skip at ingestion time
    (ingestion/ingest_medrxiv.py), just applied retroactively."""
    client = get_client()
    checked, removed, offset, batches = 0, 0, None, 0

    while True:
        points, offset = client.scroll(
            collection_name=QDRANT_COLLECTION,
            scroll_filter=PREPRINT_FILTER,
            limit=batch_size,
            offset=offset,
            with_payload=["doi", "title"],
        )
        if not points:
            break

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            published_flags = list(pool.map(lambda p: _is_now_published(p.payload["doi"]), points))

        for point, is_published in zip(points, published_flags):
            checked += 1
            if not is_published:
                continue
            doi = point.payload["doi"]
            client.delete(
                collection_name=QDRANT_COLLECTION,
                points_selector=Filter(must=[
                    FieldCondition(key="doi", match=MatchValue(value=doi)),
                    FieldCondition(key="doc_type", match=MatchValue(value="medrxiv_preprint")),
                ]),
            )
            removed += 1
            log.info(f"recheck_preprints: removed now-published preprint doi={doi} "
                      f"title={point.payload['title'][:60]!r}")

        batches += 1
        log.info(f"recheck_preprints batch {batches}: checked {checked} so far, {removed} removed")
        if offset is None or (max_batches and batches >= max_batches):
            break

    log.info(f"recheck_preprints done: checked {checked}, removed {removed}")
    record_event("recheck_preprints", checked=checked, removed=removed)
    return checked, removed


if __name__ == "__main__":
    checked, removed = recheck(batch_size=50)
    print(f"OK: checked {checked} preprints, removed {removed} now-published")
