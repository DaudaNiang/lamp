"""
utils/geo.py — Données géographiques partagées (régions, villes, départements).
"""

import re
from typing import Optional

# ─── 13 régions françaises + villes principales ──────────────────────────────

ALL_REGIONS = {
    "Île-de-France": [
        "Paris", "Boulogne-Billancourt", "Saint-Denis", "Argenteuil", "Montreuil",
    ],
    "Auvergne-Rhône-Alpes": [
        "Lyon", "Grenoble", "Saint-Étienne", "Clermont-Ferrand", "Annecy",
    ],
    "Bourgogne-Franche-Comté": [
        "Dijon", "Besançon", "Chalon-sur-Saône", "Auxerre",
    ],
    "Bretagne": [
        "Rennes", "Brest", "Quimper", "Saint-Malo",
    ],
    "Centre-Val de Loire": [
        "Orléans", "Tours", "Bourges", "Blois",
    ],
    "Corse": [
        "Ajaccio", "Bastia",
    ],
    "Grand Est": [
        "Strasbourg", "Reims", "Metz", "Nancy",
    ],
    "Hauts-de-France": [
        "Lille", "Amiens", "Roubaix", "Dunkerque",
    ],
    "Normandie": [
        "Rouen", "Caen", "Le Havre",
    ],
    "Nouvelle-Aquitaine": [
        "Bordeaux", "Limoges", "Poitiers", "La Rochelle",
    ],
    "Occitanie": [
        "Toulouse", "Montpellier", "Nîmes", "Perpignan",
    ],
    "Pays de la Loire": [
        "Nantes", "Angers", "Le Mans", "Saint-Nazaire",
    ],
    "Provence-Alpes-Côte d'Azur": [
        "Marseille", "Nice", "Toulon", "Cannes",
    ],
}

# ─── Département (code) → Région ─────────────────────────────────────────────

DEPT_TO_REGION = {
    # Auvergne-Rhône-Alpes
    "01": "Auvergne-Rhône-Alpes", "03": "Auvergne-Rhône-Alpes",
    "07": "Auvergne-Rhône-Alpes", "15": "Auvergne-Rhône-Alpes",
    "26": "Auvergne-Rhône-Alpes", "38": "Auvergne-Rhône-Alpes",
    "42": "Auvergne-Rhône-Alpes", "43": "Auvergne-Rhône-Alpes",
    "63": "Auvergne-Rhône-Alpes", "69": "Auvergne-Rhône-Alpes",
    "73": "Auvergne-Rhône-Alpes", "74": "Auvergne-Rhône-Alpes",
    # Bourgogne-Franche-Comté
    "21": "Bourgogne-Franche-Comté", "25": "Bourgogne-Franche-Comté",
    "39": "Bourgogne-Franche-Comté", "58": "Bourgogne-Franche-Comté",
    "70": "Bourgogne-Franche-Comté", "71": "Bourgogne-Franche-Comté",
    "89": "Bourgogne-Franche-Comté", "90": "Bourgogne-Franche-Comté",
    # Bretagne
    "22": "Bretagne", "29": "Bretagne", "35": "Bretagne", "56": "Bretagne",
    # Centre-Val de Loire
    "18": "Centre-Val de Loire", "28": "Centre-Val de Loire",
    "36": "Centre-Val de Loire", "37": "Centre-Val de Loire",
    "41": "Centre-Val de Loire", "45": "Centre-Val de Loire",
    # Corse
    "2A": "Corse", "2B": "Corse",
    # Grand Est
    "08": "Grand Est", "10": "Grand Est", "51": "Grand Est", "52": "Grand Est",
    "54": "Grand Est", "55": "Grand Est", "57": "Grand Est", "67": "Grand Est",
    "68": "Grand Est", "88": "Grand Est",
    # Hauts-de-France
    "02": "Hauts-de-France", "59": "Hauts-de-France", "60": "Hauts-de-France",
    "62": "Hauts-de-France", "80": "Hauts-de-France",
    # Île-de-France
    "75": "Île-de-France", "77": "Île-de-France", "78": "Île-de-France",
    "91": "Île-de-France", "92": "Île-de-France", "93": "Île-de-France",
    "94": "Île-de-France", "95": "Île-de-France",
    # Normandie
    "14": "Normandie", "27": "Normandie", "50": "Normandie",
    "61": "Normandie", "76": "Normandie",
    # Nouvelle-Aquitaine
    "16": "Nouvelle-Aquitaine", "17": "Nouvelle-Aquitaine",
    "19": "Nouvelle-Aquitaine", "23": "Nouvelle-Aquitaine",
    "24": "Nouvelle-Aquitaine", "33": "Nouvelle-Aquitaine",
    "40": "Nouvelle-Aquitaine", "47": "Nouvelle-Aquitaine",
    "64": "Nouvelle-Aquitaine", "79": "Nouvelle-Aquitaine",
    "86": "Nouvelle-Aquitaine", "87": "Nouvelle-Aquitaine",
    # Occitanie
    "09": "Occitanie", "11": "Occitanie", "12": "Occitanie", "30": "Occitanie",
    "31": "Occitanie", "32": "Occitanie", "34": "Occitanie", "46": "Occitanie",
    "48": "Occitanie", "65": "Occitanie", "66": "Occitanie", "81": "Occitanie",
    "82": "Occitanie",
    # Pays de la Loire
    "44": "Pays de la Loire", "49": "Pays de la Loire", "53": "Pays de la Loire",
    "72": "Pays de la Loire", "85": "Pays de la Loire",
    # Provence-Alpes-Côte d'Azur
    "04": "Provence-Alpes-Côte d'Azur", "05": "Provence-Alpes-Côte d'Azur",
    "06": "Provence-Alpes-Côte d'Azur", "13": "Provence-Alpes-Côte d'Azur",
    "83": "Provence-Alpes-Côte d'Azur", "84": "Provence-Alpes-Côte d'Azur",
}

_CP_RE = re.compile(r"\b(\d{5})\b")


def dept_from_address(adresse: str) -> str:
    """Extrait le code département (2 chiffres, ou 2A/2B) depuis une adresse contenant un CP."""
    if not adresse:
        return ""
    m = _CP_RE.search(adresse)
    if not m:
        return ""
    cp = m.group(1)
    if cp.startswith("20"):
        # Corse : 20000-20199 = 2A, 20200+ = 2B (approximation usuelle)
        return "2A" if int(cp[2:]) < 200 else "2B"
    return cp[:2]


def region_from_dept(dept_code: str) -> str:
    """Retourne le nom de la région depuis un code département."""
    return DEPT_TO_REGION.get(dept_code, "")


def region_from_address(adresse: str) -> str:
    """Raccourci : adresse → région (via le département détecté)."""
    return region_from_dept(dept_from_address(adresse))
