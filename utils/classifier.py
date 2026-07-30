"""
utils/classifier.py — Règles métier pour le canal recommandé et le type d'offre visée.

Logique :
- Restaurants / commerces / boulangeries / supermarchés → Canal: Appel, Type: Job étudiant
- Grandes enseignes (mots-clés connus) → Canal: Email, Type: Job étudiant
- PME / startups / consulting / tech → Canal: Email, Type: Stage / Alternance
- Cabinets RH / agences d'intérim → Canal: Email, Type: Tous
"""

from typing import List, Tuple

# Types Google Places non-informatifs à ignorer
GENERIC_TYPES = {
    "point_of_interest",
    "establishment",
    "food",
    "store",
    "premise",
    "geocode",
    "political",
}

# Labels lisibles pour les types Google Places
SECTEUR_LABELS = {
    "restaurant": "Restaurant",
    "bakery": "Boulangerie",
    "cafe": "Café",
    "supermarket": "Supermarché",
    "grocery_or_supermarket": "Supermarché",
    "meal_delivery": "Livraison repas",
    "meal_takeaway": "Restauration rapide",
    "bar": "Bar",
    "night_club": "Club / Bar",
    "accounting": "Cabinet comptable",
    "real_estate_agency": "Agence immobilière",
    "insurance_agency": "Assurance",
    "employment_agency": "Agence RH / Recrutement",
    "finance": "Finance",
    "bank": "Banque",
    "travel_agency": "Agence de voyage",
    "clothing_store": "Commerce vêtements",
    "shoe_store": "Commerce chaussures",
    "beauty_salon": "Salon de beauté",
    "hair_care": "Coiffure",
    "gym": "Salle de sport",
    "spa": "Spa / Bien-être",
    "pharmacy": "Pharmacie",
    "doctor": "Cabinet médical",
    "dentist": "Cabinet dentaire",
    "lawyer": "Cabinet juridique",
    "car_dealer": "Concession auto",
    "car_repair": "Garage",
    "electronics_store": "Commerce électronique",
    "furniture_store": "Meuble",
    "hardware_store": "Bricolage",
    "florist": "Fleuriste",
    "book_store": "Librairie",
    "jewelry_store": "Bijouterie",
    "pet_store": "Animalerie",
    "convenience_store": "Épicerie",
}

# Règles : (liste de mots-clés à chercher dans secteur+nom, canal, type_offre)
CLASSIFICATION_RULES: List[Tuple[List[str], str, str]] = [
    # --- Grandes enseignes → Email, Job étudiant ---
    (
        [
            "mcdonald", "burger king", "kfc", "subway", "quick",
            "carrefour", "leclerc", "auchan", "monoprix", "franprix",
            "picard", "lidl", "aldi", "intermarché", "casino",
            "starbucks", "paul", "brioche dorée", "flunch",
            "zara", "h&m", "uniqlo", "primark", "sephora", "fnac",
            "decathlon", "ikea", "leroy merlin", "brico dépôt",
        ],
        "Email",
        "Job étudiant",
    ),
    # --- Restauration / commerces de proximité → Appel, Job étudiant ---
    (
        [
            "restaurant", "bakery", "boulangerie", "pâtisserie",
            "cafe", "café", "bar", "brasserie", "bistro", "pizzeria",
            "supermarket", "supermarché", "épicerie", "convenience",
            "traiteur", "sandwicherie", "kebab", "sushi",
            "meal_delivery", "meal_takeaway", "restauration",
            "commerce", "boutique", "fleuriste", "boucherie",
            "fromagerie", "charcuterie", "primeur", "pharmacie",
        ],
        "Appel",
        "Job étudiant",
    ),
    # --- Cabinets / agences RH → Email, Tous ---
    (
        [
            "employment_agency", "recrutement", "ressources humaines",
            "cabinet rh", "interim", "intérim", "manpower", "adecco",
            "randstad", "hays", "robert half", "michael page",
            "people & baby", "agence emploi", "pôle emploi",
        ],
        "Email",
        "Tous",
    ),
    # --- PME / startups / consulting → Email, Stage / Alternance ---
    (
        [
            "consulting", "conseil", "agence", "startup", "pme",
            "accounting", "finance", "insurance", "technology",
            "software", "informatique", "digital", "marketing",
            "communication", "immobilier", "real_estate", "bureau",
            "cabinet", "architecte", "ingénierie", "engineering",
            "formation", "audit", "expertise", "logistique",
        ],
        "Email",
        "Stage / Alternance",
    ),
]

DEFAULT_CANAL = "Email"
DEFAULT_TYPE_OFFRE = "Stage / Alternance"


def classify_prospect(secteur: str, entreprise: str) -> Tuple[str, str]:
    """
    Détermine le canal recommandé et le type d'offre visée.

    Args:
        secteur: secteur d'activité de l'entreprise
        entreprise: nom de l'entreprise

    Returns:
        (canal, type_offre) sous forme de chaînes
    """
    combined = (secteur + " " + entreprise).lower()

    for keywords, canal, type_offre in CLASSIFICATION_RULES:
        for kw in keywords:
            if kw in combined:
                return canal, type_offre

    return DEFAULT_CANAL, DEFAULT_TYPE_OFFRE


def infer_secteur_from_types(api_types: List[str]) -> str:
    """
    Déduit un label de secteur lisible depuis la liste de types Google Places.

    Ignore les types génériques (point_of_interest, establishment...) et retourne
    le premier type informatif trouvé, traduit en français.
    """
    for t in api_types:
        if t not in GENERIC_TYPES:
            return SECTEUR_LABELS.get(t, t.replace("_", " ").capitalize())
    return "Autre"
