import time
from typing import List, Tuple, Dict, Any, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from core.config import CT_QUERY

CT_API_BASE = "https://clinicaltrials.gov/api/v2/studies"

session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retries))


def search_ct_history(mindate: str, maxdate: str, query: str = CT_QUERY, page_size: int = 1000, page_token: Optional[str] = None) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    mindate = mindate.replace("/", "-")
    maxdate = maxdate.replace("/", "-")
    
    params = {
        "query.term": query,
        "filter.advanced": f"AREA[LastUpdatePostDate]RANGE[{mindate},{maxdate}]",
        "pageSize": page_size,
    }
    if page_token:
        params["pageToken"] = page_token
        
    r = session.get(CT_API_BASE, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    
    studies = data.get("studies", [])
    next_page = data.get("nextPageToken")
    return studies, next_page


def parse_ct_study(study_json: Dict[str, Any]) -> Dict[str, Any]:
    protocol = study_json.get("protocolSection", {})
    ident_mod = protocol.get("identificationModule", {})
    status_mod = protocol.get("statusModule", {})
    desc_mod = protocol.get("descriptionModule", {})
    cond_mod = protocol.get("conditionsModule", {})
    design_mod = protocol.get("designModule", {})
    
    nct_id = ident_mod.get("nctId", "")
    title = ident_mod.get("officialTitle") or ident_mod.get("briefTitle", "")
    
    brief_summary = desc_mod.get("briefSummary", "")
    detailed_desc = desc_mod.get("detailedDescription", "")
    full_text = f"{brief_summary}\n\n{detailed_desc}".strip()
    
    conditions = cond_mod.get("conditions", [])
    
    phases = design_mod.get("phases", [])
    pub_types = phases if phases else ["Clinical Trial"]
    
    last_update = status_mod.get("lastUpdatePostDateStruct", {}).get("date", "")
    
    return {
        "nctId": nct_id,
        "title": title,
        "abstract": brief_summary,
        "full_text": full_text,
        "mesh_terms": conditions,
        "pub_types": pub_types,
        "journal": "ClinicalTrials.gov",
        "doi": "",
        "pmcid": "",
        "edat": last_update,
    }
