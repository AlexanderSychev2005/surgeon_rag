"""Shared client for the bioRxiv/medRxiv API - same backend
(api.biorxiv.org), just a different `server` path segment. Pages at ~30
items/request; the loop uses the response's own `total` rather than
assuming a page size (that assumption was wrong and cost us most of the
medRxiv results before it was caught)."""
from typing import Any, Callable, Dict, List, Optional

import requests

from core.logsetup import get_logger

log = get_logger(__name__)

API_BASE = "https://api.biorxiv.org/details"


def _paginate(server: str, mindate: str, maxdate: str, match_fn: Callable[[Dict[str, Any]], bool]) -> List[Dict[str, Any]]:
    mindate = mindate.replace("/", "-")
    maxdate = maxdate.replace("/", "-")
    cursor, matches = 0, []

    while True:
        url = f"{API_BASE}/{server}/{mindate}/{maxdate}/{cursor}"
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as e:
            log.warning(f"{server} API failed at cursor {cursor}: {e}")
            break

        messages = data.get("messages", [])
        if not messages or messages[0].get("status") != "ok":
            break

        total_available = int(messages[0].get("total", 0))
        collection = data.get("collection", [])
        if not collection:
            break

        matches.extend(p for p in collection if match_fn(p))

        cursor += len(collection)
        if cursor >= total_available:
            break

    return matches


def fetch_preprints(server: str, mindate: str, maxdate: str, query_terms: List[str]) -> List[Dict[str, Any]]:
    """Filters client-side by title/abstract keyword match - neither server
    supports server-side search, only date-range listing."""
    lower_terms = [t.lower() for t in query_terms]

    def match(paper: Dict[str, Any]) -> bool:
        title = paper.get("title", "") or paper.get("preprint_title", "")
        abstract = paper.get("abstract", "") or paper.get("preprint_abstract", "")
        text = (title + " " + abstract).lower()
        return any(t in text for t in lower_terms)

    return _paginate(server, mindate, maxdate, match)


def fetch_by_category(server: str, mindate: str, maxdate: str, categories: List[str]) -> List[Dict[str, Any]]:
    """Filters by the author-assigned `category` field - only medRxiv has
    clinical/surgical categories (see core.config.MEDRXIV_DOMAIN_CATEGORIES);
    far more precise than keyword matching where it's available."""
    cats = {c.lower() for c in categories}
    return _paginate(server, mindate, maxdate, lambda p: (p.get("category") or "").lower() in cats)


def parse_preprint(paper_json: Dict[str, Any], server_label: str) -> Dict[str, Any]:
    """server_label: display value for the `journal` field, e.g. 'medRxiv'/'bioRxiv'."""
    doi = paper_json.get("preprint_doi") or paper_json.get("doi", "")
    title = paper_json.get("preprint_title") or paper_json.get("title", "")
    abstract = paper_json.get("preprint_abstract") or paper_json.get("abstract", "")
    edat = paper_json.get("preprint_date") or paper_json.get("date", "")
    category = paper_json.get("preprint_category") or paper_json.get("category", "")
    published = paper_json.get("preprint_published") or paper_json.get("published", "")

    return {
        "pmid": 0,
        "doi": doi,
        "nctId": "",
        "pmcid": "",
        "title": title,
        "abstract": abstract,
        "full_text": "",
        "mesh_terms": [],  # preprints have no real MeSH; category (below) is the closer analog
        "pub_types": ["Preprint"],
        "journal": server_label,
        "edat": edat,
        "is_preprint": True,
        "category": category,
        "already_published_as": None if published in ("", "NA") else published,
    }


def fetch_biorxiv_history(mindate: str, maxdate: str, query_terms: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    from core.config import BIORXIV_TERMS
    return fetch_preprints("biorxiv", mindate, maxdate, query_terms or BIORXIV_TERMS)


def parse_biorxiv_paper(paper_json: Dict[str, Any]) -> Dict[str, Any]:
    return parse_preprint(paper_json, "bioRxiv")
