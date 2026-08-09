# ==========================================
# Domain Configuration
# Term lists are the source of truth: they build the search queries AND
# feed core/domains.py's classification (an article/trial/preprint is
# tagged with every domain whose terms it actually matches - MVP scope
# is surgery + the neurosurgery-adjacent slice of neurobiology, not all
# of neuroscience; see NEURO_BROAD_MESH_TERMS below for the road not taken).
# ==========================================

QDRANT_COLLECTION = "pubmed_surgery"

SURGERY_MESH_TERMS = [
    "Surgical Procedures, Operative", "General Surgery", "Perioperative Care",
    "Preoperative Care", "Postoperative Care", "Postoperative Complications",
    "Intraoperative Complications", "Anesthesia", "Venous Thromboembolism",
    "Antibiotic Prophylaxis", "Surgical Wound Infection", "Wound Healing",
    "Blood Loss, Surgical", "Blood Transfusion", "Minimally Invasive Surgical Procedures",
    "Robotic Surgical Procedures", "Laparoscopy", "Reoperation",
    "Postoperative Nausea and Vomiting", "Pain, Postoperative",
    "Enhanced Recovery After Surgery", "Patient Safety", "Length of Stay",
    "Critical Illness", "Wounds and Injuries",
    "Spinal Fusion",  # also in NEURO_NARROW below - done by both orthopedic and
                       # neurosurgeons, a genuine intersection case for the domains field
]

# Narrow: clinically/translationally adjacent to neurosurgery - the slice of
# neurobiology actually in scope for this MVP. Checked against a published
# neurosurgery-literature classification taxonomy (Oncology/Vascular/Spine/
# Functional/Trauma) - Spine and Functional were underrepresented, hence
# Spinal Fusion/Hydrocephalus/Deep Brain Stimulation below.
NEURO_NARROW_MESH_TERMS = [
    "Neurosurgical Procedures", "Neurosurgery", "Craniocerebral Trauma",
    "Brain Injuries", "Spinal Cord Injuries", "Brain Neoplasms",
    "Intracranial Hemorrhages", "Neuronal Plasticity", "Drug Resistant Epilepsy", "Stroke",
    "Spinal Fusion", "Hydrocephalus", "Deep Brain Stimulation", "Intracranial Aneurysm",
]

# Broad: general neuroscience incl. basic/molecular research - sized for
# comparison, NOT wired into the active query (see conversation: 0.62x the
# size of the surgery corpus alone, out of scope for the MVP).
NEURO_BROAD_MESH_TERMS = [
    "Neurosciences", "Neurons", "Nervous System Physiological Phenomena",
    "Neuronal Plasticity", "Neurodegenerative Diseases", "Synaptic Transmission",
    "Neural Pathways", "Central Nervous System",
]


def _mesh_or_query(terms):
    return "(" + " OR ".join(f'"{t}"[MeSH]' for t in terms) + ")"


NOT_RETRACTED = 'NOT "Retracted Publication"[pt]'

PUBMED_QUERY = f"{_mesh_or_query(SURGERY_MESH_TERMS)} {NOT_RETRACTED}"  # surgery only, kept for reference/backfill
NEURO_NARROW_QUERY = f"{_mesh_or_query(NEURO_NARROW_MESH_TERMS)} {NOT_RETRACTED}"
NEURO_BROAD_QUERY = f"{_mesh_or_query(NEURO_BROAD_MESH_TERMS)} {NOT_RETRACTED}"

# What jobs/sync.py actually queries: surgery OR neuro-narrow, one esearch
# pass - each returned article gets tagged with real MeSH-based domains
# after the fact (core/domains.py), not by which OR-branch matched.
COMBINED_PUBMED_QUERY = (
    f"({_mesh_or_query(SURGERY_MESH_TERMS)} OR {_mesh_or_query(NEURO_NARROW_MESH_TERMS)}) {NOT_RETRACTED}"
)

# ClinicalTrials.gov Query
CT_QUERY = (
    "(Surgery OR Surgical) OR "
    '(Neurosurgery OR "Brain Injury" OR "Spinal Cord Injury" OR Stroke OR Epilepsy)'
)

# Keyword lists for sources without real MeSH (CT.gov, medRxiv, bioRxiv) -
# used both to fetch (does this doc match at all) and to classify domain
# (core/domains.py checks which list(s) the matched keyword came from).
SURGERY_KEYWORDS = ["surgery", "surgical", "perioperative", "postoperative", "intraoperative"]
NEURO_KEYWORDS = [
    "neurosurgery", "neurosurgical", "brain injury", "spinal cord injury",
    "stroke", "epilepsy", "intracranial hemorrhage", "craniotomy", "neuroplasticity",
    "neuroscience", "neuron", "neural", "synap",
]

# medRxiv terms to search in title/abstract (clinical preprints) - kept as a
# fallback/reference, but medRxiv actually gets fetched by category below,
# which is author-assigned and far more precise than keyword matching.
MEDRXIV_TERMS = SURGERY_KEYWORDS + NEURO_KEYWORDS

# bioRxiv terms to search in title/abstract (basic-science preprints).
# NOT used by default - checked live (both by keyword and by its "neuroscience"
# category) and found overwhelmingly basic/molecular content, not what a
# surgical/neurosurgical department's clinicians actually want. Kept for
# reference in case scope changes later.
BIORXIV_TERMS = NEURO_KEYWORDS + SURGERY_KEYWORDS

# medRxiv category -> domain mapping. Author-assigned at submission, checked
# live against the full ~42-category list - these map cleanly onto our two
# domains (unlike bioRxiv, which has no clinical/surgical category at all).
MEDRXIV_DOMAIN_CATEGORIES = {
    "surgery": ["surgery"],
    "orthopedics": ["surgery"],
    "anesthesia": ["surgery"],
    "pain medicine": ["surgery"],
    "intensive care and critical care medicine": ["surgery"],
    "otolaryngology": ["surgery"],  # ENT surgery - a separate category from "surgery" itself
    "urology": ["surgery"],  # urologic surgery, same reasoning
    "rehabilitation medicine and physical therapy": ["surgery"],  # postoperative recovery, matches ERAS/Postoperative Care in the MeSH list
    "neurology": ["neurobiology"],
}


# ==========================================
# System Settings
# ==========================================
VECTOR_SIZE = 768  # MedCPT-Article-Encoder output dim
