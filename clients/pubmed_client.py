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


def efetch_history_batch(webenv: str, query_key: str, retstart: int, retmax: int) -> List[Dict[str, Any]]:
    params = {
        "db": "pubmed", "WebEnv": webenv, "query_key": query_key,
        "retstart": retstart, "retmax": retmax, "rettype": "abstract", "retmode": "xml",
    }
    _throttle()
    r = requests.get(f"{EUTILS}/efetch.fcgi", params=_params(params), timeout=90)
    r.raise_for_status()
    return _parse_efetch_xml(r.content)


def efetch_articles(pmids: List[str]) -> List[Dict[str, Any]]:
    if not pmids:
        return []
    params = {"db": "pubmed", "id": ",".join(pmids), "rettype": "abstract", "retmode": "xml"}
    _throttle()
    r = requests.get(f"{EUTILS}/efetch.fcgi", params=_params(params), timeout=60)
    r.raise_for_status()
    return _parse_efetch_xml(r.content)


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
            }
        )
    return articles
