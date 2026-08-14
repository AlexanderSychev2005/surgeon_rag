import io
import os

import requests
from dotenv import load_dotenv
from pypdf import PdfReader

from core.logsetup import get_logger

load_dotenv()
log = get_logger(__name__)

PMC_OA_S3 = "https://pmc-oa-opendata.s3.amazonaws.com/{pmcid}.1/{pmcid}.1.txt"
UNPAYWALL_API = "https://api.unpaywall.org/v2/{doi}"
UNPAYWALL_EMAIL = os.environ.get("UNPAYWALL_EMAIL", "")


def _text_from_pdf_url(url: str) -> str | None:
    r = requests.get(
        url, timeout=30, headers={"User-Agent": "medical-rag-research/0.1"}
    )
    r.raise_for_status()
    if not r.content.startswith(b"%PDF"):
        return None
    reader = PdfReader(io.BytesIO(r.content))
    return "\n".join((p.extract_text() or "") for p in reader.pages).strip()


def get_full_text(
    pmcid: str | None = None, doi: str | None = None
) -> tuple[str | None, str | None]:
    """Europe PMC used to be a fallback here too, but checked across two real
    bootstrap runs (700+ full-text hits): it never once contributed anything
    PMC OA S3 hadn't already found - its full-text indexing lags PMC's own OA
    bucket, so by the time we'd check it, PMC OA S3 had always already won.
    Dropped it: one less network round-trip per PMC-eligible article for zero
    measured benefit."""
    if pmcid:
        try:
            r = requests.get(PMC_OA_S3.format(pmcid=pmcid), timeout=20)
            if r.ok and r.text.strip():
                log.info(f"full text via pmc_oa: {pmcid} ({len(r.text)} chars)")
                return r.text.strip(), "pmc_oa"
            log.debug(f"pmc_oa miss for {pmcid}: HTTP {r.status_code}")
        except requests.RequestException as e:
            log.warning(f"pmc_oa request failed for {pmcid}: {e}")

    if doi:
        try:
            r = requests.get(
                UNPAYWALL_API.format(doi=doi),
                params={"email": UNPAYWALL_EMAIL},
                timeout=20,
            )
            if r.ok:
                data = r.json()
                loc = data.get("best_oa_location") or {}
                pdf_url = loc.get("url_for_pdf") or loc.get("url")
                if pdf_url:
                    try:
                        text = _text_from_pdf_url(pdf_url)
                    except Exception as e:
                        log.warning(f"pdf extraction failed for {doi} ({pdf_url}): {e}")
                        text = None
                    if text:
                        log.info(f"full text via unpaywall: {doi} ({len(text)} chars)")
                        return text, "unpaywall"
            log.debug(f"unpaywall miss for {doi}: HTTP {r.status_code}")
        except requests.RequestException as e:
            log.warning(f"unpaywall request failed for {doi}: {e}")

    log.info(f"no full text found (pmcid={pmcid}, doi={doi}) — abstract only")
    return None, None
