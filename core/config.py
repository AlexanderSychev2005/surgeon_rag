# ==========================================
# Domain Configuration
# Term lists are the source of truth for what's in scope: surgery +
# the neurosurgery-adjacent slice of neurobiology, not all of neuroscience
# (see NEURO_BROAD_MESH_TERMS below for the road not taken - checked live,
# 0.62x the size of the surgery corpus alone, ruled out for this MVP).
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
    "Spinal Fusion",  # also in NEURO_NARROW below - spine articles get indexed
                       # under either heading depending on the journal, listing
                       # it in both keeps the combined query from missing either
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
# comparison, NOT wired into the active query.
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

# What jobs/sync.py actually queries: surgery OR neuro-narrow, one esearch pass.
COMBINED_PUBMED_QUERY = (
    f"({_mesh_or_query(SURGERY_MESH_TERMS)} OR {_mesh_or_query(NEURO_NARROW_MESH_TERMS)}) {NOT_RETRACTED}"
)

# medRxiv categories to fetch - author-assigned at submission, checked live
# against the full ~42-category list; these map cleanly onto surgery +
# neurosurgery-adjacent content (bioRxiv has no clinical/surgical category
# at all, which is why it isn't a source here - see conversation history).
MEDRXIV_CATEGORIES = [
    "surgery", "orthopedics", "anesthesia", "pain medicine",
    "intensive care and critical care medicine",
    "otolaryngology",  # ENT surgery - a separate category from "surgery" itself
    "urology",  # urologic surgery, same reasoning
    "rehabilitation medicine and physical therapy",  # postoperative recovery, matches ERAS/Postoperative Care above
    "neurology",
]


# ==========================================
# System Settings
# ==========================================
VECTOR_SIZE = 768  # MedCPT-Article-Encoder output dim
