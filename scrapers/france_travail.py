"""
scrapers/france_travail.py — Scraper via l'API officielle France Travail (ex-Pôle Emploi).

API : https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search
- Gratuite avec inscription (client_id + client_secret)
- Données officielles : offres d'emploi actives publiées par les entreprises
- AVANTAGE CLÉ : les entreprises ont un BESOIN RÉEL et ACTIF de recrutement
- Retourne : nom entreprise, ville, téléphone, email, site web, description, type contrat

Inscription gratuite : https://francetravail.io
→ Créer une application → Copier client_id et client_secret dans le fichier .env

Variables .env requises :
    FT_CLIENT_ID=votre_client_id
    FT_CLIENT_SECRET=votre_client_secret
"""

import time
import re
from typing import Dict, List, Optional, Tuple

import requests

TOKEN_URL = (
    "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
    "?realm=/partenaire"
)
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
SCOPE = "api_offresdemploiv2 o2dsoffre"

# Mapping ville → code département (pour le paramètre lieuTravail)
# Couvre TOUTES les villes des 13 régions de l'app
_CITY_TO_DEPT: List[Tuple[str, List[str]]] = [
    # ── Île-de-France ──
    ("75", ["paris"]),
    ("92", ["boulogne-billancourt", "boulogne", "nanterre", "courbevoie", "issy",
            "levallois", "neuilly", "clichy", "rueil", "colombes", "asnières",
            "antony", "montrouge", "sceaux", "clamart", "gennevilliers",
            "bagneux", "malakoff", "meudon", "sèvres", "suresnes"]),
    ("93", ["saint-denis", "montreuil", "aubervilliers", "noisy-le-grand", "pantin",
            "bobigny", "bondy", "aulnay", "drancy", "bagnolet", "sevran"]),
    ("94", ["créteil", "vitry", "champigny", "saint-maur", "ivry", "vincennes",
            "maisons-alfort", "villejuif", "orly", "fontenay-sous-bois"]),
    ("91", ["évry", "corbeil", "massy", "palaiseau"]),
    ("95", ["cergy", "argenteuil", "sarcelles", "pontoise"]),
    ("78", ["versailles", "saint-germain-en-laye", "poissy", "sartrouville"]),
    ("77", ["meaux", "melun", "chelles", "marne-la-vallée", "fontainebleau"]),
    # ── Auvergne-Rhône-Alpes ──
    ("69", ["lyon"]),
    ("38", ["grenoble"]),
    ("42", ["saint-étienne", "saint-etienne"]),
    ("63", ["clermont-ferrand", "clermont"]),
    ("74", ["annecy"]),
    # ── Bourgogne-Franche-Comté ──
    ("21", ["dijon"]),
    ("25", ["besançon", "besancon"]),
    ("71", ["chalon-sur-saône", "chalon"]),
    ("89", ["auxerre"]),
    # ── Bretagne ──
    ("35", ["rennes"]),
    ("29", ["brest", "quimper"]),
    ("35", ["saint-malo"]),
    # ── Centre-Val de Loire ──
    ("45", ["orléans", "orleans"]),
    ("37", ["tours"]),
    ("18", ["bourges"]),
    ("41", ["blois"]),
    # ── Corse ──
    ("2A", ["ajaccio"]),
    ("2B", ["bastia"]),
    # ── Grand Est ──
    ("67", ["strasbourg"]),
    ("51", ["reims"]),
    ("57", ["metz"]),
    ("54", ["nancy"]),
    # ── Hauts-de-France ──
    ("59", ["lille", "roubaix", "dunkerque"]),
    ("80", ["amiens"]),
    # ── Normandie ──
    ("76", ["rouen", "le havre"]),
    ("14", ["caen"]),
    # ── Nouvelle-Aquitaine ──
    ("33", ["bordeaux"]),
    ("87", ["limoges"]),
    ("86", ["poitiers"]),
    ("17", ["la rochelle"]),
    # ── Occitanie ──
    ("31", ["toulouse"]),
    ("34", ["montpellier"]),
    ("30", ["nîmes", "nimes"]),
    ("66", ["perpignan"]),
    # ── Pays de la Loire ──
    ("44", ["nantes", "saint-nazaire"]),
    ("49", ["angers"]),
    ("72", ["le mans"]),
    # ── Provence-Alpes-Côte d'Azur ──
    ("13", ["marseille"]),
    ("06", ["nice", "cannes"]),
    ("83", ["toulon"]),
]


def _dept_from_location(location: str) -> str:
    """Résout une ville ou un département en code département France Travail."""
    loc = location.lower().strip()
    # Détecter un code département explicite (01-95, 2A, 2B)
    m = re.search(r"\b(0[1-9]|[1-9]\d|2[ab])\b", loc, re.IGNORECASE)
    if m:
        return m.group(1).upper() if m.group(1)[0] == '2' and m.group(1)[1] in 'aAbB' else m.group(1)
    # Chercher par nom de ville dans le mapping
    for code, keywords in _CITY_TO_DEPT:
        if any(kw in loc for kw in keywords):
            return code
    # Fallback Paris si rien ne matche
    return "75"


