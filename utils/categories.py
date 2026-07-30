"""
categories.py — Taxonomie des catégories de jobs étudiants + auto-classification.
"""

# ─── Catégories de jobs étudiants ────────────────────────────────────────────
# Chaque catégorie a : label affiché, mots-clés de recherche, icône

STUDENT_JOB_CATEGORIES = {
    "Cours particuliers": {
        "queries": ["soutien scolaire", "cours particuliers", "professeur particulier", "tuteur"],
        "keywords": ["soutien", "cours", "tuteur", "professeur", "enseignement", "maths", "anglais", "francais", "physique", "aide aux devoirs"],
        "icon": "📚",
    },
    "Baby-sitting": {
        "queries": ["baby-sitting", "garde d'enfants", "nounou"],
        "keywords": ["baby", "sitting", "garde", "enfant", "nounou", "babysitter", "périscolaire", "nourrice"],
        "icon": "👶",
    },
    "Restauration": {
        "queries": ["serveur restaurant", "restauration", "fast-food", "cuisine"],
        "keywords": ["serveur", "serveuse", "restaurant", "restauration", "fast-food", "cuisine", "plonge", "commis", "brasserie", "pizzeria", "burger", "sushi", "traiteur", "bar", "café", "barista", "barman"],
        "icon": "🍽️",
    },
    "Vente & Commerce": {
        "queries": ["vendeur magasin", "vente commerce", "caissier", "grande distribution"],
        "keywords": ["vendeur", "vendeuse", "vente", "caissier", "caissière", "magasin", "boutique", "commerce", "rayon", "mise en rayon", "grande distribution", "supermarché", "hypermarché"],
        "icon": "🛒",
    },
    "Livraison": {
        "queries": ["livreur", "livraison", "coursier"],
        "keywords": ["livreur", "livraison", "coursier", "uber eats", "deliveroo", "just eat", "colis", "chauffeur"],
        "icon": "🚴",
    },
    "Logistique": {
        "queries": ["préparateur de commandes", "logistique manutention", "magasinier"],
        "keywords": ["logistique", "préparateur", "commandes", "manutention", "magasinier", "entrepôt", "picking", "cariste", "inventaire", "stock"],
        "icon": "📦",
    },
    "Accueil & Événementiel": {
        "queries": ["hôtesse accueil", "événementiel", "animation commerciale"],
        "keywords": ["accueil", "hôte", "hôtesse", "événement", "événementiel", "animation", "salon", "foire", "congrès", "réception", "standardiste"],
        "icon": "🎪",
    },
    "Ménage & Entretien": {
        "queries": ["ménage", "agent entretien", "nettoyage"],
        "keywords": ["ménage", "entretien", "nettoyage", "propreté", "femme de ménage", "homme de ménage", "agent", "hygiène"],
        "icon": "🧹",
    },
    "Administratif": {
        "queries": ["assistant administratif", "secrétaire", "saisie de données"],
        "keywords": ["administratif", "secrétaire", "assistant", "saisie", "données", "bureautique", "classement", "archivage", "accueil téléphonique"],
        "icon": "💼",
    },
    "Freelance & En ligne": {
        "queries": ["freelance étudiant", "rédacteur web", "community manager"],
        "keywords": ["freelance", "rédacteur", "web", "community", "manager", "graphiste", "traduction", "transcription", "en ligne", "digital", "réseaux sociaux", "content"],
        "icon": "💻",
    },
    "Télétravail": {
        "queries": ["télétravail étudiant", "travail à domicile", "remote job"],
        "keywords": ["télétravail", "remote", "domicile", "à distance", "home office"],
        "icon": "🏠",
    },
    "Saisonnier": {
        "queries": ["job saisonnier", "job été", "vendanges", "station ski"],
        "keywords": ["saisonnier", "saison", "été", "hiver", "vendanges", "récolte", "camping", "station", "plage", "tourisme", "moniteur"],
        "icon": "☀️",
    },
    "Autres jobs étudiants": {
        "queries": ["job étudiant", "emploi étudiant temps partiel"],
        "keywords": ["étudiant", "job", "petit boulot", "extras", "interim", "mission", "ponctuel"],
        "icon": "🎓",
    },
}

# Liste ordonnée des noms de catégories (pour l'UI)
CATEGORY_NAMES = list(STUDENT_JOB_CATEGORIES.keys())


def classify_offer(title: str, description: str = "", company: str = "") -> str:
    """Classifie une offre dans une catégorie de job étudiant.

    Retourne le nom de la catégorie la plus pertinente.
    """
    text = f"{title} {description} {company}".lower()

    best_cat = "Autres jobs étudiants"
    best_score = 0

    for cat_name, cat_info in STUDENT_JOB_CATEGORIES.items():
        if cat_name == "Autres jobs étudiants":
            continue
        score = sum(1 for kw in cat_info["keywords"] if kw in text)
        if score > best_score:
            best_score = score
            best_cat = cat_name

    return best_cat


def get_category_icon(category: str) -> str:
    """Retourne l'icône pour une catégorie donnée."""
    cat = STUDENT_JOB_CATEGORIES.get(category, {})
    return cat.get("icon", "🎓")


def get_search_queries(category: str) -> list:
    """Retourne les requêtes de recherche pour une catégorie."""
    cat = STUDENT_JOB_CATEGORIES.get(category, {})
    return cat.get("queries", [])
