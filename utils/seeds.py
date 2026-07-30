"""
utils/seeds.py — Données d'amorçage (seed) pour les offres de jobs étudiants.

Fournit des offres réalistes en fallback quand les scrapers ne ramènent pas
assez de résultats. Toutes les offres ont "Source": "seed" pour les distinguer
des données scrappées.
"""

import random
from typing import List, Dict


# ── Données de référence ──────────────────────────────────────────────────────

_COMPANIES_BY_SECTOR = {
    "Cours particuliers": [
        ("Acadomia", "acadomia.fr"),
        ("Superprof", "superprof.fr"),
        ("Complétude", "completude.com"),
        ("Ipésup", "ipesup.fr"),
        ("Les Sherpas", "lessherpas.fr"),
        ("Pythagore", "pythagore.fr"),
    ],
    "Baby-sitting": [
        ("Yoopies", "yoopies.fr"),
        ("Babychou Services", "babychou.com"),
        ("Top Famille", "topfamille.fr"),
        ("Kangourou Kids", "kangourou-kids.fr"),
        ("Kiddie", "kiddie.fr"),
    ],
    "Restauration": [
        ("McDonald's", "mcdonalds.fr"),
        ("Burger King", "burgerking.fr"),
        ("KFC", "kfc.fr"),
        ("Pizza Hut", "pizzahut.fr"),
        ("Brioche Dorée", "briochedoree.fr"),
        ("Flunch", "flunch.fr"),
        ("Hippopotamus", "hippopotamus.fr"),
        ("Paul", "paul.fr"),
        ("Subway", "subway.com"),
        ("Domino's Pizza", "dominos.fr"),
    ],
    "Vente & Commerce": [
        ("Carrefour", "carrefour.fr"),
        ("Leclerc", "e.leclerc"),
        ("Fnac", "fnac.com"),
        ("H&M", "hm.com"),
        ("Zara", "zara.com"),
        ("Monoprix", "monoprix.fr"),
        ("Intermarché", "intermarche.com"),
        ("Decathlon", "decathlon.fr"),
        ("Cultura", "cultura.com"),
        ("Boulanger", "boulanger.com"),
    ],
    "Livraison": [
        ("Uber Eats", "ubereats.com"),
        ("Deliveroo", "deliveroo.fr"),
        ("Just Eat", "just-eat.fr"),
        ("Stuart", "stuart.com"),
        ("Chronopost", "chronopost.fr"),
        ("Colis Privé", "colisprive.com"),
    ],
    "Logistique": [
        ("Amazon Logistique", "amazon.fr"),
        ("XPO Logistics", "xpo.com"),
        ("ID Logistics", "id-logistics.com"),
        ("Kuehne+Nagel", "kuehne-nagel.com"),
        ("Geodis", "geodis.com"),
        ("FM Logistic", "fmlogistic.com"),
    ],
    "Accueil & Événementiel": [
        ("GL Events", "gl-events.com"),
        ("Sodexo Live", "sodexolive.com"),
        ("Viparis", "viparis.com"),
        ("Reed Expositions", "reedexpo.fr"),
        ("Publicis Events", "publicis.com"),
        ("Informa Markets", "informamarkets.fr"),
    ],
    "Ménage & Entretien": [
        ("O2", "o2.fr"),
        ("Shiva", "shiva.fr"),
        ("Ménage.net", "menage.net"),
        ("Propreté Service", "proprete-service.fr"),
        ("Générale de Propreté", "ogf.fr"),
        ("Atalian", "atalian.fr"),
    ],
    "Administratif": [
        ("Adecco", "adecco.fr"),
        ("Manpower", "manpower.fr"),
        ("Randstad", "randstad.fr"),
        ("Page Personnel", "pagepersonnel.fr"),
        ("Michael Page", "michaelpage.fr"),
        ("Hays", "hays.fr"),
    ],
    "Freelance & En ligne": [
        ("Malt", "malt.fr"),
        ("Fiverr", "fiverr.com"),
        ("Upwork", "upwork.com"),
        ("ComeUp", "comeup.com"),
        ("Textbroker", "textbroker.fr"),
        ("Rédacteur.com", "redacteur.com"),
    ],
    "Télétravail": [
        ("Teleperformance", "teleperformance.com"),
        ("Concentrix", "concentrix.com"),
        ("Webhelp", "webhelp.com"),
        ("Intelcia", "intelcia.com"),
        ("iAdvize", "iadvize.com"),
    ],
    "Saisonnier": [
        ("Club Med", "clubmed.fr"),
        ("Pierre & Vacances", "pierreetvacances.com"),
        ("Sunparks", "sunparks.fr"),
        ("Domaines Skiables de France", "domaines-skiables.fr"),
        ("Huttopia", "huttopia.com"),
        ("Campéole", "campeole.fr"),
    ],
    "Autres jobs étudiants": [
        ("Jobétudiant", "jobetudiants.com"),
        ("StudentJob", "studentjob.fr"),
        ("Jobijoba", "jobijoba.com"),
        ("Wizbii", "wizbii.com"),
        ("Indeed", "indeed.fr"),
        ("Pôle Emploi", "pole-emploi.fr"),
    ],
}

_CITIES = [
    "Paris", "Lyon", "Marseille", "Toulouse", "Bordeaux", "Nantes", "Lille",
    "Strasbourg", "Montpellier", "Rennes", "Grenoble", "Rouen", "Toulon",
    "Dijon", "Angers", "Nîmes", "Clermont-Ferrand", "Aix-en-Provence",
    "Saint-Étienne", "Tours", "Metz", "Besançon", "Caen", "Orléans",
    "Reims", "Amiens", "Nice", "Brest", "Limoges", "Nancy",
]

_PHONE_PREFIXES = ["01", "02", "03", "04", "05", "09"]

_PARTNERSHIP_TYPES = ["Job étudiant", "Stage / Alternance"]
_CANAUX = ["Appel", "mail"]


# ── Fonctions utilitaires internes ────────────────────────────────────────────

def _make_phone(rng: random.Random) -> str:
    """Génère un numéro de téléphone français réaliste."""
    prefix = rng.choice(_PHONE_PREFIXES)
    parts = [prefix] + [f"{rng.randint(0, 99):02d}" for _ in range(4)]
    return " ".join(parts)


# ── API publique ──────────────────────────────────────────────────────────────

def generate_seed_offers(n: int = 50) -> List[Dict]:
    """
    Génère n offres d'amorçage réalistes pour les jobs étudiants en France.

    Déterministe : utilise une graine fixe pour garantir la même sortie à chaque
    appel avec le même n.

    Returns:
        Liste de dicts avec les clés du schéma CSV du projet.
    """
    rng = random.Random(42)
    sectors = list(_COMPANIES_BY_SECTOR.keys())
    offers: List[Dict] = []

    for i in range(n):
        sector = sectors[i % len(sectors)]
        company_name, company_domain = rng.choice(_COMPANIES_BY_SECTOR[sector])
        city = rng.choice(_CITIES)
        canal = rng.choice(_CANAUX)
        partnership = rng.choice(_PARTNERSHIP_TYPES)

        offer = {
            "Entreprise": company_name,
            "Lien": f"https://www.{company_domain}#seed",
            "Contact": _make_phone(rng),
            "Localisation": city,
            "Canal de contact": canal,
            "Type de partenariat": partnership,
            "Secteur": sector,
            "Source": "seed",
            "Statut": "Nouveau",
        }
        offers.append(offer)

    return offers


def needs_seeds(current_count: int, threshold: int = 10) -> bool:
    """Retourne True si le nombre d'offres courantes est inférieur au seuil."""
    return current_count < threshold
