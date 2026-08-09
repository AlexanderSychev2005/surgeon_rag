from typing import Any, Dict, List, Optional

from clients.biorxiv_client import fetch_by_category, parse_preprint
from core.config import MEDRXIV_DOMAIN_CATEGORIES


def fetch_medrxiv_history(mindate: str, maxdate: str, categories: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    return fetch_by_category("medrxiv", mindate, maxdate, categories or list(MEDRXIV_DOMAIN_CATEGORIES.keys()))


def parse_medrxiv_paper(paper_json: Dict[str, Any]) -> Dict[str, Any]:
    return parse_preprint(paper_json, "medRxiv")
