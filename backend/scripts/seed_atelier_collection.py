"""Idempotent seeder for Noir Atelier's Curated 100-Piece Maison Archive.

Preserves the 5 baseline fixtures (PRD-001..PRD-005) from `seed_demo.py` and
enriches the live PostgreSQL `noir` database to an exact 100-garment curated
collection spanning:
  - Atelier Essentials (₹1,899 – ₹6,999)
  - Signature Ready-to-Wear (₹7,500 – ₹49,500)
  - Private Client Reserve (₹52,000 – ₹98,000)
  - Haute Archive & Couture Editions (₹1,15,000 – ₹4,65,000)

Run:
    python -m backend.scripts.seed_atelier_collection
"""

from decimal import Decimal
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.app.database import get_sync_engine
from backend.app.models import (
    BusinessConfig,
    Category,
    Color,
    Material,
    PaymentMethod,
    Product,
    ProductImage,
    ProductMaterial,
    ProductReview,
    Recommendation,
    SearchSynonym,
)
from backend.app.reference_data import FIT_FEEDBACK_OPTIONS
from backend.app.services.inventory_service import Ref, open_balance
from backend.app.services.config_service import invalidate_config_cache
from backend.app.services.variant_service import set_variant_prices
from backend.app.storage.object_store import LocalObjectStore
from backend.scripts.seed_demo import seed_database

# Curated editorial photography archetypes (real fashion garments on Unsplash)
ARCHETYPE_IMAGES: Dict[str, str] = {
    "men_shirt_linen": "https://images.unsplash.com/photo-1596755094514-f87e34085b2c?auto=format&fit=crop&w=1000&q=85",
    "men_shirt_crisp": "https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?auto=format&fit=crop&w=1000&q=85",
    "men_tee": "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?auto=format&fit=crop&w=1000&q=85",
    "men_knit": "https://images.unsplash.com/photo-1614975059251-992f11792b9f?auto=format&fit=crop&w=1000&q=85",
    "men_blazer": "https://images.unsplash.com/photo-1507679799987-c73779587ccf?auto=format&fit=crop&w=1000&q=85",
    "men_coat": "https://images.unsplash.com/photo-1544022613-e87ca75a784a?auto=format&fit=crop&w=1000&q=85",
    "men_trousers": "https://images.unsplash.com/photo-1473966968600-fa801b869a1a?auto=format&fit=crop&w=1000&q=85",
    "men_couture": "https://images.unsplash.com/photo-1593030761757-71fae45fa0e7?auto=format&fit=crop&w=1000&q=85",
    "women_silk_dress": "https://images.unsplash.com/photo-1595777457583-95e059d581b8?auto=format&fit=crop&w=1000&q=85",
    "women_evening_gown": "https://images.unsplash.com/photo-1566174053879-31528523f8ae?auto=format&fit=crop&w=1000&q=85",
    "women_blouse": "https://images.unsplash.com/photo-1551163943-3f6a855d1153?auto=format&fit=crop&w=1000&q=85",
    "women_tee": "https://images.unsplash.com/photo-1503342217505-b0a15ec3261c?auto=format&fit=crop&w=1000&q=85",
    "women_blazer": "https://images.unsplash.com/photo-1591047139829-d91aecb6caea?auto=format&fit=crop&w=1000&q=85",
    "women_coat": "https://images.unsplash.com/photo-1539533018447-63fcce2678e3?auto=format&fit=crop&w=1000&q=85",
    "women_knit": "https://images.unsplash.com/photo-1576566588028-4147f3842f27?auto=format&fit=crop&w=1000&q=85",
    "women_trousers": "https://images.unsplash.com/photo-1594633312681-425c7b97ccd1?auto=format&fit=crop&w=1000&q=85",
    "women_couture": "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?auto=format&fit=crop&w=1000&q=85",
    "kids_knit": "https://images.unsplash.com/photo-1519238263530-99bdd11df2ea?auto=format&fit=crop&w=1000&q=85",
    "kids_festive": "https://images.unsplash.com/photo-1518831959646-742c3a14ebf7?auto=format&fit=crop&w=1000&q=85",
    "kids_linen": "https://images.unsplash.com/photo-1503919545889-aef636e10ad4?auto=format&fit=crop&w=1000&q=85",
}

EXTRA_CATEGORIES = [
    {"id": "CAT-13", "slug": "blouse", "name": "Silk Blouses & Tunics", "parent_id": "CAT-10", "order": 13},
    {"id": "CAT-22", "slug": "blazer", "name": "Tailored Blazers", "parent_id": "CAT-20", "order": 22},
    {"id": "CAT-23", "slug": "coat", "name": "Overcoats & Trenches", "parent_id": "CAT-20", "order": 23},
    {"id": "CAT-31", "slug": "cardigan", "name": "Cardigans & Wraps", "parent_id": "CAT-30", "order": 31},
    {"id": "CAT-41", "slug": "evening-gown", "name": "Evening Gowns", "parent_id": "CAT-40", "order": 41},
    {"id": "CAT-50", "slug": "trousers", "name": "Tailored Trousers", "parent_id": None, "order": 50},
    {"id": "CAT-60", "slug": "couture-archive", "name": "Haute Archive & Couture", "parent_id": None, "order": 60},
    {"id": "CAT-61", "slug": "ceremonial", "name": "Ceremonial & Bridal", "parent_id": "CAT-60", "order": 61},
]

CATEGORY_CODE_MAP: Dict[str, str] = {
    "CAT-TOP": "CAT-10",
    "CAT-SHT": "CAT-11",
    "CAT-TSH": "CAT-12",
    "CAT-BLS": "CAT-13",
    "CAT-OUT": "CAT-20",
    "CAT-OVR": "CAT-21",
    "CAT-BLZ": "CAT-22",
    "CAT-COT": "CAT-23",
    "CAT-KNT": "CAT-30",
    "CAT-CRD": "CAT-31",
    "CAT-DRS": "CAT-40",
    "CAT-GWN": "CAT-41",
    "CAT-TRS": "CAT-50",
    "CAT-CTR": "CAT-60",
    "CAT-CRM": "CAT-61",
}

EXTRA_COLORS = [
    ("Champagne Ecru", "white", "#EDE4D3", "CMP"),
    ("Espresso Umber", "brown", "#3B2B23", "ESP"),
    ("Camel Vicuna", "camel", "#B68F66", "CML"),
    ("Olive Moss", "green", "#4A5240", "OLV"),
    ("Celadon Sage", "green", "#7D8B78", "CLD"),
    ("Burgundy Oxblood", "burgundy", "#581F27", "BRG"),
    ("Antique Gold", "gold", "#A88952", "GLD"),
    ("Pearl Alabaster", "white", "#F5F2EB", "PRL"),
    ("Graphite Smoke", "grey", "#3A3B3C", "GRP"),
    ("Royal Indigo", "blue", "#1C2942", "IND"),
]

COLOR_NAME_MAP: Dict[str, str] = {
    "Ivory Chalk": "Ivory",
    "Charcoal Slate": "Charcoal",
}

MATERIAL_NAME_MAP: Dict[str, str] = {
    "European Flax Linen": "Belgian Linen",
    "Extra-Fine Merino Wool": "Merino Wool",
    "Peruvian Pima Cotton": "Pima Cotton",
}

EXTRA_MATERIALS = [
    ("Himalayan Cashmere", "cashmere"),
    ("Kani Pashmina", "pashmina"),
    ("Baby Alpaca", "alpaca"),
    ("Kanjeevaram Zari Silk", "silk"),
    ("Super 180s Virgin Wool", "wool"),
    ("Chanderi Silk Organza", "silk"),
    ("Belgian Bast Linen", "linen"),
    ("Sea Island Cotton", "cotton"),
    ("Vicuna & Baby Cashmere", "cashmere"),
]

