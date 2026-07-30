"""
utils/qualifier.py — Score de qualification prospect /10 pour le CRM.

Filtrage STRICT : seuls les établissements aptes à recruter des étudiants
en jobs (temps partiel, extra, saisonnier) sont gardés.
"""

import re
from typing import Dict, List, Tuple

# ─── EXCLUSIONS — tout prospect contenant ces mots = score 0, éliminé ────────

_EXCLUDED_KEYWORDS = [
    # Médical / Santé / Hôpitaux
    "médecin", "médical", "dentiste", "pharmacie", "hôpital", "hospitalier",
    "clinique", "infirmier", "kinésithérapeute", "kiné", "ostéopathe",
    "opticien", "orthodontiste", "dermatologue", "cardiologue", "pédiatre",
    "radiologue", "vétérinaire", "laboratoire d'analyses", "orthophoniste",
    "psychologue", "psychiatre", "sage-femme", "chirurgien",
    "chu ", "chru", "epsm", "ehpad", "maison de retraite", "résidence senior",
    "aide-soignant", "aide soignant", "soins infirmiers",
    # Juridique
    "avocat", "notaire", "huissier", "juridique", "cabinet d'avocats",
    "greffier", "tribunal", "commissaire de justice",
    # Administration / Public / Collectivités
    "administration", "préfecture", "mairie", "conseil départemental",
    "conseil régional", "ministère", "trésor public", "impôts",
    "département de ", "département d'", "ville de ", "ville d'",
    "communauté de communes",
    "communauté d'agglomération", "métropole et ccas", "ccas",
    "fonction publique", "territorial", "sncf", "ratp",
    "france travail", "pôle emploi", "pole emploi",
    # Éducation / Universités / Écoles (ils ne recrutent pas des étudiants en job)
    "université", "universite", "école normale", "ecole normale",
    "collège", "college", "lycée", "lycee", "rectorat", "académie",
    "éducation nationale", "education nationale",
    # Religion / Associations cultuelles
    "mosquée", "église", "synagogue", "temple", "paroisse", "diocèse",
    "association cultuelle", "association musulmane", "association catholique",
    "imam", "pasteur", "rabbin", "culte",
    # Associations / Bénévolat / ONG
    "association loi 1901", "ong", "fondation caritative",
    "bénévolat", "bénévole", "benevolat", "benevole",
    "association monsieur", "croix-rouge", "secours populaire",
    "restos du coeur", "emmaüs", "médecins sans frontières",
    # Architecture / BTP spécialisé
    "architecte", "architecture", "cabinet d'architecture", "géomètre",
    "bureau d'études", "bureau d'étude", "ingénierie",
    # Artisans spécialisés (pas de jobs étudiants)
    "plombier", "électricien", "serrurier", "chauffagiste", "couvreur",
    "charpentier", "menuisier", "maçon", "peintre en bâtiment",
    "carreleur", "vitrier", "ramoneur", "terrassier",
    # Finance / Conseil spécialisé
    "expert-comptable", "expert comptable", "commissaire aux comptes",
    "cabinet comptable", "audit", "consulting",
    # Funéraire
    "pompes funèbres", "funéraire", "crématorium",
    # Auto-école / Permis
    "auto-école", "auto école",
    # Immobilier
    "agence immobilière", "immobilier", "syndic de copropriété",
    # Assurance
    "assurance", "mutuelle", "courtier en assurance",
    # Banque
    "banque", "crédit", "prêt immobilier",
    # Intérim / RH
    "agence d'intérim", "agence interim", "cabinet de recrutement",
    "ressources humaines",
    # Stages / Alternances
    "stage", "alternance", "alternant", "stagiaire", "apprentissage",
    "contrat pro", "contrat d'apprentissage",
    # Social / Médico-social (pas des employeurs de jobs étudiants)
    "éducateur spécialisé", "educateur specialise",
    "aide sociale", "action sociale", "solidarité",
    "handicap", "insertion",
    # Énergie / Utilities
    "edf", "engie", "veolia", "suez",
]

# ─── Chaînes et franchises connues (score bonus) ─────────────────────────────

_CHAINS = {
    "mcdonald", "burger king", "kfc", "quick", "subway", "domino",
    "pizza hut", "five guys", "starbucks", "paul", "brioche dorée",
    "class'croute", "pomme de pain", "flunch", "buffalo grill",
    "hippopotamus", "courtepaille", "léon", "del arte",
    "bistro régent", "la pataterie", "pitaya", "pokawa", "big fernand",
    "bagelstein", "o'tacos", "krispy kreme",
    "carrefour", "auchan", "leclerc", "intermarché", "casino", "monoprix",
    "franprix", "lidl", "aldi", "picard", "naturalia", "biocoop",
    "sephora", "zara", "h&m", "uniqlo", "primark", "fnac", "darty",
    "boulanger", "décathlon", "go sport", "intersport",
    "novotel", "ibis", "mercure", "accor", "marriott", "hilton",
    "holiday inn", "kyriad", "best western", "campanile",
    "mcdo", "mcd", "mcdonald's",
    "nike", "adidas", "levi's", "celio", "jules", "kiabi",
    "la halle", "gémo", "action", "gifi", "centrakor", "cultura",
    "leroy merlin", "castorama", "ikea", "conforama", "but",
    "nespresso", "kusmi tea", "mariage frères",
    "flixbus", "uber", "deliveroo", "uber eats", "just eat",
    "brico dépôt", "brico depot", "brico cash", "mr bricolage",
    "pandora", "normal",
}

