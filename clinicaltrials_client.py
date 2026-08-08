import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

CT_API_BASE = "https://clinicaltrials.gov/api/v2/studies"
SURGERY_CT_QUERY = "Surgery OR Surgical"

session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retries))

def search_ct_history(mindate: str, maxdate: str, query=SURGERY_CT_QUERY, page_size=1000, page_token=None):
    """
    mindate, maxdate in YYYY-MM-DD format.
    Uses LAST_UPDATE_POSTED to find trials updated or posted in the window.
    """
    # Convert YYYY/MM/DD to YYYY-MM-DD if needed
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
    total_count = data.get("totalCount", 0) # totalCount is often omitted unless countTotal=true, but we can just page.
    return studies, next_page

def parse_ct_study(study_json):
    """
    Extract relevant fields from a CT study JSON to a normalized dict similar to pubmed docs.
    """
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
    full_text = f"{brief_summary}\\n\\n{detailed_desc}".strip()
    
    conditions = cond_mod.get("conditions", [])
    
    phases = design_mod.get("phases", [])
    pub_types = phases if phases else ["Clinical Trial"]
    
    last_update = status_mod.get("lastUpdatePostDateStruct", {}).get("date", "")
    
    return {
        "nctId": nct_id,
        "title": title,
        "abstract": brief_summary, # treat summary as abstract
        "full_text": full_text,    # treat summary + desc as full text for chunking
        "mesh_terms": conditions,
        "pub_types": pub_types,
        "journal": "ClinicalTrials.gov",
        "doi": "",
        "pmcid": "",
        "edat": last_update, # use last update as the sync anchor
    }
