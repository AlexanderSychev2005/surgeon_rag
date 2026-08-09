"""Domain tagging: which topic area(s) a document belongs to. An article can
belong to more than one (e.g. a neurosurgery paper is both surgery AND
neurobiology) - that's the whole point of tagging rather than picking a
single collection per domain, see conversation history.

PubMed items carry real MeSH descriptors, so classification there is an
exact set intersection. CT.gov/medRxiv/bioRxiv have no controlled
vocabulary, so classification falls back to keyword substring match on
whatever text we already have (title/abstract/conditions) - approximate,
but consistent with how those sources are already being *found* (same
keyword lists drive both the fetch filter and the domain tag)."""
from typing import Iterable, List, Optional

from core.config import (
    MEDRXIV_DOMAIN_CATEGORIES,
    NEURO_KEYWORDS,
    NEURO_NARROW_MESH_TERMS,
    SURGERY_KEYWORDS,
    SURGERY_MESH_TERMS,
)
from core.logsetup import get_logger

log = get_logger(__name__)

_SURGERY_MESH = set(SURGERY_MESH_TERMS)
_NEURO_MESH = set(NEURO_NARROW_MESH_TERMS)


def classify_mesh_domains(mesh_terms: Optional[Iterable[str]]) -> List[str]:
    terms = set(mesh_terms or [])
    domains = []
    if terms & _SURGERY_MESH:
        domains.append("surgery")
    if terms & _NEURO_MESH:
        domains.append("neurobiology")
    if not domains:
        # genuinely shouldn't happen - COMBINED_PUBMED_QUERY guarantees a MeSH
        # hit from one of these lists. Surface it instead of silently guessing.
        log.warning(f"classify_mesh_domains: no domain matched for mesh_terms={list(terms)[:10]}")
    return domains


def classify_keyword_domains(text: str) -> List[str]:
    """CT.gov/medRxiv/bioRxiv have no controlled vocabulary. Unlike the MeSH
    case, a source query can match on text we're not re-checking here (e.g.
    CT.gov's query.term searches far more fields than title+abstract+
    conditions) - so an empty result here is real and expected sometimes,
    not a bug. Return it as-is rather than guessing a domain."""
    text = (text or "").lower()
    domains = []
    if any(k in text for k in SURGERY_KEYWORDS):
        domains.append("surgery")
    if any(k in text for k in NEURO_KEYWORDS):
        domains.append("neurobiology")
    return domains


def classify_medrxiv_category_domains(category: str) -> List[str]:
    """medRxiv only - the category is author-assigned at submission and maps
    cleanly onto our two domains (checked live against the full category
    list), so use it directly instead of the keyword fallback."""
    return MEDRXIV_DOMAIN_CATEGORIES.get((category or "").lower(), [])


def demo():
    assert classify_mesh_domains(["Laparoscopy", "Humans"]) == ["surgery"]
    assert classify_mesh_domains(["Neurosurgery", "Humans"]) == ["neurobiology"]
    assert set(classify_mesh_domains(["Neurosurgical Procedures", "Postoperative Complications"])) == {"surgery", "neurobiology"}
    assert classify_keyword_domains("A study of laparoscopic surgery outcomes") == ["surgery"]
    # "neurosurgical" legitimately contains "surgical" - both tags are correct here,
    # this IS the surgery/neuro intersection the domain field exists to capture
    assert set(classify_keyword_domains("Neurosurgical management of stroke")) == {"surgery", "neurobiology"}
    print("OK: domain classification matches expected cases")


if __name__ == "__main__":
    demo()