# ─── Mots-clés positifs (jobs étudiants) ─────────────────────────────────────
# Cherchés UNIQUEMENT dans le nom + secteur + notes (PAS dans type_offre)

_STUDENT_KEYWORDS = [
    "extra", "extras", "job flexible",
    "temps partiel", "mi-temps", "week-end", "weekend", "saisonnier",
    "saison", "vacances", "horaires flexibles", "horaires aménageables",
    "sans expérience", "débutant accepté", "premier emploi",
    "complément de revenu", "petit boulot",
]

# ─── Secteurs cibles (OK pour jobs étudiants) ────────────────────────────────

_TARGET_SECTORS = [
    "restaurant", "brasserie", "fast-food", "restauration rapide",
    "restauration", "café", "traiteur", "hôtel", "hôtellerie",
    "supermarché", "hypermarché", "grande distribution",
    "magasin", "boutique", "vendeur", "vendeuse",
    "boulangerie", "pâtisserie", "glacier", "snack", "sandwicherie",
    "livraison", "entrepôt", "préparateur",
    "nettoyage", "propreté",
    "hôtesse", "événementiel",
    "garde d'enfants", "baby-sitting", "babysitter", "nounou",
    "cours particuliers", "soutien scolaire",
    "caissier", "caissière", "mise en rayon",
    "serveur", "serveuse", "commis", "plongeur", "barman", "barista",
    "livreur", "coursier",
    "manutentionnaire", "magasinier", "picking",
    "réceptionniste", "receptionniste",
]


def compute_score(prospect: Dict) -> Tuple[int, List[str]]:
    """
    Calcule le score de qualification /10 pour un prospect.
    Retourne (score, reasons). Score 0 = exclu automatiquement.
    """
    score = 5
    reasons = []

    name = (prospect.get("Entreprise", "") or "").lower()
    sector = (prospect.get("Secteur", "") or "").lower()
    link = (prospect.get("Lien", "") or "").lower()
    phone = (prospect.get("Téléphone", "") or prospect.get("Contact", "") or "").strip()
    source = (prospect.get("Source", "") or "").lower()
    notes = (prospect.get("Notes", "") or prospect.get("Remarque", "") or "").lower()
    type_offre = (prospect.get("Type offre visée", "") or "").lower()

    # Texte pour exclusions (inclut tout)
    text = f"{name} {sector} {notes} {type_offre}"
    # Texte pour scoring positif (SANS type_offre pour éviter le biais "étudiant")
    content_text = f"{name} {sector} {notes}"

    # ══════════════════════════════════════════════════
    # EXCLUSION AUTOMATIQUE — score = 0, prospect jeté
    # ══════════════════════════════════════════════════
    for kw in _EXCLUDED_KEYWORDS:
        if kw in text:
            return 0, [f"Exclu ({kw})"]

    if "stage" in type_offre or "alternance" in type_offre:
        return 0, ["Exclu (stage/alternance)"]

    # ══════════════════════════════════════════════════
    # SCORING POSITIF
    # ══════════════════════════════════════════════════

    # Chaîne / franchise → +1
    for chain in _CHAINS:
        if chain in name:
            score += 1
            reasons.append("Chaîne/franchise")
            break

    # Secteur cible → +1
    for kw in _TARGET_SECTORS:
        if kw in content_text:
            score += 1
            reasons.append(f"Secteur cible ({kw})")
            break

    # Mots-clés étudiants dans le CONTENU RÉEL (pas type_offre) → +1
    found = [kw for kw in _STUDENT_KEYWORDS if kw in content_text]
    if found:
        score += 1
        reasons.append(f"Job étudiant ({', '.join(found[:2])})")

    # Téléphone direct → +2 (signal fort : on peut appeler directement)
    digits = re.sub(r"\D", "", phone)
    if len(digits) >= 10:
        score += 2
        reasons.append("Téléphone direct")

    # Lien valide → +1
    if link and link.startswith("http"):
        score += 1
        reasons.append("Fiche en ligne")

    # Source avec offre active (LinkedIn/FT) → +1
    is_active_source = (
        "linkedin" in link or "linkedin" in source
        or "francetravail" in notes or "france travail" in notes
        or "francetravail" in source
    )
    if is_active_source:
        score += 1
        reasons.append("Source active")

    # ══════════════════════════════════════════════════
    # PÉNALITÉS
    # ══════════════════════════════════════════════════

    # Pas de téléphone → -2 (pénalité forte : sans tel, prospect peu utilisable)
    if len(digits) < 10:
        score -= 2
        reasons.append("Pas de téléphone")

    # Pas de lien → -1
    if not link:
        score -= 1
        reasons.append("Pas de lien")

    score = max(0, min(10, score))
    if not reasons:
        reasons.append("Score de base")

    return score, reasons


def format_score_reasons(reasons: List[str]) -> str:
    """Formate les raisons pour la colonne Remarque."""
    return " | ".join(reasons)


def qualify_prospects(prospects: List[Dict], min_score: int = 5) -> List[Dict]:
    """
    Score, filtre et trie les prospects.
    - Exclut les secteurs incompatibles (score 0)
    - Exclut score < min_score
    - Trie par score décroissant
    """
    scored = []
    for p in prospects:
        score, reasons = compute_score(p)
        p["SCORE"] = score
        p["_score_reasons"] = format_score_reasons(reasons)
        if score >= min_score:
            scored.append(p)

    scored.sort(key=lambda p: p.get("SCORE", 0), reverse=True)
    return scored
