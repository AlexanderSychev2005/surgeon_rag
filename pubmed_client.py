"""Minimal NCBI E-utilities client: esearch + efetch, parsed into plain dicts."""
import os
import time
import xml.etree.ElementTree as ET

import requests
from dotenv import load_dotenv

load_dotenv()

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
NCBI_API_KEY = os.environ.get("NCBI_API_KEY") or None
NCBI_EMAIL = os.environ.get("NCBI_EMAIL") or None
# without an API key NCBI allows 3 req/s, with one 10 req/s
_MIN_INTERVAL = 0.11 if NCBI_API_KEY else 0.35
_last_call = 0.0


def _throttle():
    global _last_call
    wait = _MIN_INTERVAL - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()


def _params(extra):
    p = dict(extra)
    if NCBI_API_KEY:
        p["api_key"] = NCBI_API_KEY
    if NCBI_EMAIL:
        p["email"] = NCBI_EMAIL
    return p


def esearch_pmids(query, retmax=20, mindate=None, maxdate=None, datetype="edat"):
    """Returns a list of PMIDs matching `query`. datetype='edat' catches
    articles by the date they were ADDED to PubMed (not published) -
    that's what you want for an incremental "what's new" sync."""
    params = {"db": "pubmed", "term": query, "retmax": retmax, "retmode": "json"}
    if mindate and maxdate:
        params.update(datetype=datetype, mindate=mindate, maxdate=maxdate)
    _throttle()
    r = requests.get(f"{EUTILS}/esearch.fcgi", params=_params(params), timeout=30)
    r.raise_for_status()
    return r.json()["esearchresult"]["idlist"]


def esearch_history(query, mindate=None, maxdate=None, datetype="pdat"):
    """Like esearch_pmids but keeps the result set server-side (usehistory=y)
    so efetch_history_batch can page through it with retstart, instead of
    capping out at whatever retmax you pass. Use this for bulk backfills;
    use esearch_pmids for small/incremental pulls.
    Returns (webenv, query_key, count)."""
    params = {"db": "pubmed", "term": query, "retmode": "json", "usehistory": "y", "retmax": 0}
    if mindate and maxdate:
        params.update(datetype=datetype, mindate=mindate, maxdate=maxdate)
    _throttle()
    r = requests.get(f"{EUTILS}/esearch.fcgi", params=_params(params), timeout=30)
    r.raise_for_status()
    result = r.json()["esearchresult"]
    return result["webenv"], result["querykey"], int(result["count"])


def efetch_history_batch(webenv, query_key, retstart, retmax):
    """Fetch one page of a history-backed result set (see esearch_history)."""
    params = {
        "db": "pubmed", "WebEnv": webenv, "query_key": query_key,
        "retstart": retstart, "retmax": retmax, "rettype": "abstract", "retmode": "xml",
    }
    _throttle()
    r = requests.get(f"{EUTILS}/efetch.fcgi", params=_params(params), timeout=90)
    r.raise_for_status()
    return _parse_efetch_xml(r.content)


def efetch_articles(pmids):
    """Fetch full MEDLINE XML for a batch of PMIDs and parse the fields we need:
    title, abstract, mesh_terms, pub_types, doi, pmcid, pub_date, edat."""
    if not pmids:
        return []
    params = {"db": "pubmed", "id": ",".join(pmids), "rettype": "abstract", "retmode": "xml"}
    _throttle()
    r = requests.get(f"{EUTILS}/efetch.fcgi", params=_params(params), timeout=60)
    r.raise_for_status()
    return _parse_efetch_xml(r.content)


def _parse_efetch_xml(xml_bytes):
    root = ET.fromstring(xml_bytes)
    articles = []
    for art in root.findall(".//PubmedArticle"):
        pmid = art.findtext(".//MedlineCitation/PMID")
        title = art.findtext(".//Article/ArticleTitle") or ""
        abstract = " ".join(
            (t.text or "") for t in art.findall(".//Article/Abstract/AbstractText")
        )
        mesh_terms = [
            d.text for d in art.findall(".//MeshHeadingList/MeshHeading/DescriptorName")
        ]
        pub_types = [t.text for t in art.findall(".//PublicationTypeList/PublicationType")]
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
                edat = f"{int(y):04d}-{int(m):02d}-{int(day):02d}"  # zero-padded ISO date

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


def demo():
    pmids = esearch_pmids('"Laparoscopy"[MeSH]', retmax=3)
    assert pmids, "esearch returned nothing - check network/query"
    articles = efetch_articles(pmids)
    assert len(articles) == len(pmids)
    assert all(a["title"] for a in articles)
    print(f"OK: fetched {len(articles)} articles, e.g. {articles[0]['title'][:80]!r}")


if __name__ == "__main__":
    demo()
