"""
scrapers/indeed.py — Scraper best-effort pour Indeed France.

Note importante : Indeed utilise une protection anti-bot agressive.
Ce scraper fonctionne en mode "best-effort" :
- Il tente de récupérer les noms d'entreprises et localisations depuis les offres d'emploi
- Les données retournées sont partielles (Entreprise + Ville, sans téléphone/email)
- Si Indeed bloque les requêtes, les résultats seront vides (géré silencieusement)

Requêtes utilisées : "étudiant", "alternance", "stage" → cible les entreprises
qui recrutent explicitement des étudiants et jeunes diplômés.
"""

import time
import urllib.parse
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential

BASE_URL = "https://www.indeed.fr/emplois"
HOMEPAGE_URL = "https://www.indeed.fr/"

# Requêtes ciblant les emplois étudiants / stages / alternances
DEFAULT_QUERIES = [
    "job étudiant",
    "stage IDF",
    "alternance",
    "temps partiel étudiant",
]


class IndeedScraper:
    """
    Scrape les entreprises qui recrutent des étudiants sur Indeed France.
    Retourne des dicts partiels (Entreprise + Ville uniquement).
    """

    def __init__(self, delay: float = 3.0, max_retries: int = 3):
        self.delay = delay
        self.max_retries = max_retries
        self.ua = UserAgent()
        self.session = self._build_session()

    def _build_session(self) -> requests.Session:
        """Crée une session avec warm-up Indeed."""
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": self.ua.random,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
        )
        try:
            session.get(HOMEPAGE_URL, timeout=10)
        except Exception:
            pass
        return session

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _get_page(self, url: str) -> Optional[BeautifulSoup]:
        """Charge une page Indeed. Retourne None si bloqué (403, CAPTCHA, etc.)."""
        self.session.headers.update(
            {
                "User-Agent": self.ua.random,
                "Referer": HOMEPAGE_URL,
            }
        )
        try:
            response = self.session.get(url, timeout=15)
            if response.status_code in (403, 429, 503):
                return None
            response.raise_for_status()
            return BeautifulSoup(response.text, "lxml")
        except Exception:
            return None

    def _extract_company_from_card(self, card) -> Optional[Dict]:
        """
        Extrait le nom d'entreprise et la ville depuis une carte d'offre d'emploi.
        Essaie plusieurs sélecteurs pour robustesse face aux changements Indeed.
        """
        # Nom de l'entreprise
        company_el = (
            card.select_one('span[data-testid="company-name"]')
            or card.select_one("a.companyName")
            or card.select_one(".companyName")
            or card.select_one('[class*="company"]')
        )
        if not company_el:
            return None

        company_name = company_el.get_text(strip=True)
        if not company_name or len(company_name) < 2:
            return None

        # Localisation
        location_el = (
            card.select_one('div[data-testid="text-location"]')
            or card.select_one(".companyLocation")
            or card.select_one('[class*="location"]')
        )
        location = location_el.get_text(strip=True) if location_el else ""

        # Extraire la ville (souvent "Paris (75)" ou "Boulogne-Billancourt (92)")
        city = self._parse_city(location)

        return {
            "Entreprise": company_name,
            "Secteur": "Recrutement actif",
            "Ville": city,
            "Adresse": location,
            "Téléphone": "",
            "Email": "",
            "Site web": "",
            "LinkedIn": "",
            "Type offre visée": "",
            "Canal recommandé": "",
            "Assigné à": "",
            "Statut": "À contacter",
            "Date ajout": "",
            "Notes": "Source: Indeed",
        }

    def _parse_city(self, location: str) -> str:
        """Extrait le nom de ville depuis une localisation Indeed."""
        import re
        if not location:
            return ""
        # Indeed affiche souvent "Ville (CP)" ou "Ville, Département"
        clean = re.sub(r"\s*\(\d+\)", "", location).strip()
        # Prend la première partie avant la virgule
        return clean.split(",")[0].strip()

    def scrape(
        self,
        job_queries: Optional[List[str]] = None,
        location: str = "Île-de-France",
        max_pages: int = 5,
        progress_callback=None,
    ) -> List[Dict]:
        """
        Scrape les entreprises recrutant sur Indeed pour les requêtes données.

        Args:
            job_queries: liste de termes de recherche (None = DEFAULT_QUERIES)
            location: zone géographique
            max_pages: nombre max de pages par requête
            progress_callback: fonction de log optionnelle

        Returns:
            Liste de dicts prospects partiels (1 entrée par entreprise unique)
        """
        if job_queries is None:
            job_queries = DEFAULT_QUERIES

        all_prospects = []
        seen_companies = set()  # Dédup interne : 1 entrée par entreprise

        encoded_location = urllib.parse.quote(location)

        for query in job_queries:
            encoded_query = urllib.parse.quote(query)

            for page in range(max_pages):
                start = page * 10
                url = (
                    f"{BASE_URL}?q={encoded_query}&l={encoded_location}"
                    f"&radius=50&start={start}"
                )

                if progress_callback:
                    progress_callback(
                        f"[Indeed] Page {page + 1}/{max_pages} — '{query}' @ {location}"
                    )

                soup = self._get_page(url)

                if soup is None:
                    if progress_callback:
                        progress_callback(
                            "[Indeed] Accès bloqué ou erreur réseau, passage à la requête suivante."
                        )
                    break

                # Recherche des cartes d'offres d'emploi
                cards = (
                    soup.select("div.job_seen_beacon")
                    or soup.select('[data-testid="slider_container"]')
                    or soup.select("div.result")
                    or soup.select("div.jobsearch-SerpJobCard")
                )

                if not cards:
                    if progress_callback:
                        progress_callback(
                            f"[Indeed] Aucune offre trouvée page {page + 1}, arrêt."
                        )
                    break

                for card in cards:
                    try:
                        prospect = self._extract_company_from_card(card)
                        if not prospect:
                            continue
                        # Dédup par nom d'entreprise normalisé
                        key = prospect["Entreprise"].lower().strip()
                        if key not in seen_companies:
                            seen_companies.add(key)
                            all_prospects.append(prospect)
                    except Exception:
                        continue

                if progress_callback:
                    progress_callback(
                        f"[Indeed] {len(all_prospects)} entreprises uniques collectées"
                    )

                time.sleep(self.delay)

        return all_prospects
