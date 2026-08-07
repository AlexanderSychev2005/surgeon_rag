"""Best-effort legal full text acquisition, in order:
1) PMC Open Access S3 bucket (pmc-oa-opendata) - fastest, plain text, no lag
   even for articles added to PMC today (unlike Europe PMC below).
2) Europe PMC fullTextXML - covers PMC Open Access too, kept as a fallback
   since its indexing lags PMC's own OA bucket by some time.
3) Unpaywall -> best OA location -> PDF text extraction (non-PMC OA copies).
4) abstract only (caller's fallback).
"""
import io
import os
import xml.etree.ElementTree as ET

import requests
from dotenv import load_dotenv
from pypdf import PdfReader

from logsetup import get_logger

load_dotenv()
log = get_logger(__name__)

PMC_OA_S3 = "https://pmc-oa-opendata.s3.amazonaws.com/{pmcid}.1/{pmcid}.1.txt"
EUROPEPMC_FULLTEXT = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
UNPAYWALL_API = "https://api.unpaywall.org/v2/{doi}"
UNPAYWALL_EMAIL = os.environ.get("UNPAYWALL_EMAIL", "")


def _text_from_europepmc_xml(xml_bytes):
    root = ET.fromstring(xml_bytes)
    parts = [p.text for p in root.iter("p") if p.text]
    return "\n".join(parts).strip()


def _text_from_pdf_url(url):
    r = requests.get(url, timeout=30, headers={"User-Agent": "medical-rag-research/0.1"})
    r.raise_for_status()
    if "pdf" not in r.headers.get("Content-Type", "").lower() and not url.lower().endswith(".pdf"):
        return None
    reader = PdfReader(io.BytesIO(r.content))
    return "\n".join((p.extract_text() or "") for p in reader.pages).strip()


def get_full_text(pmcid=None, doi=None):
    """Returns (text, source) where source is one of
    'pmc_oa', 'europepmc', 'unpaywall', or (None, None) if nothing found."""
    if pmcid:
        try:
            r = requests.get(PMC_OA_S3.format(pmcid=pmcid), timeout=20)
            if r.ok and r.text.strip():
                log.info(f"full text via pmc_oa: {pmcid} ({len(r.text)} chars)")
                return r.text.strip(), "pmc_oa"
            log.debug(f"pmc_oa miss for {pmcid}: HTTP {r.status_code}")
        except requests.RequestException as e:
            log.warning(f"pmc_oa request failed for {pmcid}: {e}")

        try:
            r = requests.get(EUROPEPMC_FULLTEXT.format(pmcid=pmcid), timeout=30)
            if r.ok and r.content:
                text = _text_from_europepmc_xml(r.content)
                if text:
                    log.info(f"full text via europepmc: {pmcid} ({len(text)} chars)")
                    return text, "europepmc"
            log.debug(f"europepmc miss for {pmcid}: HTTP {r.status_code}")
        except (requests.RequestException, ET.ParseError) as e:
            log.warning(f"europepmc request failed for {pmcid}: {e}")

    if doi:
        try:
            r = requests.get(
                UNPAYWALL_API.format(doi=doi), params={"email": UNPAYWALL_EMAIL}, timeout=20
            )
            if r.ok:
                data = r.json()
                loc = data.get("best_oa_location") or {}
                pdf_url = loc.get("url_for_pdf") or loc.get("url")
                if pdf_url:
                    text = _text_from_pdf_url(pdf_url)
                    if text:
                        log.info(f"full text via unpaywall: {doi} ({len(text)} chars)")
                        return text, "unpaywall"
            log.debug(f"unpaywall miss for {doi}: HTTP {r.status_code}")
        except requests.RequestException as e:
            log.warning(f"unpaywall request failed for {doi}: {e}")

    log.info(f"no full text found (pmcid={pmcid}, doi={doi}) — abstract only")
    return None, None


def demo():
    # a known PMC-OA article (Bassi et al., pancreatic surgery outcomes definitions - open access)
    text, source = get_full_text(pmcid="PMC5013675")
    assert text and source == "pmc_oa", f"expected pmc_oa full text, got source={source}"
    print(f"OK: {source} full text, {len(text)} chars")


if __name__ == "__main__":
    demo()