EXTRA_SYNONYMS = [
    ("blouse", "product_type", "blouse"),
    ("tunic", "product_type", "blouse"),
    ("kurta", "product_type", "shirt"),
    ("blazer", "product_type", "blazer"),
    ("sportcoat", "product_type", "blazer"),
    ("jacket", "product_type", "outerwear"),
    ("coat", "product_type", "coat"),
    ("overcoat", "product_type", "coat"),
    ("trench", "product_type", "coat"),
    ("gown", "product_type", "evening-gown"),
    ("evening gown", "product_type", "evening-gown"),
    ("cardigan", "product_type", "cardigan"),
    ("trousers", "product_type", "trousers"),
    ("trouser", "product_type", "trousers"),
    ("pants", "product_type", "trousers"),
    ("chinos", "product_type", "trousers"),
    ("palazzo", "product_type", "trousers"),
    ("couture", "product_type", "couture-archive"),
    ("archive", "product_type", "couture-archive"),
    ("bridal", "product_type", "ceremonial"),
    ("lehenga", "product_type", "ceremonial"),
    ("sherwani", "product_type", "ceremonial"),
    ("bandhgala", "product_type", "ceremonial"),
    ("tuxedo", "product_type", "couture-archive"),
    ("cashmere", "material", "cashmere"),
    ("pashmina", "material", "pashmina"),
    ("vicuna", "material", "cashmere"),
    ("alpaca", "material", "alpaca"),
    ("kanjeevaram", "material", "silk"),
    ("banarasi", "material", "silk"),
    ("chanderi", "material", "silk"),
    ("zari", "material", "silk"),
    ("camel", "color", "camel"),
    ("tan", "color", "camel"),
    ("beige", "color", "white"),
    ("brown", "color", "brown"),
    ("espresso", "color", "brown"),
    ("green", "color", "green"),
    ("olive", "color", "green"),
    ("sage", "color", "green"),
    ("burgundy", "color", "burgundy"),
    ("oxblood", "color", "burgundy"),
    ("maroon", "color", "burgundy"),
    ("wine", "color", "burgundy"),
    ("gold", "color", "gold"),
    ("bronze", "color", "gold"),
]


def _adult_prices(base: int, sizes: Tuple[str, ...] = ("S", "M", "L", "XL"), step: int = 0) -> Dict[str, Decimal]:
    return {sz: Decimal(f"{base + idx * step}.00") for idx, sz in enumerate(sizes)}


def _kids_prices(base: int, step: int = 150) -> Dict[str, Decimal]:
    sizes = ("4Y", "6Y", "8Y", "10Y", "12Y")
    return {sz: Decimal(f"{base + idx * step}.00") for idx, sz in enumerate(sizes)}