class FranceTravailScraper:
    """
    Scrape les offres d'emploi de France Travail (ex-Pôle Emploi).
    Cible les entreprises qui recrutent ACTIVEMENT — la source la plus qualifiée.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        delay: float = 0.5,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.delay = delay
        self._token: Optional[str] = None
        self._token_expires: float = 0.0
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "CDE-ScraperBot/1.0",
        })

    # ── Auth OAuth2 ──────────────────────────────────────────────────────────

    def _get_token(self) -> str:
        """Obtient un token OAuth2 (mis en cache 20 min)."""
        if self._token and time.time() < self._token_expires - 60:
            return self._token
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": SCOPE,
        }
        resp = self.session.post(TOKEN_URL, data=data, timeout=15)
        resp.raise_for_status()
        j = resp.json()
        self._token = j["access_token"]
        self._token_expires = time.time() + j.get("expires_in", 1200)
        return self._token

    # ── Requête API ──────────────────────────────────────────────────────────

    def _search(
        self,
        keywords: str,
        dept: str,
        offset: int = 0,
        size: int = 50,
        type_contrat: str = "CDD,CDI,SAI",
    ) -> Optional[dict]:
        """Appelle l'API de recherche d'offres."""
        try:
            token = self._get_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }
            params = {
                "motsCles": keywords,
                "departement": dept,
                "typeContrat": type_contrat,
                "experienceExige": "D",       # Débutant accepté
                "range": f"{offset}-{offset + size - 1}",
            }
            resp = self.session.get(
                SEARCH_URL, params=params, headers=headers, timeout=20
            )
            if resp.status_code == 206:         # Partial content — résultats normaux
                return resp.json()
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            return None
        except Exception:
            return None

    # ── Parsing d'une offre → prospect ──────────────────────────────────────

    def _offer_to_prospect(self, offer: dict) -> Optional[Dict]:
        """Convertit une offre France Travail en dict prospect CDE."""
        entreprise = offer.get("entreprise") or {}
        lieu = offer.get("lieuTravail") or {}
        contact = offer.get("contact") or {}

        nom = entreprise.get("nom", "").strip().title()
        if not nom or nom.lower() in ("particulier", "confidentiel", "non communiqué"):
            return None

        ville = lieu.get("libelle", "").strip().title()
        # Nettoyer "75 - Paris" → "Paris"
        ville = re.sub(r"^\d+\s*[-–]\s*", "", ville).strip()

        phone = contact.get("telephone", "").strip()
        email = contact.get("email", "").strip()
        website = entreprise.get("url", "").strip()
        if website and not website.startswith("http"):
            website = "https://" + website

        # Type de contrat → type d'offre
        type_contrat = offer.get("typeContrat", "")
        type_offre = {
            "APP": "Stage / Alternance",
            "PRO": "Stage / Alternance",
            "CDD": "Job étudiant",
            "CDI": "Job étudiant",
            "SAI": "Job étudiant",
        }.get(type_contrat, "Job étudiant")

        intitule = offer.get("intitule", "").strip()
        desc = offer.get("description", "").strip()[:200]

        return {
            "Entreprise":       nom,
            "Secteur":          offer.get("secteurActiviteLibelle", ""),
            "Ville":            ville,
            "Adresse":          ville,
            "Téléphone":        phone,
            "Email":            email,
            "Lien":             website,
            "_detail_id":       "",
            "LinkedIn":         "",
            "Type offre visée": type_offre,
            "Canal recommandé": "Appel" if phone else ("mail" if email else "Appel"),
            "Assigné à":        "",
            "Statut":           "À contacter",
            "Date ajout":       "",
            "Notes":            f"Offre: {intitule} | Source: France Travail",
        }

    # ── Point d'entrée ───────────────────────────────────────────────────────

    def scrape(
        self,
        query: str,
        location: str = "Paris",
        max_pages: int = 3,
        fetch_phones: bool = False,
        progress_callback=None,
    ) -> List[Dict]:
        """
        Récupère les offres actives sur France Travail pour la requête donnée.

        Args:
            query:             terme de recherche (ex: "serveur", "vendeur", "caissier")
            location:          ville ou zone IDF
            max_pages:         nombre de pages (50 offres/page, 150 offres max par appel)
            fetch_phones:      ignoré (les phones viennent de l'API directement)
            progress_callback: fonction de log optionnelle

        Returns:
            Liste de dicts prospects (entreprises ayant publié une offre)
        """
        dept = _dept_from_location(location)
        all_prospects: List[Dict] = []
        seen_companies: set = set()

        for page in range(max_pages):
            offset = page * 50

            if progress_callback:
                progress_callback(
                    f"[France Travail] Page {page + 1}/{max_pages} — "
                    f"'{query}' @ {location} (dept {dept})"
                )

            data = self._search(query, dept, offset=offset)

            if not data:
                if progress_callback:
                    progress_callback(
                        f"[France Travail] Aucun résultat page {page + 1} — arrêt."
                    )
                break

            offers = data.get("resultats") or []
            if not offers:
                break

            new_count = 0
            for offer in offers:
                prospect = self._offer_to_prospect(offer)
                if not prospect:
                    continue
                # Dédup interne par nom d'entreprise (1 entrée par entreprise par session)
                key = prospect["Entreprise"].lower().strip()
                if key in seen_companies:
                    continue
                seen_companies.add(key)
                all_prospects.append(prospect)
                new_count += 1

            total_api = data.get("Content-Range", f"?/{len(offers)}")
            if progress_callback:
                progress_callback(
                    f"[France Travail] {new_count} nouvelles entreprises "
                    f"(total session : {len(all_prospects)})"
                )

            # Vérifier s'il reste des pages
            content_range = data.get("Content-Range", "")
            if content_range:
                try:
                    total = int(content_range.split("/")[1])
                    if offset + 50 >= total:
                        break
                except (IndexError, ValueError):
                    pass

            time.sleep(self.delay)

        return all_prospects
