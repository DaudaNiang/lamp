"""
scrapers/linkedin_jobs.py — Scraper des offres d'emploi LinkedIn (accès public).

Stratégie :
- Accès public (sans compte) via linkedin.com/jobs/search
- 60 offres max par requête (limite LinkedIn pour les visiteurs non-connectés)
- Chaque résultat = une entreprise qui recrute ACTIVEMENT
- Le lien vers l'offre LinkedIn sert de preuve de besoin réel + lien utile pour la prise de contact

Avantage clé : les entreprises ont posté elles-mêmes leur offre
→ besoin de recrutement 100% confirmé et récent.

Pas d'authentification requise, pas de clé API.
"""

import re
import time
import urllib.parse
from typing import Dict, List, Optional

import cloudscraper
from bs4 import BeautifulSoup

BASE_URL = "https://www.linkedin.com/jobs/search/"

# Mots-clés indiqu que c'est un stage/alternance
_STAGE_KEYWORDS = re.compile(
    r"\b(stage|intern|alternance|alternant|apprenti|apprentissage|vae)\b",
    re.IGNORECASE,
)

# Domaines à exclure de la colonne Lien (on veut l'URL LinkedIn job, pas une redirection)
_EXCL = (
    "linkedin.com/company", "facebook.com", "instagram.com",
    "twitter.com", "google.com", "apple.com",
)


def _type_offre_from_title(title: str) -> str:
    """Déduit le type d'offre depuis le titre de poste."""
    if _STAGE_KEYWORDS.search(title):
        return "Stage / Alternance"
    return "Job étudiant"


class LinkedInJobsScraper:
    """
    Scrape les offres d'emploi LinkedIn en accès public.
    Retourne les entreprises qui ont posté une offre active dans la zone cible.
    """

    def __init__(self, delay: float = 2.0):
        self.delay = delay
        self.scraper = cloudscraper.create_scraper()
        # Note: ne pas ajouter de Referer LinkedIn → déclenche le code 999 (rate limit)
        self.scraper.headers.update({
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        })

    # ── Parsing ──────────────────────────────────────────────────────────────

    def _parse_card(self, card) -> Optional[Dict]:
        """Extrait les données d'une card LinkedIn .base-card."""
        # Nom de l'entreprise
        company_el = card.select_one("h4")
        company = company_el.get_text(strip=True) if company_el else ""
        if not company or len(company) < 2:
            return None

        # Titre du poste
        title_el = card.select_one("h3")
        title = title_el.get_text(strip=True) if title_el else ""

        # Localisation
        loc_el = card.select_one(".job-search-card__location")
        location = loc_el.get_text(strip=True) if loc_el else ""
        # Nettoyer "Paris, Île-de-France, France" → "Paris"
        location = location.split(",")[0].strip()

        # Date de publication
        date_el = card.select_one("time")
        date_posted = date_el.get("datetime", "") if date_el else ""

        # Lien direct vers l'offre LinkedIn
        link_el = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
        job_url = ""
        if link_el:
            href = link_el.get("href", "")
            # Nettoyer les paramètres de tracking
            job_url = href.split("?")[0] if href else ""

        if not job_url:
            return None

        # ID unique pour dédup interne
        entity_urn = card.get("data-entity-urn", "")

        type_offre = _type_offre_from_title(title)
        canal = "Appel" if type_offre == "Job étudiant" else "mail"

        return {
            "Entreprise":       company,
            "Secteur":          title,          # Titre du poste = secteur d'activité visible
            "Ville":            location,
            "Adresse":          location,
            "Téléphone":        "",
            "Email":            "",
            "Lien":             job_url,         # URL offre LinkedIn = preuve de besoin réel
            "_detail_id":       "",
            "_entity_urn":      entity_urn,      # Pour dédup interne (retiré avant export)
            "LinkedIn":         job_url,
            "Type offre visée": type_offre,
            "Canal recommandé": canal,
            "Assigné à":        "",
            "Statut":           "À contacter",
            "Date ajout":       date_posted,
            "Notes":            f"Offre LinkedIn : {title}",
        }

    # ── Point d'entrée ───────────────────────────────────────────────────────

    def scrape(
        self,
        query: str,
        location: str = "Paris",
        max_pages: int = 1,     # LinkedIn limite à ~60 résultats publics (1 page)
        fetch_phones: bool = False,
        progress_callback=None,
    ) -> List[Dict]:
        """
        Scrape les offres LinkedIn pour la requête et la zone données.

        Args:
            query:             terme de recherche (ex: "serveur", "vendeur", "caissier")
            location:          ville (ex: "Paris", "Boulogne-Billancourt")
            max_pages:         ignoré (LinkedIn public = 1 page de ~60 résultats)
            fetch_phones:      ignoré (non disponible via LinkedIn public)
            progress_callback: fonction de log optionnelle

        Returns:
            Liste de dicts prospects (entreprises recrutant activement)
        """
        # LinkedIn attend location avec virgule littérale — ne pas passer par urlencode complet
        loc_enc = urllib.parse.quote(f"{location}, France")
        query_enc = urllib.parse.quote(query)
        # f_TPR=r604800 = offres des 7 derniers jours
        url = f"{BASE_URL}?keywords={query_enc}&location={loc_enc}&f_TPR=r604800"

        if progress_callback:
            progress_callback(
                f"[LinkedIn] Recherche '{query}' @ {location} (offres 7 jours)"
            )

        all_prospects: List[Dict] = []
        seen_urns: set = set()
        seen_companies: set = set()

        try:
            resp = self.scraper.get(url, timeout=20)
            if resp.status_code != 200:
                if progress_callback:
                    progress_callback(
                        f"[LinkedIn] HTTP {resp.status_code} — accès refusé, passage à la suite."
                    )
                return []

            soup = BeautifulSoup(resp.text, "lxml")
            cards = soup.select(".base-card[data-entity-urn]")

            if not cards:
                # Fallback : essai sans filtre date
                url2 = f"{BASE_URL}?keywords={query_enc}&location={loc_enc}"
                resp2 = self.scraper.get(url2, timeout=20)
                if resp2.status_code == 200:
                    soup = BeautifulSoup(resp2.text, "lxml")
                    cards = soup.select(".base-card[data-entity-urn]")

            if not cards and progress_callback:
                progress_callback(f"[LinkedIn] Aucune offre trouvée pour '{query}' @ {location}")

            for card in cards:
                urn = card.get("data-entity-urn", "")
                if urn in seen_urns:
                    continue
                seen_urns.add(urn)

                prospect = self._parse_card(card)
                if not prospect:
                    continue

                # Dédup par entreprise (1 entrée par entreprise même si plusieurs offres)
                company_key = prospect["Entreprise"].lower().strip()
                if company_key in seen_companies:
                    continue
                seen_companies.add(company_key)

                # Retirer les clés internes avant export
                prospect.pop("_entity_urn", None)
                all_prospects.append(prospect)

            if progress_callback:
                progress_callback(
                    f"[LinkedIn] {len(all_prospects)} entreprises uniques "
                    f"trouvées pour '{query}' @ {location}"
                )

        except Exception as e:
            if progress_callback:
                progress_callback(f"[LinkedIn] Erreur : {e}")

        time.sleep(self.delay)
        return all_prospects