# 95 curated garments (PRD-006 .. PRD-100) completing the 100-piece Maison Archive
# Tuple format:
# (num, dept, cat_id, name, color_name, color_code, hsn, materials_list, base_price, price_step, per_size_qty, origin, archetype, accent_tag, desc, fit, care, final_sale)
CURATED_95_SPECS: List[Tuple[Any, ...]] = [
    # --- MEN: ATELIER ESSENTIALS (PRD-006 .. PRD-017) ---
    (6, "MEN", "CAT-SHT", "Antwerp Washed Flax Mandarin Shirt", "Ivory Chalk", "IVR", "6205", [("European Flax Linen", 100)], 2499, 100, 6, "India", "men_shirt_linen", "100% Belgian Flax Linen", "Collarless mandarin placket tailored from pre-washed 165 GSM Belgian flax with natural mother-of-pearl buttons.", "Relaxed architectural cut; true to size.", "Cold gentle wash, line dry in shade, warm steam.", False),
    (7, "MEN", "CAT-SHT", "Como Striped Cotton Poplin Shirt", "Midnight Navy", "NVY", "6205", [("Sea Island Cotton", 100)], 4200, 0, 5, "Italy", "men_shirt_crisp", "120/2 Two-Fold Sea Island Poplin", "Woven in Como from two-fold long-staple cotton poplin with single-needle French side seams and split yoke.", "Tailored slim-regular silhouette.", "Machine wash 30C gentle, press while damp.", False),
    (8, "MEN", "CAT-TSH", "Sea Island Interlock Knit Polo", "Noir Black", "BLK", "6105", [("Sea Island Cotton", 100)], 3800, 0, 7, "Peru", "men_tee", "Gassed Sea Island Cotton", "Mercerized interlock polo with a clean three-button concealed placket and tailored jacket-friendly collar stand.", "Trim sartorial shoulder; take usual size.", "Cold gentle cycle, reshape and dry flat.", False),
    (9, "MEN", "CAT-TSH", "Heavyweight 260 GSM Pima Crewneck Tee", "Espresso Umber", "ESP", "6109", [("Peruvian Pima Cotton", 100)], 2299, 100, 8, "Peru", "men_tee", "260 GSM Peruvian Pima Jersey", "Compact-spun Peruvian Pima jersey offering an opaque, architectural drape that holds its collar line indefinitely.", "Boxy tailored torso; true to size.", "Cold wash inside out, do not tumble dry.", False),
    (10, "MEN", "CAT-TSH", "Fine-Ribbed Silk-Cotton Henley Top", "Pearl Alabaster", "PRL", "6109", [("Peruvian Pima Cotton", 70), ("Mulberry Silk", 30)], 4900, 0, 5, "Italy", "men_tee", "70% Pima Cotton · 30% Mulberry Silk", "Spun with mulberry silk for luminous lustre and natural thermoregulation beneath tailored jackets.", "Close layering fit.", "Hand wash cold with neutral silk detergent.", False),
    (11, "MEN", "CAT-SHT", "Botanical Dyed Bast Linen Camp Shirt", "Olive Moss", "OLV", "6205", [("Belgian Bast Linen", 100)], 5600, 0, 5, "India", "men_shirt_linen", "190 GSM Slub Bast Linen", "Open Cuban collar resort shirt cut with straight side vents and smoked trochus shell buttons.", "Breezy resort drape; true to size.", "Gentle cold wash or dry clean.", False),
    (12, "MEN", "CAT-KNT", "ZQ Merino Fine-Gauge Mockneck", "Charcoal Slate", "CHR", "6110", [("Extra-Fine Merino Wool", 100)], 6800, 0, 5, "Italy", "men_knit", "17.5-Micron ZQ Merino", "Fully-fashioned 16-gauge knit engineered to sit cleanly under unstructured tailoring without bulk.", "Refined slim cut.", "Hand wash cold or dry clean, dry flat.", False),
    (13, "MEN", "CAT-TRS", "Gurkha High-Waisted Cotton Twill Trousers", "Camel Vicuna", "CML", "6203", [("Sea Island Cotton", 98), ("Recycled Polyamide", 2)], 6400, 0, 5, "India", "men_trousers", "Brushed Cavalry Cotton Twill", "Double-buckled extended Gurkha waistband with deep forward pleats and crisp turn-up cuffs.", "High-rise tailored waist, tapered leg.", "Dry clean recommended or cold gentle press.", False),
    (14, "MEN", "CAT-SHT", "Shadow-Plaid Brushed Cotton Overshirt", "Graphite Smoke", "GRP", "6205", [("Peruvian Pima Cotton", 100)], 5900, 0, 5, "Portugal", "men_shirt_crisp", "Brushed Twill Flannel", "Softly peached mid-weight cotton twill shirt-jacket with horn buttons and twin chest patch pockets.", "Structured overshirt cut; room for tee underneath.", "Cold wash, hang dry.", False),
    (15, "MEN", "CAT-TSH", "Atelier Pique Resort Shirt-Polo", "Champagne Ecru", "CMP", "6105", [("Peruvian Pima Cotton", 100)], 3400, 0, 6, "India", "men_tee", "Honeycomb Pima Pique", "One-piece seamless Riviera collar crafted in breathable open-cell Pima pique.", "Tailored resort fit.", "Cold gentle machine wash.", False),
    (16, "MEN", "CAT-SHT", "Chambray Selvedge Workman Dress Shirt", "Royal Indigo", "IND", "6205", [("Sea Island Cotton", 100)], 6200, 0, 4, "Japan", "men_shirt_crisp", "Okayama Shuttle-Loom Cotton", "Yarn-dyed indigo shuttle-loom shirting finished with gusseted hems and mother-of-pearl buttons.", "Classic tailored fit.", "Wash separately cold; natural indigo character.", False),
    (17, "MEN", "CAT-TRS", "Drawstring Relaxed Belgian Linen Trousers", "Ivory Chalk", "IVR", "6203", [("European Flax Linen", 100)], 6900, 0, 5, "India", "men_trousers", "220 GSM Heavy Belgian Linen", "Tailored fly front with concealed internal braided drawcord for effortless warm-climate sophistication.", "Relaxed straight leg.", "Cold gentle wash, steam damp.", False),

    # --- MEN: SIGNATURE READY-TO-WEAR (PRD-018 .. PRD-034) ---
    (18, "MEN", "CAT-BLZ", "Biella Hopsack Unstructured Travel Blazer", "Midnight Navy", "NVY", "6203", [("Extra-Fine Merino Wool", 100)], 28500, 0, 4, "Italy", "men_blazer", "High-Twist Biella Wool Hopsack", "Half-canvassed Neapolitan soft-shoulder blazer in crease-resistant open-weave hopsack with Bemberg cupro butterfly lining.", "True tailored fit with natural shoulder.", "Specialist dry clean only.", False),
    (19, "MEN", "CAT-BLZ", "Solbiati Heavy Linen Double-Breasted Jacket", "Camel Vicuna", "CML", "6203", [("Belgian Bast Linen", 100)], 34000, 0, 3, "Italy", "men_blazer", "Solbiati 310 GSM Irish-Finish Linen", "Six-on-two peak-lapel jacket cut from weighty, rumple-resistant Solbiati linen with genuine dark horn buttons.", "Structured chest, softly nipped waist.", "Dry clean only; hang on wide cedar hanger.", False),
    (20, "MEN", "CAT-TRS", "Vitale Super 150s Flannel Double-Pleat Trousers", "Charcoal Slate", "CHR", "6203", [("Super 180s Virgin Wool", 100)], 16500, 0, 4, "Italy", "men_trousers", "Woollen-Spun Biella Flannel", "Side-tab adjusters, curtained sartorial waistband, and fluid drape across the thigh.", "Classic full drape; unfinished hem ready.", "Dry clean only.", False),
    (21, "MEN", "CAT-SHT", "22-Momme Washed Mulberry Silk Evening Shirt", "Noir Black", "BLK", "6205", [("Mulberry Silk", 100)], 18500, 0, 4, "Italy", "men_shirt_crisp", "Sandwashed 22-Momme Mulberry Silk", "Matte sandwashed silk habotai shirt with concealed French placket and smoked Agoya shell buttons.", "Fluid evening silhouette.", "Dry clean or cold hand wash in silk bath.", False),
    (22, "MEN", "CAT-KNT", "Himalayan 4-Ply Cashmere Crewneck Sweater", "Espresso Umber", "ESP", "6110", [("Himalayan Cashmere", 100)], 26000, 0, 3, "Nepal", "men_knit", "100% Grade-A Ladakhi Cashmere", "Combed high-altitude underfleece knitted in a dense 4-ply saddle-shoulder construction.", "Classic regular fit.", "Hand wash cold or specialist cashmere clean.", False),
    (23, "MEN", "CAT-CRD", "Shawl-Collar Ribbed Cashmere-Merino Cardigan", "Champagne Ecru", "CMP", "6110", [("Extra-Fine Merino Wool", 70), ("Himalayan Cashmere", 30)], 22500, 0, 3, "Scotland", "men_knit", "7-Gauge Fisherman Rib Wool-Cashmere", "Plush shawl-collar jacket-cardigan with leather-shanked horn buttons and deep welt pockets.", "Generous layering cut.", "Dry clean or cold wool hand wash, dry flat.", False),
    (24, "MEN", "CAT-COT", "Water-Repellent Gabardine Raglan Trench Coat", "Olive Moss", "OLV", "6201", [("Sea Island Cotton", 100)], 38500, 0, 3, "United Kingdom", "men_coat", "High-Density Ventile Cotton Gabardine", "Single-piece raglan sleeve storm coat woven from tightly twisted long-staple cotton that naturally repels rain.", "Overcoat proportions; fits cleanly over tailoring.", "Specialist dry clean and reproof as needed.", False),
    (25, "MEN", "CAT-OVR", "Brushed Baby Alpaca Shirt-Jacket", "Graphite Smoke", "GRP", "6201", [("Baby Alpaca", 85), ("Extra-Fine Merino Wool", 15)], 24500, 0, 3, "Peru", "men_coat", "Andean Baby Alpaca Boucle", "Featherlight yet deeply insulating shirt-jacket finished with hand-bound internal seams.", "Relaxed tailored overshirt.", "Dry clean only.", False),
    (26, "MEN", "CAT-TRS", "Raw Tussar Silk & Linen Pleated Resort Trousers", "Champagne Ecru", "CMP", "6203", [("Mulberry Silk", 55), ("European Flax Linen", 45)], 14800, 0, 4, "India", "men_trousers", "Handloom Tussar-Linen Blend", "Subtle slub texture combining wild silk lustre with crisp flax structure.", "Mid-rise straight leg.", "Dry clean only.", False),
    (27, "MEN", "CAT-BLZ", "Silk-Linen Herringbone Summer Sportcoat", "Pearl Alabaster", "PRL", "6203", [("Mulberry Silk", 52), ("European Flax Linen", 48)], 36500, 0, 3, "Italy", "men_blazer", "Como Silk-Linen Herringbone", "Quarter-lined warm-weather jacket with Milanese hand-sewn lapel buttonhole and patch pockets.", "Tailored fit.", "Dry clean only.", False),
    (28, "MEN", "CAT-SHT", "Hand-Loomed Chanderi Silk Kurta-Shirt", "Antique Gold", "GLD", "6205", [("Chanderi Silk Organza", 100)], 12500, 0, 4, "India", "men_couture", "Heritage Chanderi Handloom", "Subtly sheer ceremonial shirt crafted on pit looms in Madhya Pradesh with tonal resham placket.", "Relaxed straight cut.", "Dry clean only.", False),
    (29, "MEN", "CAT-KNT", "Mulberry Silk & Cashmere Fine Polo Sweater", "Burgundy Oxblood", "BRG", "6110", [("Himalayan Cashmere", 55), ("Mulberry Silk", 45)], 19800, 0, 4, "Italy", "men_knit", "Cashmere-Silk 18-Gauge Knit", "Featherweight luxury knit with fluid drape and a softly structured open polo collar.", "Trim fit.", "Hand wash cold or dry clean.", False),
    (30, "MEN", "CAT-COT", "Reversible Wool-Silk Car Coat", "Noir Black", "BLK", "6201", [("Super 180s Virgin Wool", 80), ("Mulberry Silk", 20)], 46000, 0, 3, "Italy", "men_coat", "Double-Woven Wool-Silk Twill", "Minimalist concealed-placket car coat reversing from matte obsidian wool to water-resistant silk taffeta.", "Architectural straight coat cut.", "Specialist dry clean.", False),
    (31, "MEN", "CAT-TRS", "Super 160s Barathea Evening Trousers", "Noir Black", "BLK", "6203", [("Super 180s Virgin Wool", 100)], 19500, 0, 4, "Italy", "men_trousers", "Pure Barathea Wool · Silk Galon", "Formal evening trousers finished with a single 18mm mulberry silk satin side braid and waist adjusters.", "Classic dinner suit cut.", "Dry clean only.", False),
    (32, "MEN", "CAT-OVR", "Suede-Finish Brushed Moleskin Field Jacket", "Espresso Umber", "ESP", "6201", [("Sea Island Cotton", 100)], 21500, 0, 3, "United Kingdom", "men_coat", "Lancashire Heavy Moleskin", "Four-pocket safari field jacket with internal drawcord waist and horn buttons.", "Tailored utility fit.", "Dry clean only.", False),
    (33, "MEN", "CAT-CRD", "Cable-Knit Baby Alpaca Zip Cardigan", "Royal Indigo", "IND", "6110", [("Baby Alpaca", 100)], 23000, 0, 3, "Peru", "men_knit", "Two-Way Riri Zip · Baby Alpaca", "Sculptural rope-cable knit with brushed palladium two-way zip hardware.", "Regular tailored fit.", "Dry clean or cold flat wash.", False),
    (34, "MEN", "CAT-SHT", "Pinpoint Oxford Bespoke Tab-Collar Shirt", "Pearl Alabaster", "PRL", "6205", [("Sea Island Cotton", 100)], 9200, 0, 5, "Italy", "men_shirt_crisp", "140/2 Two-Fold Pinpoint Cotton", "Crisp formal shirting with button-tab collar arch and mitred barrel cuffs.", "Slim tailored fit.", "Warm wash, press crisp.", False),

    # --- MEN: PRIVATE RESERVE & HAUTE ARCHIVE (PRD-035 .. PRD-043) ---
    (35, "MEN", "CAT-BLZ", "Hand-Tailored Mulberry Silk Velvet Smoking Jacket", "Burgundy Oxblood", "BRG", "6203", [("Mulberry Silk", 100)], 92000, 0, 2, "Italy", "men_couture", "Pure Silk Pile Velvet · Quilted Shawl", "Full-canvas evening smoking jacket featuring hand-quilted silk barathea shawl lapels and frog toggle closure.", "Bespoke evening cut.", "Specialist couture dry clean only.", False),
    (36, "MEN", "CAT-COT", "Double-Faced Mongolian Cashmere Belted Overcoat", "Noir Black", "BLK", "6201", [("Himalayan Cashmere", 100)], 165000, 0, 2, "Italy", "men_coat", "620 GSM Hand-Split Double Cashmere", "Individually hand-finished by master coatmakers with invisible pick-stitched edges—zero interlining for cloud-like warmth.", "Generous draped overcoat.", "Specialist couture dry clean only.", False),
    (37, "MEN", "CAT-CTR", "Savile-Cut Super 180s Wool & Silk Three-Piece Tuxedo", "Noir Black", "BLK", "6203", [("Super 180s Virgin Wool", 88), ("Mulberry Silk", 12)], 195000, 0, 2, "Italy", "men_blazer", "Super 180s Tasmanian Wool · Grosgrain Lapel", "Full floating horsehair canvas dinner suit complete with low-cut double-breasted waistcoat and silk-braided trousers.", "Classic Savile Row formal drape.", "Specialist couture dry clean only.", False),
    (38, "MEN", "CAT-CRM", "Varanasi Brocade & Antique Zari Bandhgala Jacket", "Antique Gold", "GLD", "6203", [("Kanjeevaram Zari Silk", 100)], 148000, 0, 2, "India", "men_couture", "Handloom Real Silver-Gilt Zari Brocade", "Woven over three weeks on traditional Varanasi jacquard pit looms and tailored with custom gilded enamel buttons.", "Regal structured bandhgala silhouette.", "Store in muslin wrap; specialist dry clean only.", False),
    (39, "MEN", "CAT-CRM", "Royal Hand-Spun Pashmina & Zardozi Sherwani", "Ivory Chalk", "IVR", "6203", [("Kani Pashmina", 100)], 245000, 0, 2, "India", "men_couture", "Pure Kashmiri Pashmina · 320 Artisan Hours", "Heirloom ceremonial sherwani hand-embroidered at collar and cuffs with fine metallic dabka and silk resham needlework.", "Bespoke ceremonial long-coat proportions.", "Acid-free archival box storage; couture specialist care.", False),
    (40, "MEN", "CAT-COT", "Loro-Weight Pure Cashmere Storm Greatcoat", "Camel Vicuna", "CML", "6201", [("Himalayan Cashmere", 100)], 310000, 0, 2, "Italy", "men_coat", "750 GSM Ripple-Finish Pure Cashmere", "Double-breasted ulster greatcoat with convertible storm collar, horn buttons, and silk-twill sleeve lining.", "Commanding full-length silhouette.", "Specialist luxury furrier/cashmere clean.", False),
    (41, "MEN", "CAT-CTR", "Biella Vicuna & Baby Cashmere Archive Overcoat", "Camel Vicuna", "CML", "6201", [("Vicuna & Baby Cashmere", 100)], 465000, 0, 1, "Italy", "men_coat", "Numbered Vault Edition · Certified Vicuna", "Our pinnacle menswear archive piece: ethically sheared Andean vicuna blended with 13.5-micron baby cashmere, hand-sewn over 64 hours.", "Tailored classic overcoat.", "Complimentary lifetime Noir Atelier specialist pressing & storage.", False),
    (42, "MEN", "CAT-BLZ", "Pure Cashmere Flannel Double-Breasted Suit", "Charcoal Slate", "CHR", "6203", [("Himalayan Cashmere", 95), ("Mulberry Silk", 5)], 135000, 0, 2, "Italy", "men_blazer", "Hand-Canvassed Cashmere-Silk Suiting", "Two-piece sartorial suit with hand-padded lapels, Milanese buttonholes, and high-waisted pleated trousers.", "Structured sartorial fit.", "Specialist dry clean only.", False),
    (43, "MEN", "CAT-CTR", "Srinagar Kani Loom Shawl-Lapel Dinner Jacket", "Midnight Navy", "NVY", "6203", [("Kani Pashmina", 75), ("Mulberry Silk", 25)], 78000, 0, 2, "India", "men_couture", "Authentic Wooden-Needle Kani Weave", "Subtle tonal Kani shawl lapels set against midnight silk-pashmina suiting.", "Tailored evening cut.", "Specialist dry clean only.", False),

    # --- WOMEN: ATELIER ESSENTIALS (PRD-044 .. PRD-055) ---
    (44, "WOMEN", "CAT-TSH", "Sculpted Boatneck Peruvian Pima Top", "Noir Black", "BLK", "6109", [("Peruvian Pima Cotton", 100)], 2199, 100, 7, "Peru", "women_tee", "Double-Jersey Peruvian Pima", "Clean architectural boat neckline with French-darted bust shaping in opaque double-knit Pima.", "Sleek body-skimming fit.", "Cold gentle wash, dry flat.", False),
    (45, "WOMEN", "CAT-BLS", "Crisp Sea Island Poplin Atelier Shirt", "Pearl Alabaster", "PRL", "6206", [("Sea Island Cotton", 100)], 4600, 0, 6, "Italy", "women_blouse", "120/2 Two-Fold Cotton Poplin", "Elongated French cuffs, concealed placket, and curved shirttail hem designed for effortless tucking or layering.", "Relaxed borrowed-from-tailoring cut.", "Machine wash 30C gentle, steam crisp.", False),
    (46, "WOMEN", "CAT-SHT", "Antwerp Washed Linen Resort Tunic", "Champagne Ecru", "CMP", "6206", [("European Flax Linen", 100)], 3900, 0, 6, "India", "women_blouse", "100% European Flax Linen", "Split V-neck airy tunic with shell buttons and side gussets.", "Flowing relaxed drape.", "Cold wash gentle, line dry.", False),
    (47, "WOMEN", "CAT-TSH", "Mulberry Silk-Rib Sleeveless Shell", "Ivory Chalk", "IVR", "6109", [("Mulberry Silk", 65), ("Peruvian Pima Cotton", 35)], 4800, 0, 6, "Italy", "women_tee", "Seamless Tubular Silk-Cotton Rib", "Knit on vintage circular machines without side seams for second-skin comfort beneath blazers.", "Close rib stretch fit.", "Hand wash cold.", False),
    (48, "WOMEN", "CAT-TRS", "High-Waist Wide-Leg Flax Linen Trousers", "Olive Moss", "OLV", "6204", [("European Flax Linen", 100)], 6500, 0, 5, "India", "women_trousers", "210 GSM Washed Belgian Linen", "Architectural double knife pleats elongating the leg with deep side pockets and invisible side zip.", "High-rise fitted waist, wide leg.", "Cold gentle wash or dry clean.", False),
    (49, "WOMEN", "CAT-KNT", "Superfine ZQ Merino Ballet-Neck Sweater", "Celadon Sage", "CLD", "6110", [("Extra-Fine Merino Wool", 100)], 6400, 0, 5, "Italy", "women_knit", "17.5-Micron ZQ Merino", "Delicate portrait neckline and elongated ribbed cuffs in featherlight merino.", "Feminine tailored fit.", "Cold wool cycle, dry flat.", False),
    (50, "WOMEN", "CAT-BLS", "Botanical-Dyed Cotton Voile Pintuck Blouse", "Champagne Ecru", "CMP", "6206", [("Sea Island Cotton", 100)], 5200, 0, 5, "India", "women_blouse", "Hand-Pintucked Mulmul Cotton", "48 micro-pintucks across the bib front crafted by master artisans with covered fabric buttons.", "Airy tailored bodice.", "Gentle cold hand wash.", False),
    (51, "WOMEN", "CAT-DRS", "Minimalist Poplin Belted Shirt Dress", "Midnight Navy", "NVY", "6204", [("Sea Island Cotton", 100)], 6900, 0, 5, "India", "women_silk_dress", "Crisp Long-Staple Cotton Poplin", "Midi-length architectural shirt dress with detachable self-fabric obi belt and side seam pockets.", "Cinched waist, A-line skirt.", "Cold wash, warm iron.", False),
    (52, "WOMEN", "CAT-CRD", "Fine-Gauge Merino Cropped Bolero Cardigan", "Noir Black", "BLK", "6110", [("Extra-Fine Merino Wool", 100)], 5800, 0, 5, "Italy", "women_knit", "18-Gauge Combed Merino", "Designed specifically to pair over bias-cut silk slip dresses without interrupting the waistline.", "Waist-skimming cropped cut.", "Hand wash cold, dry flat.", False),
    (53, "WOMEN", "CAT-TRS", "Tailored Stretch-Cotton Cigarette Ankle Trousers", "Espresso Umber", "ESP", "6204", [("Sea Island Cotton", 96), ("Recycled Polyamide", 4)], 6200, 0, 5, "Portugal", "women_trousers", "Sateen-Weave Compact Cotton", "Pressed centre-front creases and subtle ankle slits for day-to-evening versatility.", "Slim tailored leg.", "Machine wash cold gentle.", False),
    (54, "WOMEN", "CAT-TSH", "Draped Asymmetric Jersey Atelier Top", "Graphite Smoke", "GRP", "6109", [("Peruvian Pima Cotton", 100)], 3600, 0, 6, "Peru", "women_tee", "Silky Mercerized Pima Jersey", "Softly gathered shoulder pleats creating sculptural diagonal drape.", "True to size.", "Cold wash gentle.", False),
    (55, "WOMEN", "CAT-SHT", "Boyfriend Striped Belgian Linen Shirt", "Royal Indigo", "IND", "6206", [("European Flax Linen", 100)], 5400, 0, 5, "India", "women_blouse", "Yarn-Dyed Belgian Flax", "Generously proportioned shirting with dropped shoulders and luminous mother-of-pearl buttons.", "Oversized editorial fit.", "Cold gentle wash.", False),

    # --- WOMEN: SIGNATURE READY-TO-WEAR (PRD-056 .. PRD-074) ---
    (56, "WOMEN", "CAT-BLS", "22-Momme Como Silk Charmeuse Lavalliere Blouse", "Pearl Alabaster", "PRL", "6206", [("Mulberry Silk", 100)], 16800, 0, 4, "Italy", "women_blouse", "22-Momme Como Silk Charmeuse", "Fluid tie-neck blouse that can be knotted as a dramatic bow or worn loose as an evening scarf.", "Fluid tailored drape.", "Dry clean only.", False),
    (57, "WOMEN", "CAT-DRS", "Cowl-Back 25-Momme Silk Satin Midi Dress", "Burgundy Oxblood", "BRG", "6204", [("Mulberry Silk", 100)], 24500, 0, 3, "Italy", "women_silk_dress", "25-Momme Heavy Mulberry Satin", "Cut on the true 45-degree bias with a low sculptural cowl back and French-bound roulette straps.", "Bias cut moulds naturally to body.", "Specialist silk dry clean.", False),
    (58, "WOMEN", "CAT-BLZ", "Sculpted Hourglass Virgin Wool Bar Blazer", "Noir Black", "BLK", "6204", [("Super 180s Virgin Wool", 100)], 36000, 0, 3, "Italy", "women_blazer", "Architectural Barathea Wool", "Nipped waist and softly rounded peplum hip inspired by mid-century Parisian haute couture.", "Contoured sartorial fit.", "Dry clean only.", False),
    (59, "WOMEN", "CAT-TRS", "Fluid 22-Momme Mulberry Silk Palazzo Trousers", "Noir Black", "BLK", "6204", [("Mulberry Silk", 100)], 19500, 0, 4, "Italy", "women_trousers", "Heavy Silk Crepe de Chine", "Floor-grazing wide-leg evening trousers lined in breathable silk habotai.", "High waist, sweeping palazzo leg.", "Dry clean only.", False),
    (60, "WOMEN", "CAT-CRD", "Pure Himalayan Cashmere Belted Wrap Cardigan", "Camel Vicuna", "CML", "6110", [("Himalayan Cashmere", 100)], 28500, 0, 3, "Nepal", "women_knit", "100% Combed Himalayan Cashmere", "Cocooning robe-style knit coatigan with wide ribbed shawl lapels and waist tie.", "Relaxed wrap fit.", "Hand wash cold or dry clean.", False),
    (61, "WOMEN", "CAT-DRS", "Chanderi Silk-Organza Hand-Block Midi Dress", "Celadon Sage", "CLD", "6204", [("Chanderi Silk Organza", 100)], 18200, 0, 4, "India", "women_silk_dress", "Handwoven Chanderi Silk · Cotton Slip", "Translucent gossamer silk organza layered over a detachable organic Pima slip with tonal resham edging.", "Floaty tiered silhouette.", "Dry clean only.", False),
    (62, "WOMEN", "CAT-COT", "Belted Storm-Flap Cotton-Silk Trench Coat", "Champagne Ecru", "CMP", "6202", [("Sea Island Cotton", 72), ("Mulberry Silk", 28)], 42000, 0, 3, "Italy", "women_coat", "Water-Repellent Cotton-Silk Twill", "Subtle pearlised sheen with leather-covered buckles, gun flap, and deep inverted back pleat.", "Classic trench proportions.", "Specialist dry clean.", False),
    (63, "WOMEN", "CAT-KNT", "Baby Alpaca & Silk Turtleneck Poncho Knit", "Ivory Chalk", "IVR", "6110", [("Baby Alpaca", 75), ("Mulberry Silk", 25)], 21000, 0, 3, "Peru", "women_knit", "Cloud-Spun Baby Alpaca & Silk", "Architectural cape-like drape with fitted rib lower sleeves for effortless winter layering.", "Relaxed cape fit.", "Dry clean only.", False),
    (64, "WOMEN", "CAT-BLZ", "Solbiati Ecru Linen Double-Breasted Suit Blazer", "Ivory Chalk", "IVR", "6204", [("Belgian Bast Linen", 100)], 31500, 0, 3, "Italy", "women_blazer", "300 GSM Heavy Belgian Linen", "Sharp peak lapels and natural corozo buttons; pairs seamlessly with our wide-leg flax trousers.", "Tailored menswear-inspired cut.", "Dry clean only.", False),
    (65, "WOMEN", "CAT-TRS", "Super 160s Wool Crepe High-Waist Pleated Pants", "Charcoal Slate", "CHR", "6204", [("Super 180s Virgin Wool", 100)], 17800, 0, 4, "Italy", "women_trousers", "High-Twist Crepe Wool", "Fluid movement and zero wrinkling from morning flights to evening gallery openings.", "True high-rise tailored fit.", "Dry clean only.", False),
    (66, "WOMEN", "CAT-DRS", "Draped Asymmetric Jersey-Silk Column Midi", "Espresso Umber", "ESP", "6104", [("Mulberry Silk", 80), ("Recycled Polyamide", 20)], 26500, 0, 3, "Italy", "women_silk_dress", "Fluid Silk Milano Knit", "Grecian-inspired shoulder gather cascading into a sleek calf-length column.", "Sculpted stretch drape.", "Dry clean only.", False),
    (67, "WOMEN", "CAT-BLS", "Sheer Silk Organza Puff-Sleeve Evening Shirt", "Noir Black", "BLK", "6206", [("Chanderi Silk Organza", 100)], 15400, 0, 4, "India", "women_blouse", "Crisp Pure Silk Organza · Silk Cami Included", "Architectural volume sleeves balanced by a sharp couture point collar and silk camisole.", "Structured sheer silhouette.", "Dry clean only.", False),
    (68, "WOMEN", "CAT-KNT", "Pure Cashmere Boatneck Lounge Tunic", "Graphite Smoke", "GRP", "6110", [("Himalayan Cashmere", 100)], 24000, 0, 3, "Scotland", "women_knit", "2-Ply Scottish-Spun Cashmere", "Side-slit elongated tunic crafted for travel and quiet weekends.", "Relaxed tunic drape.", "Cold cashmere hand wash, dry flat.", False),
    (69, "WOMEN", "CAT-GWN", "Liquid 30-Momme Silk Halter Evening Gown", "Antique Gold", "GLD", "6204", [("Mulberry Silk", 100)], 48500, 0, 3, "Italy", "women_evening_gown", "30-Momme Couture-Weight Charmeuse", "Pooling hemline and hand-twisted silk neck collar glowing like molten champagne bronze.", "Floor-sweeping bias fit.", "Specialist silk dry clean.", False),
    (70, "WOMEN", "CAT-COT", "Unlined Double-Faced Wool-Cashmere Short Coat", "Olive Moss", "OLV", "6202", [("Super 180s Virgin Wool", 85), ("Himalayan Cashmere", 15)], 46500, 0, 3, "Italy", "women_coat", "Hand-Finished Double-Faced Cloth", "Cropped cocoon silhouette with wide kimono sleeves and invisible snap closures.", "Relaxed sculptural fit.", "Specialist dry clean.", False),
    (71, "WOMEN", "CAT-DRS", "Handloom Tussar & Mulberry Silk Wrap Dress", "Camel Vicuna", "CML", "6204", [("Mulberry Silk", 100)], 21500, 0, 3, "India", "women_silk_dress", "Artisanal Loom-Textured Silk", "True wrap construction with wide obi sash and concealed internal stay button.", "Adjustable wrap waist.", "Dry clean only.", False),
    (72, "WOMEN", "CAT-BLZ", "Collarless Boucle Tweed Couture Jacket", "Pearl Alabaster", "PRL", "6204", [("Super 180s Virgin Wool", 70), ("Mulberry Silk", 30)], 39500, 0, 3, "France", "women_blazer", "French Ribbon-Yarn Wool-Silk Tweed", "Braided selvedge trim, four patch pockets, and custom brushed-bronze NA monogrammed buttons.", "Boxy cropped Parisian cut.", "Specialist dry clean.", False),
    (73, "WOMEN", "CAT-TRS", "Cashmere-Blend Knitted Lounge Wide Trousers", "Champagne Ecru", "CMP", "6104", [("Extra-Fine Merino Wool", 70), ("Himalayan Cashmere", 30)], 16200, 0, 4, "Italy", "women_trousers", " Milano-Stitched Wool-Cashmere", "Tailored knit trousers combining sofa-level softness with crisp vertical drape.", "Elasticated smooth high waist.", "Hand wash cold, dry flat.", False),
    (74, "WOMEN", "CAT-BLS", "Hand-Embroidered Parsi Gara Silk Tunic", "Midnight Navy", "NVY", "6206", [("Mulberry Silk", 100)], 32000, 0, 3, "India", "women_couture", "Heritage Silk Crepe · Hand Satin-Stitch", "Delicate ivory avian and botanical motifs hand-embroidered along the neckline and cuffs.", "Straight tailored tunic.", "Specialist dry clean only.", False),

    # --- WOMEN: PRIVATE RESERVE & HAUTE ARCHIVE (PRD-075 .. PRD-085) ---
    (75, "WOMEN", "CAT-GWN", "Sculpted Silk Faille Off-Shoulder Opera Gown", "Noir Black", "BLK", "6204", [("Mulberry Silk", 100)], 88000, 0, 2, "Italy", "women_evening_gown", "Internal Corsetry · Pure Silk Faille", "Architectural folded portrait neckline with internal boned bodice and dramatic cathedral back pleat.", "Couture structured bodice; true to size.", "Specialist couture dry clean.", False),
    (76, "WOMEN", "CAT-COT", "Pure Cashmere Double-Faced Belted Maxi Coat", "Pearl Alabaster", "PRL", "6202", [("Himalayan Cashmere", 100)], 185000, 0, 2, "Italy", "women_coat", "640 GSM Pure Cashmere · Hand Pick-Stitched", "Ankle-grazing winter icon hand-finished without lining so two layers of pure cashmere move as one.", "Generous wrap silhouette.", "Specialist cashmere dry clean.", False),
    (77, "WOMEN", "CAT-CTR", "Double-Faced Mongolian Cashmere Opera Cape", "Camel Vicuna", "CML", "6202", [("Himalayan Cashmere", 100)], 145000, 0, 2, "Italy", "women_coat", "Pure Cashmere · Horn Toggle Collar", "Sweeping tailored cape with concealed arm slits and hand-stitched buffalo leather piping.", "One effortless tailored drape across S–XL.", "Specialist dry clean only.", False),
    (78, "WOMEN", "CAT-GWN", "30-Momme Mulberry Silk Hand-Beaded Column Gown", "Champagne Ecru", "CMP", "6204", [("Mulberry Silk", 100)], 265000, 0, 2, "India", "women_evening_gown", "280 Hours Hand Micro-Glass & Zari Embroidery", "Luminous bias-cut silk column encrusted by master karigars with tonal micro-cut glass beads and fine metallic thread.", "Sleek couture column.", "Archival muslin bag included; specialist couture care.", False),
    (79, "WOMEN", "CAT-CRM", "Banarasi Pure Tissue-Silk Draped Couture Sari Gown", "Antique Gold", "GLD", "6204", [("Kanjeevaram Zari Silk", 100)], 168000, 0, 2, "India", "women_couture", "Handloom Real Zari Tissue · Pre-Sculpted Pallu", "Merges six yards of handwoven Varanasi gold-tissue silk with modern corseted evening construction.", "Structured bodice with fluid draped skirt.", "Store wrapped in unbleached mulmul; couture dry clean.", False),
    (80, "WOMEN", "CAT-CRM", "Srinagar Kani Pashmina & Zardozi Opera Coat", "Burgundy Oxblood", "BRG", "6202", [("Kani Pashmina", 100)], 385000, 0, 2, "India", "women_couture", "Numbered Vault Edition · 420 Loom & Needle Hours", "Woven with wooden tujis in Kashmir from 14-micron Changthangi pashmina and finished with antique gold zardozi borders.", "Regal full-length evening coat.", "Lifetime Noir Atelier archival care & insured storage.", False),
    (81, "WOMEN", "CAT-CRM", "Kanchipuram Pure Mulberry & Korvai Zari Couture Lehenga", "Burgundy Oxblood", "BRG", "6204", [("Kanjeevaram Zari Silk", 100)], 425000, 0, 1, "India", "women_couture", "Numbered Bridal Archive · 24K Electroplated Silver Zari", "Three-piece heirloom ensemble: 24-kali handwoven temple-border silk skirt, sculpted blouse, and Chanderi-zari dupatta.", "Custom-allowance seams for private fitting.", "Delivered in cedar-lined archival trunk; specialist care.", False),
    (82, "WOMEN", "CAT-CTR", "Atelier Sculpted Virgin Wool & Silk Evening Tuxedo", "Pearl Alabaster", "PRL", "6204", [("Super 180s Virgin Wool", 82), ("Mulberry Silk", 18)], 96000, 0, 2, "Italy", "women_blazer", "Ivory Silk Satin Peak Lapels", "Two-piece women's smoking tuxedo with satin-covered buttons and elongated flare-leg evening trousers.", "Sharp tailored evening cut.", "Specialist dry clean only.", False),
    (83, "WOMEN", "CAT-GWN", "Silk Velvet & Organza Sculpted Gown", "Royal Indigo", "IND", "6204", [("Mulberry Silk", 100)], 125000, 0, 2, "Italy", "women_evening_gown", "Como Silk Velvet · Architectural Organza Stole", "Deep midnight silk velvet column paired with a detachable cloud-like silk organza shoulder train.", "Fitted evening column.", "Specialist couture dry clean.", False),
    (84, "WOMEN", "CAT-COT", "Baby Alpaca & Cashmere Fur-Free Shearling Coat", "Ivory Chalk", "IVR", "6202", [("Baby Alpaca", 70), ("Himalayan Cashmere", 30)], 115000, 0, 2, "Peru", "women_coat", "Woven Fleeced Alpaca-Cashmere Pile", "Ultra-plush cruelty-free teddy weave delivering extraordinary loft without synthetic fibers.", "Cocoon overcoat fit.", "Specialist dry clean.", False),
    (85, "WOMEN", "CAT-CTR", "Hand-Painted Kalamkari & Mulberry Silk Couture Cape Set", "Espresso Umber", "ESP", "6204", [("Mulberry Silk", 100)], 74000, 0, 2, "India", "women_couture", "Natural Mineral Dye Pen-Kalamkari on Silk", "Freehand bamboo-pen botanical artwork executed with natural indigo, myrobalan, and madder root over heavy mulberry silk.", "Flowing cape over tailored silk trousers.", "Specialist dry clean away from direct sunlight.", False),

    # --- KIDS: HEIRLOOM ESSENTIALS & CEREMONIAL ARCHIVE (PRD-086 .. PRD-100) ---
    (86, "KIDS", "CAT-SHT", "Junior Belgian Flax Mandarin Collar Shirt", "Ivory Chalk", "IVR", "6205", [("European Flax Linen", 100)], 2199, 100, 6, "India", "kids_linen", "Soft-Washed Belgian Flax", "Pre-softened breathable linen shirt with smooth rounded shell buttons safe for young skin.", "Comfort Heirloom kids cut.", "Gentle machine wash 30C.", False),
    (87, "KIDS", "CAT-TSH", "Organic Peruvian Pima Striped Breton Tee", "Midnight Navy", "NVY", "6109", [("Peruvian Pima Cotton", 100)], 1899, 100, 7, "Peru", "kids_linen", "100% Organic Pima Cotton", "Yarn-dyed nautical stripes in ultra-soft hypoallergenic Pima cotton jersey.", "Easy everyday play & travel fit.", "Machine wash cold.", False),
    (88, "KIDS", "CAT-DRS", "Hand-Smocked Sea Island Cotton Party Dress", "Pearl Alabaster", "PRL", "6204", [("Sea Island Cotton", 100)], 4800, 150, 5, "India", "kids_festive", "Artisanal Honeycomb Hand-Smocking", "Peter Pan collar, French seams throughout, and full cotton voile petticoat lining.", "Classic heirloom silhouette with sash tie.", "Gentle cold wash, line dry.", False),
    (89, "KIDS", "CAT-CRD", "ZQ Merino Heirloom Cable Cardigan", "Champagne Ecru", "CMP", "6110", [("Extra-Fine Merino Wool", 100)], 3600, 150, 5, "Italy", "kids_knit", "Itch-Free 17.5-Micron Merino", "Softly structured diamond-cable knit with natural corozo nut buttons.", "Roomy layering cut.", "Gentle wool wash 30C, dry flat.", False),
    (90, "KIDS", "CAT-TRS", "Junior Tailored Linen-Cotton Pleated Shorts & Trousers", "Camel Vicuna", "CML", "6203", [("European Flax Linen", 55), ("Sea Island Cotton", 45)], 2900, 100, 6, "India", "kids_linen", "Adjustable Internal Button Waist", "Smart tailored trousers with hidden elastic buttonhole tabs to grow across seasons.", "Comfort tailored fit.", "Machine wash cold gentle.", False),
    (91, "KIDS", "CAT-KNT", "Pure Himalayan Cashmere Junior Crewneck", "Celadon Sage", "CLD", "6110", [("Himalayan Cashmere", 100)], 8900, 250, 4, "Nepal", "kids_knit", "Featherlight Grade-A Cashmere", "Cloud-soft hypoallergenic cashmere sweater crafted for sensitive young skin.", "Classic comfort fit.", "Cold hand wash, dry flat.", False),
    (92, "KIDS", "CAT-DRS", "Chanderi Silk & Mulmul Festive Frock", "Antique Gold", "GLD", "6204", [("Chanderi Silk Organza", 60), ("Sea Island Cotton", 40)], 7800, 200, 4, "India", "kids_festive", "Soft Mulmul Lining · Zero Scratchy Seams", "Luminous festive Chanderi dress fully enclosed with organic cotton mulmul lining so no metallic thread touches skin.", "Twirl-friendly flared skirt.", "Dry clean recommended.", False),
    (93, "KIDS", "CAT-CRM", "Junior Mulberry Silk Kurta & Bandi Waistcoat Set", "Royal Indigo", "IND", "6203", [("Mulberry Silk", 100)], 11500, 300, 4, "India", "kids_festive", "3-Piece Ceremonial Silk Ensemble", "Quilted mulberry silk Nehru waistcoat paired with ivory silk-cotton kurta and elasticated pyjama.", "Easy movement ceremonial cut.", "Dry clean only.", False),
    (94, "KIDS", "CAT-COT", "Miniature Virgin Wool Double-Breasted Pea Coat", "Midnight Navy", "NVY", "6201", [("Super 180s Virgin Wool", 90), ("Himalayan Cashmere", 10)], 14500, 400, 3, "Italy", "kids_knit", "Soft Wool-Cashmere Melton", "Classic anchor-button winter coat lined in smooth breathable viscose-silk.", "Coat fit over knitwear.", "Dry clean only.", False),
    (95, "KIDS", "CAT-CRM", "Heirloom Banarasi Silk Junior Lehenga Set", "Burgundy Oxblood", "BRG", "6204", [("Kanjeevaram Zari Silk", 100)], 24500, 500, 3, "India", "kids_festive", "Handwoven Silk · Soft Cotton Backing", "Lightweight handloom silk ceremonial skirt and blouse engineered for effortless comfort during family celebrations.", "Adjustable drawstring & hook waist.", "Dry clean only.", False),
    (96, "KIDS", "CAT-BLZ", "Junior Unstructured Linen-Wool Ceremonial Blazer", "Charcoal Slate", "CHR", "6203", [("Extra-Fine Merino Wool", 60), ("European Flax Linen", 40)], 9800, 250, 4, "Italy", "kids_linen", "Stretch-Comfort Unlined Shoulder", "Tailored single-breasted blazer that moves like a cardigan for weddings and recitals.", "True to age size.", "Dry clean only.", False),
    (97, "KIDS", "CAT-DRS", "Pure Mulberry Silk Velvet Winter Party Dress", "Burgundy Oxblood", "BRG", "6204", [("Mulberry Silk", 100)], 12800, 300, 3, "Italy", "kids_festive", "Plush Silk Velvet · Ecru Silk Collar", "Heirloom holiday dress with contrasting ecru silk-crepe collar and covered back buttons.", "Classic A-line silhouette.", "Specialist dry clean.", False),
    (98, "KIDS", "CAT-KNT", "Baby Alpaca & Merino Hooded Knit Coat", "Ivory Chalk", "IVR", "6110", [("Baby Alpaca", 70), ("Extra-Fine Merino Wool", 30)], 8400, 200, 4, "Peru", "kids_knit", "Hand-Finished Wooden Toggles", "Cozy hooded knit coat crafted from sustainably sheared Peruvian alpaca and merino.", "Relaxed outer-knit fit.", "Hand wash cold, dry flat.", False),
    (99, "KIDS", "CAT-SHT", "Hand-Embroidered Cotton Voile Family Kurta", "Pearl Alabaster", "PRL", "6205", [("Sea Island Cotton", 100)], 3800, 150, 5, "India", "kids_linen", "Tonal Chikankari Shadow-Work", "Featherlight Lucknowi shadow-work embroidery on breathable long-staple cotton voile.", "Relaxed comfort fit.", "Cold gentle hand wash.", False),
    (100, "KIDS", "CAT-CRM", "Archive Pashmina & Silk Ceremonial Sherwani Set", "Champagne Ecru", "CMP", "6203", [("Kani Pashmina", 60), ("Mulberry Silk", 40)], 38000, 800, 2, "India", "kids_festive", "Bespoke Junior Ceremonial Archive", "Hand-finished miniature ceremonial sherwani matching our Men's Haute Archive collection.", "Tailored ceremonial cut.", "Store in muslin garment pouch; specialist dry clean.", False),
]


