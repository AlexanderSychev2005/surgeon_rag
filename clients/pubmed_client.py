import os
import time
import xml.etree.ElementTree as ET
from typing import List, Optional, Tuple, Dict, Any

import requests
from dotenv import load_dotenv

load_dotenv()

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
NCBI_API_KEY = os.environ.get("NCBI_API_KEY") or None
NCBI_EMAIL = os.environ.get("NCBI_EMAIL") or None
_MIN_INTERVAL = 0.11 if NCBI_API_KEY else 0.35
_last_call = 0.0


def _throttle() -> None:
    global _last_call
    wait = _MIN_INTERVAL - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()


def _params(extra: Dict[str, Any]) -> Dict[str, Any]:
    p = dict(extra)
    if NCBI_API_KEY:
        p["api_key"] = NCBI_API_KEY
    if NCBI_EMAIL:
        p["email"] = NCBI_EMAIL
    return p


def esearch_pmids(query: str, retmax: int = 20, mindate: Optional[str] = None, maxdate: Optional[str] = None, datetype: str = "edat") -> List[str]:
    params = {"db": "pubmed", "term": query, "retmax": retmax, "retmode": "json"}
    if mindate and maxdate:
        params.update(datetype=datetype, mindate=mindate, maxdate=maxdate)
    _throttle()
    r = requests.get(f"{EUTILS}/esearch.fcgi", params=_params(params), timeout=30)
    r.raise_for_status()
    return r.json()["esearchresult"]["idlist"]


def esearch_history(query: str, mindate: Optional[str] = None, maxdate: Optional[str] = None, datetype: str = "pdat") -> Tuple[str, str, int]:
    params = {"db": "pubmed", "term": query, "retmode": "json", "usehistory": "y", "retmax": 0}
    if mindate and maxdate:
        params.update(datetype=datetype, mindate=mindate, maxdate=maxdate)
    _throttle()
    r = requests.get(f"{EUTILS}/esearch.fcgi", params=_params(params), timeout=30)
    r.raise_for_status()
    result = r.json()["esearchresult"]
    return result["webenv"], result["querykey"], int(result["count"])


def efetch_history_batch(webenv: str, query_key: str, retstart: int, retmax: int, max_retries: int = 3) -> List[Dict[str, Any]]:
    """Retries on transient connection drops - NCBI occasionally cuts off
    large XML responses mid-stream (ChunkedEncodingError), unrelated to
    anything in the request; a retry is enough, no backoff-worthy rate limit
    involved like the medRxiv 429 case."""
    params = {
        "db": "pubmed", "WebEnv": webenv, "query_key": query_key,
        "retstart": retstart, "retmax": retmax, "rettype": "abstract", "retmode": "xml",
    }
    for attempt in range(max_retries + 1):
        _throttle()
        try:
            r = requests.get(f"{EUTILS}/efetch.fcgi", params=_params(params), timeout=90)
            r.raise_for_status()
            return _parse_efetch_xml(r.content)
        except requests.RequestException:
            if attempt == max_retries:
                raise
            time.sleep(2 * (attempt + 1))


def efetch_articles(pmids: List[str]) -> List[Dict[str, Any]]:
    if not pmids:
        return []
    params = {"db": "pubmed", "id": ",".join(pmids), "rettype": "abstract", "retmode": "xml"}
    _throttle()
    r = requests.get(f"{EUTILS}/efetch.fcgi", params=_params(params), timeout=60)
    r.raise_for_status()
    return _parse_efetch_xml(r.content)


_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_date_element(el: Optional[ET.Element]) -> Optional[str]:
    """PubDate/ArticleDate elements: Year always present if the element is,
    Month can be numeric or a 3-letter name, Day often missing entirely.
    Returns an ISO date, defaulting missing Month/Day to 01 - approximate,
    but this field is for display ("when was this published"), not for
    watermarking (edat handles that with real day precision)."""
    if el is None:
        return None
    y = el.findtext("Year")
    if not y:
        return None
    m_raw = el.findtext("Month") or "1"
    m = _MONTHS.get(m_raw.strip().lower()[:3], None)
    if m is None:
        m = int(m_raw) if m_raw.isdigit() else 1
    d_raw = el.findtext("Day")
    d = int(d_raw) if d_raw and d_raw.isdigit() else 1
    return f"{int(y):04d}-{m:02d}-{d:02d}"


def _parse_efetch_xml(xml_bytes: bytes) -> List[Dict[str, Any]]:
    root = ET.fromstring(xml_bytes)
    articles = []
    for art in root.findall(".//PubmedArticle"):
        pmid = art.findtext(".//MedlineCitation/PMID")
        title = art.findtext(".//Article/ArticleTitle") or ""
        abstract = " ".join(
            (t.text or "") for t in art.findall(".//Article/Abstract/AbstractText")
        )
        mesh_terms = [
            d.text for d in art.findall(".//MeshHeadingList/MeshHeading/DescriptorName") if d.text
        ]
        pub_types = [t.text for t in art.findall(".//PublicationTypeList/PublicationType") if t.text]
        journal = art.findtext(".//Article/Journal/Title") or ""

        doi, pmcid = None, None
        for aid in art.findall(".//PubmedData/ArticleIdList/ArticleId"):
            if aid.get("IdType") == "doi":
                doi = aid.text
            elif aid.get("IdType") == "pmc":
                pmcid = aid.text

        edat = None
        for d in art.findall(".//PubmedData/History/PubMedPubDate"):
            if d.get("PubStatus") == "entrez":
                y, m, day = (d.findtext(x) for x in ("Year", "Month", "Day"))
                if y and m and day:
                    edat = f"{int(y):04d}-{int(m):02d}-{int(day):02d}"

        # pub_date: when the article was actually published, for display -
        # distinct from edat (when PubMed indexed it, for the sync watermark).
        # Prefer the electronic pub date (most precise, common for epub-ahead-
        # of-print), fall back to the journal issue's cover date.
        pub_date = _parse_date_element(art.find(".//Article/ArticleDate"))
        if not pub_date:
            pub_date = _parse_date_element(art.find(".//Article/Journal/JournalIssue/PubDate"))

        articles.append(
            {
                "pmid": pmid,
                "title": title,
                "abstract": abstract,
                "mesh_terms": mesh_terms,
                "pub_types": pub_types,
                "journal": journal,
                "doi": doi,
                "pmcid": pmcid,
                "edat": edat,
                "pub_date": pub_date,
            }
        )
    return articles
