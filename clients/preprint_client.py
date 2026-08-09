"""medRxiv API client (api.biorxiv.org/details/medrxiv - same backend bioRxiv
uses, different path segment, but bioRxiv itself isn't a source here; see
conversation history - checked live and it's overwhelmingly basic-science
content even scoped to its "neuroscience" category, not what a surgical/
neurosurgical department wants). Pages at ~30 items/request; the loop uses
the response's own `total` rather than assuming a page size (that
assumption was wrong and cost us most of the medRxiv results before it
was caught)."""
from typing import Any, Dict, List

import requests

from core.logsetup import get_logger

log = get_logger(__name__)

API_BASE = "https://api.biorxiv.org/details/medrxiv"


def fetch_by_category(mindate: str, maxdate: str, categories: List[str]) -> List[Dict[str, Any]]:
    """Filters by the author-assigned `category` field - no server-side
    search exists, only date-range listing, so this pages through the whole
    window and filters client-side."""
    mindate, maxdate = mindate.replace("/", "-"), maxdate.replace("/", "-")
    cats = {c.lower() for c in categories}
    cursor, matches = 0, []

    while True:
        url = f"{API_BASE}/{mindate}/{maxdate}/{cursor}"
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as e:
            log.warning(f"medrxiv API failed at cursor {cursor}: {e}")
            break

        messages = data.get("messages", [])
        if not messages or messages[0].get("status") != "ok":
            break

        total_available = int(messages[0].get("total", 0))
        collection = data.get("collection", [])
        if not collection:
            break

        matches.extend(p for p in collection if (p.get("category") or "").lower() in cats)

        cursor += len(collection)
        if cursor >= total_available:
            break

    return matches


def parse_preprint(paper_json: Dict[str, Any]) -> Dict[str, Any]:
    doi = paper_json.get("doi", "")
    title = paper_json.get("title", "")
    abstract = paper_json.get("abstract", "")
    edat = paper_json.get("date", "")
    category = paper_json.get("category", "")
    published = paper_json.get("published", "")

    return {
        "pmid": 0,
        "doi": doi,
        "nctId": "",
        "pmcid": "",
        "title": title,
        "abstract": abstract,
        "full_text": "",
        "mesh_terms": [],
        "pub_types": ["Preprint"],
        "journal": "medRxiv",
        "edat": edat,
        "is_preprint": True,
        "category": category,
        "already_published_as": None if published in ("", "NA") else published,
    }
