"""
utils/residence_taxonomy.py — Détection des gestionnaires connus et exclusion
des résidences publiques (CROUS, logement social) pour ne garder que le
privé lucratif, cible commerciale du Coin des Étudiants.
"""

from typing import Dict

# ─── Gestionnaires nationaux connus (résidences étudiantes privées) ─────────
# Mot-clé détecté dans le nom → nom d'affichage normalisé du gestionnaire

_KNOWN_CHAINS: Dict[str, str] = {
    "studéa": "Studéa (Nexity)",
    "studea": "Studéa (Nexity)",
    "uxco": "UXCO Student",
    "les belles années": "Les Belles Années",
    "cardinal campus": "Cardinal Campus",
    "fac-habitat": "Fac-Habitat",
    "fac habitat": "Fac-Habitat",
    "twenty campus": "Twenty Campus",
    "kley": "KLEY",
    "odalys campus": "Odalys Campus",
    "odalys": "Odalys Campus",
    "studélites": "Studélites",
    "studelites": "Studélites",
    "estudines": "Estudines",
    "suitétudes": "Suitétudes",
    "suitetudes": "Suitétudes",
    "arpej": "ARPEJ",
    "sergic": "Sergic Résidences Étudiantes",
    "youfirst campus": "YouFirst Campus",
    "youfirst": "YouFirst Campus",
    "nemea": "Nemea Appart'Étud",
    "espacil": "Espacil Habitat",
}

# Domaines officiels connus (référence pour l'onglet Gestionnaires)
KNOWN_CHAIN_DOMAINS: Dict[str, str] = {
    "Studéa (Nexity)": "studea.com",
    "UXCO Student": "uxco.com",
    "Les Belles Années": "lesbellesannees.com",
    "Cardinal Campus": "cardinal-campus.fr",
    "Fac-Habitat": "fac-habitat.com",
    "Twenty Campus": "twentycampus.com",
    "KLEY": "kley.fr",
    "Odalys Campus": "odalys-campus.com",
    "Studélites": "studelites.com",
    "Estudines": "estudines.fr",
    "Suitétudes": "suitetudes.com",
    "ARPEJ": "arpej.fr",
    "Sergic Résidences Étudiantes": "sergic.com",
    "YouFirst Campus": "youfirst-campus.fr",
    "Nemea Appart'Étud": "nemea.fr",
    "Espacil Habitat": "espacil.fr",
}


def classify_gestionnaire(name: str) -> str:
    """Retourne le nom du gestionnaire connu si détecté dans le nom, sinon ''."""
    lname = (name or "").lower()
    for kw, display in _KNOWN_CHAINS.items():
        if kw in lname:
            return display
    return ""


# ─── Exclusion : résidences publiques / CROUS / logement social ─────────────
# On veut UNIQUEMENT le privé lucratif — le CROUS n'est jamais un partenaire.

_PUBLIC_EXCLUDED_KEYWORDS = [
    "crous", "cnous",
    "logement social", "hlm", "opac", "office public",
    "cité universitaire du crous", "cité-u crous",
    "bailleur social", "office hlm",
]


def is_public_residence(name: str, adresse: str = "", notes: str = "") -> bool:
    """True si la résidence est publique (CROUS/social) → à exclure."""
    text = f"{name} {adresse} {notes}".lower()
    return any(kw in text for kw in _PUBLIC_EXCLUDED_KEYWORDS)


# ─── Filtre : le résultat doit ressembler à une résidence étudiante ─────────
# (évite de garder des agences immobilières, régies, etc. trouvées par erreur
# sur la même recherche Pages Jaunes)

_RESIDENCE_POSITIVE_KEYWORDS = [
    "résidence étudiante", "residence etudiante", "résidence étudiants",
    "résidence pour étudiants", "logement étudiant", "student residence",
    "campus", "appart'étud", "appart étud", "cité étudiante",
]


def looks_like_residence(name: str, notes: str = "") -> bool:
    """True si le nom/description correspond bien à une résidence étudiante."""
    text = f"{name} {notes}".lower()
    if any(kw in text for kw in _RESIDENCE_POSITIVE_KEYWORDS):
        return True
    # Les gestionnaires connus sont déjà un signal suffisant
    return bool(classify_gestionnaire(name))
