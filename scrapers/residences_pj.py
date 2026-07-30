"""
scrapers/residences_pj.py — Scraper de résidences étudiantes privées via Pages Jaunes.

Stratégie :
- Réutilise PagesJaunesScraper (déjà fonctionnel, cloudscraper + sélecteurs réels)
- Requêtes ciblées : "résidence étudiante", "résidence étudiante privée",
  "logement étudiant", "student residence"
- Pour chaque fiche : récupère le VRAI site web officiel (pas la fiche PJ)
  depuis la page détail, puis visite ce site pour extraire Instagram + Email
- Filtre : exclut le CROUS/logement social, garde uniquement les résidences
  privées (utils.residence_taxonomy)
- PAS de téléphone (demande explicite) — Lien, Instagram, Email uniquement
"""

import re
import time
from typing import Dict, List, Optional

from scrapers.pages_jaunes import PagesJaunesScraper, PJ_DOMAIN
from utils.geo import dept_from_address, region_from_dept
from utils.residence_taxonomy import (
    classify_gestionnaire,
    is_public_residence,
    looks_like_residence,
)

RESIDENCE_QUERIES = [
    "résidence étudiante",
    "résidence étudiante privée",
    "logement étudiant",
    "student residence",
]

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_INSTAGRAM_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/[A-Za-z0-9_.\-/]+", re.IGNORECASE
)

# Domaines à ignorer pour l'email (faux positifs communs : sentry, wixpress, etc.)
_EMAIL_DOMAIN_BLACKLIST = (
    "sentry.io", "wixpress.com", "example.com", "domain.com",
    "yourdomain.com", ".png", ".jpg", ".gif", ".svg", ".webp",
)


class ResidencePagesJaunesScraper:
    """Découvre des résidences étudiantes privées via Pages Jaunes."""

    def __init__(self, delay: float = 2.0):
        self.delay = delay
        self._pj = PagesJaunesScraper(delay=delay)

    # ── Extraction email / Instagram depuis le site officiel ────────────────

    def _extract_email_instagram(self, url: str) -> tuple:
        """Visite le site officiel de la résidence pour trouver email + Instagram."""
        if not url or not url.startswith("http"):
            return "", ""
        try:
            resp = self._pj.scraper.get(url, timeout=10)
            text = resp.text

            email = ""
            for m in _EMAIL_RE.finditer(text):
                candidate = m.group(0).lower()
                if not any(bad in candidate for bad in _EMAIL_DOMAIN_BLACKLIST):
                    email = m.group(0)
                    break

            insta_match = _INSTAGRAM_RE.search(text)
            instagram = insta_match.group(0).split("?")[0].rstrip("/") if insta_match else ""

            return email, instagram
        except Exception:
            return "", ""

    # ── Point d'entrée ───────────────────────────────────────────────────────

    def scrape(
        self,
        location: str,
        queries: Optional[List[str]] = None,
        max_pages: int = 2,
        fetch_details: bool = True,
        progress_callback=None,
    ) -> List[Dict]:
        """
        Scrape les résidences étudiantes privées pour une ville donnée.

        Args:
            location:        ville cible
            queries:         liste de requêtes (défaut: RESIDENCE_QUERIES)
            max_pages:       pages Pages Jaunes max par requête
            fetch_details:   si True, visite le site officiel pour email/Instagram
            progress_callback: fonction de log optionnelle

        Returns:
            Liste de dicts résidences (colonnes CSV résidences)
        """
        queries = queries or RESIDENCE_QUERIES
        all_results: List[Dict] = []
        seen_in_run: set = set()

        for query in queries:
            for page in range(1, max_pages + 1):
                url = (
                    f"https://www.pagesjaunes.fr/annuaire/chercherlespros"
                    f"?quoiqui={query.replace(' ', '+')}&ou={location.replace(' ', '+')}&page={page}"
                )
                if progress_callback:
                    progress_callback(
                        f"[Résidences] '{query}' @ {location} — page {page}/{max_pages}"
                    )
                try:
                    soup = self._pj._get(url)
                except Exception as e:
                    if progress_callback:
                        progress_callback(f"[Résidences] Erreur page {page} : {e}")
                    break

                cards = self._pj._parse_listing_page(soup)
                if not cards:
                    break

                for card in cards:
                    name = card.get("Entreprise", "")
                    adresse = card.get("Adresse", "")
                    ville = card.get("Ville", "") or location

                    # Filtre 1 : doit ressembler à une résidence étudiante
                    if not looks_like_residence(name):
                        continue
                    # Filtre 2 : exclure CROUS / logement social
                    if is_public_residence(name, adresse):
                        continue

                    dedup_local = f"{name.lower()}|{ville.lower()}"
                    if dedup_local in seen_in_run:
                        continue
                    seen_in_run.add(dedup_local)

                    website = ""
                    did = card.get("_detail_id", "")
                    if fetch_details and did:
                        try:
                            _phone, website = self._pj._get_detail_info(did)
                        except Exception:
                            website = ""
                        time.sleep(self.delay)

                    lien = website or f"{PJ_DOMAIN}/pros/{did}" if did else ""

                    email, instagram = "", ""
                    if fetch_details and website:
                        email, instagram = self._extract_email_instagram(website)

                    dept = dept_from_address(adresse)
                    region = region_from_dept(dept)

                    all_results.append({
                        "Nom résidence":  name,
                        "Gestionnaire":   classify_gestionnaire(name),
                        "Lien":           lien,
                        "Instagram":      instagram,
                        "Email":          email,
                        "Adresse":        adresse,
                        "Ville":          ville,
                        "Département":    dept,
                        "Région":         region,
                        "Statut":         "À contacter",
                        "Canal de contact": "Email" if email else "Formulaire site",
                        "Remarque":       f"Trouvé via '{query}'" + (
                            f" | Gestionnaire: {classify_gestionnaire(name)}"
                            if classify_gestionnaire(name) else ""
                        ),
                    })

                if progress_callback:
                    progress_callback(
                        f"[Résidences] {len(cards)} fiches examinées "
                        f"(total retenu : {len(all_results)})"
                    )

                time.sleep(self.delay)

        return all_results
