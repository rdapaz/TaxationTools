"""
Expense categories for Australian household budgeting.

Consolidated to ~18 categories — enough granularity to be useful,
few enough for the local DistilBERT model to train on (~2500 transactions).

Categories are organised into groups for display purposes.
The CATEGORIES dict maps category_id -> display metadata.
The LEGACY_MAP maps old tax-tool categories to their new equivalents.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple


# ── Colour palette ──────────────────────────────────────────────────────────
CATEGORY_COLOURS = {
    # Home
    "housing":              "#4E79A7",
    "utilities":            "#59A14F",

    # Transport
    "fuel":                 "#F28E2B",
    "car":                  "#FF9DA7",
    "public_transport":     "#BAB0AC",

    # Living
    "groceries":            "#499894",
    "household":            "#E15759",
    "dining_out":           "#FF9D9A",

    # Health
    "health":               "#D37295",
    "fitness":              "#B6992D",

    # Family
    "children":             "#A0CBE8",

    # Lifestyle
    "entertainment":        "#D4A6C8",
    "clothing":             "#FFBE7D",
    "personal_care":        "#D7B5A6",

    # Financial
    "insurance":            "#76B7B2",
    "fees_charges":         "#9C755F",

    # Work (tax deductible)
    "work_deductible":      "#2196F3",

    # Catch-all
    "other":                "#9E9E9E",
    "uncategorised":        "#BDBDBD",
}


@dataclass
class CategoryInfo:
    """Metadata for a single expense category."""
    id: str
    display_name: str
    group: str
    colour: str
    tax_deductible: bool = False
    description: str = ""
    keywords: str = ""  # Helps AI classification


# ── Master category list ───────────────────────────────────────────────────
CATEGORIES: Dict[str, CategoryInfo] = {}

def _register(id: str, display_name: str, group: str, *,
              tax_deductible: bool = False, description: str = "",
              keywords: str = ""):
    CATEGORIES[id] = CategoryInfo(
        id=id,
        display_name=display_name,
        group=group,
        colour=CATEGORY_COLOURS.get(id, "#9E9E9E"),
        tax_deductible=tax_deductible,
        description=description,
        keywords=keywords,
    )

# ── Home (2) ────────────────────────────────────────────────────────────────
_register("housing",       "Housing",          "Home",
          description="Rent, mortgage, rates, strata, home repairs, Bunnings",
          keywords="rent mortgage strata council rates bunnings hardware tradesman plumber electrician")
_register("utilities",     "Utilities",        "Home",
          description="Electricity, gas, water, internet, mobile phone",
          keywords="agl origin energyaustralia synergy telstra optus vodafone nbn iinet")

# ── Transport (3) ──────────────────────────────────────────────────────────
_register("fuel",          "Fuel",             "Transport",
          description="Petrol, diesel, EV charging",
          keywords="bp caltex shell ampol 7-eleven petrol fuel ampcharge")
_register("car",           "Car",              "Transport",
          description="Rego, service, tyres, tolls, parking, car wash",
          keywords="linkt etag rego mechanic tyres parking ultratune kmart auto repco")
_register("public_transport", "Public Transport", "Transport",
          description="Train, bus, ferry, Opal, Myki, rideshare, taxis",
          keywords="opal myki transperth uber didi taxi lyft")

# ── Living (3) ─────────────────────────────────────────────────────────────
_register("groceries",     "Groceries",        "Living",
          description="Supermarkets, butcher, bakery, fruit & veg",
          keywords="woolworths coles aldi costco igaX harris farm spudshed")
_register("household",     "Household",        "Living",
          description="Cleaning, homewares, Kmart, Target, Big W",
          keywords="kmart target big-w ikea officeworks cleaning")
_register("dining_out",    "Dining Out",       "Living",
          description="Restaurants, cafes, takeaway, UberEats, Menulog",
          keywords="restaurant cafe coffee mcdonald uber eats menulog doordash dominos")

# ── Health (2) ─────────────────────────────────────────────────────────────
_register("health",        "Health",           "Health",
          description="GP, dentist, optometrist, pharmacy, hospital, Medicare gap",
          keywords="medical dental doctor pharmacy chemist optical specsavers priceline")
_register("fitness",       "Fitness",          "Health",
          description="Gym, sports, equipment, activewear",
          keywords="gym anytime fitness rebel sport decathlon")

# ── Family (1) ─────────────────────────────────────────────────────────────
_register("children",      "Children",         "Family",
          description="Childcare, school fees, uniforms, kids activities, tutoring",
          keywords="childcare school uniform swimming karate music lesson tutoring")

# ── Lifestyle (3) ──────────────────────────────────────────────────────────
_register("entertainment", "Entertainment",    "Lifestyle",
          description="Streaming, movies, gaming, concerts, hobbies, subscriptions, apps",
          keywords="netflix disney spotify steam playstation xbox cinema event ticketek")
_register("clothing",      "Clothing",         "Lifestyle",
          description="Clothes, shoes, accessories",
          keywords="cotton on uniqlo zara h&m nike adidas")
_register("personal_care", "Personal Care",    "Lifestyle",
          description="Hair, beauty, grooming, skincare",
          keywords="hairdresser barber beauty salon mecca sephora")

# ── Financial (2) ──────────────────────────────────────────────────────────
_register("insurance",     "Insurance",        "Financial",
          description="Home, car, health, life, pet insurance",
          keywords="bupa medibank nib hcf allianz nrma racq suncorp youi")
_register("fees_charges",  "Fees & Charges",   "Financial",
          description="Bank fees, interest charges, ATM fees, donations, gifts",
          keywords="bank fee interest charge atm donation gift")

# ── Work (1 — all tax-deductible items merged) ────────────────────────────
_register("work_deductible", "Work Deductible", "Work",
          tax_deductible=True,
          description="Software, training, books, professional memberships — tax deductible",
          keywords="udemy coursera oreilly manning pluralsight jetbrains github adobe acm ieee")

# ── Catch-all (2) ─────────────────────────────────────────────────────────
_register("other",         "Other",            "Other",
          description="Anything that doesn't fit the above")
_register("uncategorised", "Uncategorised",    "Other",
          description="Not yet categorised")


# ── Legacy mapping (old tax-tool categories → new) ────────────────────────
LEGACY_MAP = {
    "not work related":       None,   # needs AI re-categorisation
    "magazines and journals":  "work_deductible",
    "professional membership": "work_deductible",
    "software":               "work_deductible",
    "technical library":      "work_deductible",
    "training":               "work_deductible",
    "other":                  "other",
}


def get_groups() -> List[Tuple[str, List[CategoryInfo]]]:
    """Return categories grouped by group name, preserving insertion order."""
    groups: Dict[str, List[CategoryInfo]] = {}
    for cat in CATEGORIES.values():
        groups.setdefault(cat.group, []).append(cat)
    return list(groups.items())


def get_category_names() -> List[str]:
    """Return all category display names sorted alphabetically."""
    return sorted(c.display_name for c in CATEGORIES.values())


def get_category_ids() -> List[str]:
    """Return all category IDs."""
    return list(CATEGORIES.keys())


def colour_for(category_id: str) -> str:
    """Return hex colour string for a category."""
    cat = CATEGORIES.get(category_id)
    return cat.colour if cat else "#9E9E9E"


def get_classification_prompt() -> str:
    """Build the category list for AI classification prompts."""
    lines = []
    for cat in CATEGORIES.values():
        if cat.id == "uncategorised":
            continue
        line = f'- "{cat.id}": {cat.description}'
        lines.append(line)
    return "\n".join(lines)