def _ensure_archetype_images(object_store: LocalObjectStore) -> Dict[str, Path]:
    cache_dir = object_store.root / "editorial-archetypes"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Reliable local fallback from existing PRD-001..005 JPEGs
    fallback_candidates = [
        object_store.root / "products" / f"PRD-00{i}" / "product.jpg"
        for i in range(1, 6)
        if (object_store.root / "products" / f"PRD-00{i}" / "product.jpg").exists()
    ]
    default_fallback = fallback_candidates[0] if fallback_candidates else None

    resolved: Dict[str, Path] = {}
    with httpx.Client(timeout=12.0, follow_redirects=True) as client:
        for key, url in ARCHETYPE_IMAGES.items():
            target = cache_dir / f"{key}.jpg"
            if not target.exists() or target.stat().st_size < 1024:
                try:
                    resp = client.get(url)
                    if resp.status_code == 200 and len(resp.content) > 1024:
                        target.write_bytes(resp.content)
                except Exception:
                    pass
            if target.exists() and target.stat().st_size >= 1024:
                resolved[key] = target
            elif default_fallback is not None:
                resolved[key] = default_fallback
    return resolved


def seed_atelier_collection(engine: Optional[Engine] = None) -> Dict[str, Any]:
    eng = engine or get_sync_engine()
    # Ensure baseline schema, 41 tables, policies, permissions, and PRD-001..PRD-005 exist
    seed_database(eng)
    object_store = LocalObjectStore()
    archetype_files = _ensure_archetype_images(object_store)

    with Session(eng) as session:
        # 1. Upsert expanded luxury taxonomy categories (flush each so parent FK exists)
        for c in EXTRA_CATEGORIES:
            existing_cat = session.get(Category, c["id"])
            if existing_cat is None:
                session.add(
                    Category(
                        category_id=c["id"],
                        slug=c["slug"],
                        name=c["name"],
                        parent_id=c["parent_id"],
                        display_order=c["order"],
                        is_active=True,
                    )
                )
                session.flush()

        # 2. Upsert expanded colour palette
        color_ids: Dict[str, int] = {
            row.name: row.color_id for row in session.scalars(select(Color)).all()
        }
        for name, family, hex_code, _code in EXTRA_COLORS:
            if name not in color_ids:
                col = Color(name=name, family=family, hex_code=hex_code)
                session.add(col)
                session.flush()
                color_ids[name] = col.color_id

        # 3. Upsert expanded natural luxury fibers
        material_ids: Dict[str, int] = {
            row.name: row.material_id for row in session.scalars(select(Material)).all()
        }
        for name, family in EXTRA_MATERIALS:
            if name not in material_ids:
                mat = Material(name=name, family=family)
                session.add(mat)
                session.flush()
                material_ids[name] = mat.material_id

        # 4. Upsert expanded natural-language search synonyms
        existing_terms = set(session.scalars(select(SearchSynonym.term)).all())
        for term, dim, val in EXTRA_SYNONYMS:
            if term not in existing_terms:
                session.add(SearchSynonym(term=term, dimension=dim, value=val, is_active=True))
                existing_terms.add(term)

        # 5. Update payment method ceilings for multi-lakh Haute Archive orders
        pm_limits = {
            "upi": ("UPI (Instant · Up to ₹1,00,000)", Decimal("1.00"), Decimal("100000.00")),
            "card": ("Credit / Debit Card", Decimal("1.00"), Decimal("1500000.00")),
            "bank_transfer": ("IMPS / RTGS / NEFT Private Wire", Decimal("1.00"), Decimal("5000000.00")),
            "emi": ("No-Cost Atelier EMI", Decimal("5000.00"), Decimal("500000.00")),
        }
        for mid, (mname, min_v, max_v) in pm_limits.items():
            pm = session.get(PaymentMethod, mid)
            if pm is not None:
                pm.name = mname
                pm.min_order_inr = min_v
                pm.max_order_inr = max_v

        # 6. Enrich BusinessConfig for the 100-piece Curated Maison positioning
        cat_cfg = session.scalar(select(BusinessConfig).where(BusinessConfig.config_key == "catalog"))
        custom_tiers = [
            {"id": "ALL", "label": "All Editions", "min_price": None, "max_price": None},
            {"id": "ESSENTIAL", "label": "Essentials · Up to ₹6,999", "min_price": None, "max_price": 6999},
            {"id": "SIGNATURE", "label": "Ready-to-Wear · ₹7,000 – ₹49,999", "min_price": 7000, "max_price": 49999},
            {"id": "PRIVATE_RESERVE", "label": "Private Reserve · ₹50,000 – ₹99,999", "min_price": 50000, "max_price": 99999},
            {"id": "HAUTE_ARCHIVE", "label": "Haute Archive · ₹1,00,000+", "min_price": 100000, "max_price": None},
        ]
        cat_payload = {
            "luxury_tier_min_inr": 7000,
            "high_value_tier_min_inr": 50000,
            "couture_tier_min_inr": 100000,
            "curated_collection_target": 100,
            "custom_price_tiers": custom_tiers,
            "fit_feedback_options": list(FIT_FEEDBACK_OPTIONS),
        }
        if cat_cfg is not None:
            cat_cfg.config_value = cat_payload
        else:
            session.add(BusinessConfig(config_key="catalog", config_value=cat_payload, updated_by="seed_atelier"))

        ui_cfg = session.scalar(select(BusinessConfig).where(BusinessConfig.config_key == "storefront_ui"))
        ui_payload = {
            "hero_eyebrow": "Maison de Haute Confection · Curated 100-Piece Archive",
            "hero_title": "The New Edit",
            "hero_subtitle": (
                "An intimate edit of 100 natural-fiber garments—from everyday Belgian flax shirting and "
                "Como mulberry silk to numbered Kashmiri Kani pashmina and bridal couture pieces."
            ),
            "hero_image_url": "/media/products/PRD-080/product.jpg",
            "hero_image_alt": "Noir Atelier Editorial Collection",
            "ai_quick_prompts": [
                {"label": "Haute Archive pieces (₹1L+)", "prompt": "Show me Haute Archive couture garments above INR 100000", "audience": "customer"},
                {"label": "Women's mulberry silk edit", "prompt": "Show me Women's silk dresses and blouses", "audience": "customer"},
                {"label": "Men's linen & cashmere", "prompt": "Show me Men's linen shirts and cashmere knitwear", "audience": "customer"},
                {"label": "Authenticity, GST & returns", "prompt": "What are the return policy rules and GST slabs?", "audience": "customer"},
                {"label": "Executive GMV telemetry", "prompt": "Show GMV and order analytics report", "audience": "staff"},
            ],
        }
        if ui_cfg is not None:
            ui_cfg.config_value = ui_payload
        else:
            session.add(BusinessConfig(config_key="storefront_ui", config_value=ui_payload, updated_by="seed_atelier"))

        # 7. Insert PRD-006 .. PRD-100 idempotently
        existing_pids = set(session.scalars(select(Product.product_id)).all())
        inserted = 0

        for spec in CURATED_95_SPECS:
            (
                num,
                dept,
                cat_id,
                name,
                color_name,
                color_code,
                hsn,
                materials_list,
                base_price,
                price_step,
                per_size_qty,
                origin,
                archetype,
                accent_tag,
                desc,
                fit,
                care,
                final_sale,
            ) = spec

            pid = f"PRD-{num:03d}"
            if pid in existing_pids:
                continue

            sku = f"{pid}-{color_code}"
            if dept == "KIDS":
                v_prices = _kids_prices(base_price, step=price_step)
            elif dept == "WOMEN":
                sizes_tuple = ("XS", "S", "M", "L") if base_price >= 7000 else ("XS", "S", "M", "L", "XL")
                v_prices = _adult_prices(base_price, sizes=sizes_tuple, step=price_step)
            else:
                v_prices = _adult_prices(base_price, sizes=("S", "M", "L", "XL"), step=price_step)

            size_map = {size: per_size_qty for size in v_prices}

            img_rel_key = f"products/{pid}/product.jpg"
            img_dest = object_store.root / img_rel_key
            if not img_dest.exists():
                src_img = archetype_files.get(archetype)
                if src_img and src_img.exists():
                    img_dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src_img, img_dest)
            image_url = f"/media/{img_rel_key}"

            resolved_cat_id = CATEGORY_CODE_MAP.get(cat_id, cat_id)
            resolved_color_name = COLOR_NAME_MAP.get(color_name, color_name)

            prod = Product(
                product_id=pid,
                sku=sku,
                name=name,
                description=desc,
                category_id=resolved_cat_id,
                department=dept,
                mrp_inr=min(v_prices.values()),
                hsn_code=hsn,
                color_id=color_ids[resolved_color_name],
                sizes_available=list(v_prices.keys()),
                fit_guide=fit,
                fabric_and_care=care,
                country_of_origin=origin,
                final_sale=final_sale,
                security_tag_required=True,
            )
            session.add(prod)
            session.flush()
            set_variant_prices(session, prod, v_prices)

            for mat_name, pct in materials_list:
                resolved_mat_name = MATERIAL_NAME_MAP.get(mat_name, mat_name)
                session.add(
                    ProductMaterial(
                        product_id=pid,
                        material_id=material_ids[resolved_mat_name],
                        percentage=pct,
                    )
                )

            session.add(
                ProductImage(
                    product_id=pid,
                    url=image_url,
                    alt_text=accent_tag,
                    display_order=1,
                )
            )
            # Opening stock per size, through the ledger like every other stock change.
            seed_ref = Ref("admin", pid, "seed", "atelier_collection_opening_stock")
            for variant in prod.variants:
                open_balance(
                    session, variant, size_map.get(variant.size, 0), seed_ref,
                    low_stock_threshold=1 if base_price >= 80000 else 2,
                )

            # Seed an authentic client review on key flagship & archive pieces
            if num % 3 == 0 or base_price >= 100000:
                reviewer = "CUS-001" if dept in ("MEN", "KIDS") else "CUS-002"
                session.add(
                    ProductReview(
                        product_id=pid,
                        customer_id=reviewer,
                        rating=5,
                        fit_feedback="true_to_size",
                        comment=(
                            f"Impeccable {origin} craftsmanship—the {accent_tag.lower()} hand-feel and finishing "
                            "are worthy of a true heritage fashion house."
                        ),
                    )
                )

            inserted += 1

        session.flush()

        # 8. Curated Complete-the-Look pairings for high-value pieces
        curated_pairings = [
            ("PRD-041", "PRD-037", "private_archive_pairing"),
            ("PRD-037", "PRD-021", "complete_the_look"),
            ("PRD-039", "PRD-100", "family_ceremonial_edit"),
            ("PRD-080", "PRD-078", "haute_archive_pairing"),
            ("PRD-081", "PRD-095", "family_bridal_edit"),
            ("PRD-058", "PRD-059", "complete_the_look"),
            ("PRD-018", "PRD-020", "complete_the_look"),
        ]
        existing_recs = {
            (r.source_product_id, r.recommended_product_id)
            for r in session.scalars(select(Recommendation)).all()
        }
        for src_id, dst_id, rel in curated_pairings:
            if (src_id, dst_id) not in existing_recs:
                session.add(
                    Recommendation(
                        source_product_id=src_id,
                        recommended_product_id=dst_id,
                        relation_type=rel,
                        score=Decimal("0.9700"),
                    )
                )

        session.commit()
        invalidate_config_cache()
        total_count = int(session.scalar(select(func.count(Product.product_id))) or 0)
        return {"status": "ok", "inserted": inserted, "total_products": total_count}


if __name__ == "__main__":
    summary = seed_atelier_collection()
    print(f"Noir Atelier Curated Archive synced: {summary}")
