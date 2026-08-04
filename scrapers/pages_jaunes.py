"""
scrapers/pages_jaunes.py — Scraper HTML pour Pages Jaunes.

Stratégie :
- cloudscraper pour contourner le challenge Cloudflare (résolvait le 403)
- Sélecteurs réels issus du HTML live de pagesjaunes.fr :
    Container  : div.bi-content       (20 résultats par page)
    Nom        : .bi-header-title h3
    Adresse    : .bi-address
    Téléphone  : regex sur la page detail /pros/{id}
- Pagination via le paramètre &page=N (confirmé en live)
- Délai de 2s minimum entre les requêtes
"""

import os
import re
import time
import urllib.parse
from typing import Dict, List, Optional

import cloudscraper
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_fixed

BASE_URL = "https://www.pagesjaunes.fr/annuaire/chercherlespros"
DETAIL_URL = "https://www.pagesjaunes.fr/pros/{}"
PJ_DOMAIN = "https://www.pagesjaunes.fr"

# Regex téléphone FR (capturée sur les pages détail)
PHONE_RE = re.compile(
    r"(?:0|\+33)[1-9][\s.\-]?\d{2}[\s.\-]?\d{2}[\s.\-]?\d{2}[\s.\-]?\d{2}"
)


def _clean_phone(raw: str) -> str:
    """
    Nettoie et valide un numéro FR. Retourne format '01 23 45 67 89' ou '' si invalide.
    """
    if not raw:
        return ""
    # Garder uniquement les chiffres et le +
    digits = re.sub(r"[^\d+]", "", raw)
    # +33 → 0
    if digits.startswith("+33"):
        digits = "0" + digits[3:]
    elif digits.startswith("33") and len(digits) == 11:
        digits = "0" + digits[2:]
    # Valider : 10 chiffres commençant par 0
    if len(digits) != 10 or not digits.startswith("0"):
        return ""
    # Format lisible : 01 23 45 67 89
    return f"{digits[0:2]} {digits[2:4]} {digits[4:6]} {digits[6:8]} {digits[8:10]}"

# Requêtes prédéfinies par catégorie (utile pour l'UI)
PRESET_QUERIES = {
    "restaurants":    "restaurant",
    "boulangeries":   "boulangerie patisserie",
    "commerces":      "commerce boutique",
    "supermarchés":   "supermarche epicerie",
    "pme_startups":   "agence conseil startup",
    "cabinets_rh":    "agence recrutement ressources humaines",
    "grandes_enseignes": "grande surface",
    "bars_cafes":     "bar cafe brasserie",
}


class PagesJaunesScraper:
    """Scrape les annonces Pages Jaunes via cloudscraper (contourne Cloudflare)."""

    def __init__(self, delay: float = 2.0):
        self.delay = delay
        self.scraper = cloudscraper.create_scraper()
        self.scraper.headers.update({
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
        })

        # Fallback : sur un serveur cloud (IP datacenter), Cloudflare bloque
        # souvent cloudscraper seul. On peut fournir un cookie de session
        # capturé depuis un vrai navigateur (variable PJ_COOKIE_HEADER) pour
        # se faire passer pour cette session déjà validée.
        cookie_header = os.getenv("PJ_COOKIE_HEADER", "").strip()
        if cookie_header:
            self.scraper.headers.update({"Cookie": cookie_header})

        self._warmed_up = False

    def _warm_up(self):
        """Visite la page d'accueil une fois pour obtenir les cookies Cloudflare."""
        if self._warmed_up:
            return
        try:
            self.scraper.get(PJ_DOMAIN, timeout=15)
        except Exception:
            pass
        self._warmed_up = True

    # ── Requêtes réseau ──────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def _get(self, url: str) -> BeautifulSoup:
        """GET avec retry automatique. Lève une exception si status != 200."""
        self._warm_up()
        resp = self.scraper.get(url, timeout=20)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")

    # ── Parsing d'une page de résultats ─────────────────────────────────────

    def _parse_listing_page(self, soup: BeautifulSoup) -> List[Dict]:
        """Extrait les fiches de la page de résultats."""
        results = []
        cards = soup.select("div.bi-content")
        for card in cards:
            try:
                p = self._extract_card(card)
                if p.get("Entreprise"):
                    results.append(p)
            except Exception:
                continue
        return results

    def _extract_card(self, card) -> Dict:
        """Extrait les champs d'une fiche .bi-content."""
        # Nom
        name_el = card.select_one(".bi-header-title h3") or card.select_one(".bi-header-title h2")
        name = name_el.get_text(strip=True) if name_el else ""

        # Adresse brute (ex: "1 rue Auber 75009 Paris Voir le plan")
        addr_el = card.select_one(".bi-address")
        addr_raw = addr_el.get_text(separator=" ", strip=True) if addr_el else ""
        # Nettoyer "Voir le plan" en fin
        addr_clean = re.sub(r"\s*Voir le plan.*$", "", addr_raw).strip()

        # Extraire ville et code postal
        ville, cp = self._parse_address(addr_clean)

        # Lien vers la page détail (/pros/XXXXXXXX)
        detail_id = self._extract_detail_id(card)

        return {
            "Entreprise":      name,
            "Secteur":         "",
            "Ville":           ville,
            "Adresse":         addr_clean,
            "Téléphone":       "",   # rempli optionnellement via _get_detail_phone
            "Email":           "",
            "Lien":            "",
            "_detail_id":      detail_id,  # clé temporaire, retirée à l'export
            "LinkedIn":        "",
            "Type offre visée":"",
            "Canal recommandé":"",
            "Assigné à":       "",
            "Statut":          "À contacter",
            "Date ajout":      "",
            "Notes":           "",
        }

    def _parse_address(self, addr: str):
        """Retourne (ville, code_postal) depuis une adresse brute PJ."""
        # Cherche un code postal 5 chiffres
        m = re.search(r"(\d{5})\s+(.+?)$", addr)
        if m:
            return m.group(2).strip(), m.group(1)
        # Fallback : dernier mot
        parts = addr.rsplit(" ", 1)
        return (parts[-1] if len(parts) > 1 else addr), ""

    def _extract_detail_id(self, card) -> str:
        """Extrait l'ID de la page détail depuis les liens de la carte."""
        for a in card.find_all("a", href=True):
            m = re.search(r"/pros/(\d+)", a["href"])
            if m:
                return m.group(1)
        return ""

    # ── Page détail (téléphone + lien) ──────────────────────────────────────

    # Domaines à exclure (réseaux sociaux / agrégateurs / partenaires PJ)
    _EXCLUDED_DOMAINS = (
        "pagesjaunes.fr", "solocal.com", "facebook.com", "instagram.com",
        "google.", "twitter.com", "youtube.com", "linkedin.com", "tripadvisor",
        "leboncoin", "lafourchette", "thefork", "deliveroo", "ubereats",
        "justeat", "maps.", "apple.com", "android.", "yelp.", "g.page",
        "tiktok.com", "snapchat.com", "booking.com", "opentable",
    )

    # Regex pour détecter un nom de domaine dans du texte brut (ex: "altosor-communication.com")
    _DOMAIN_RE = re.compile(
        r'^(?:www\.)?[\w\-][\w\-\.]+\.'
        r'(?:fr|com|org|net|eu|io|co|biz|pro|info|shop|store|app|online|paris|fr)$',
        re.IGNORECASE,
    )

    def _extract_website_from_soup(self, soup) -> str:
        """
        Extrait le site web depuis la page détail PJ.

        Stratégie :
        1. Cherche <span class="value"> précédé d'une icône "icon-lien"
           → PJ affiche le domaine en clair dans ces spans (href="#" car chargé par JS)
        2. Cherche les <a href="#"> dont le texte ressemble à un domaine
        3. Cherche les <a href="http..."> externes non-exclus (fallback)
        """
        # ── Stratégie 1 : icon-lien + span.value (fiable, structure PJ connue) ──
        for icon_el in soup.select(".icon-lien"):
            value_span = icon_el.find_next_sibling("span", class_="value")
            if not value_span:
                # L'icône peut être dans un conteneur — cherche le span voisin
                parent = icon_el.parent
                if parent:
                    value_span = parent.find("span", class_="value")
            if value_span:
                raw = value_span.get_text(strip=True).lower()
                if self._DOMAIN_RE.match(raw):
                    if not any(d in raw for d in self._EXCLUDED_DOMAINS):
                        domain = raw.lstrip("www.")
                        return f"https://www.{domain}"

        # ── Stratégie 2 : span.value avec texte ressemblant à un domaine ──
        for span in soup.select("span.value"):
            raw = span.get_text(strip=True).lower()
            if "." in raw and self._DOMAIN_RE.match(raw):
                if not any(d in raw for d in self._EXCLUDED_DOMAINS):
                    domain = raw.lstrip("www.")
                    return f"https://www.{domain}"

        # ── Stratégie 3 : liens href réels (fallback) ──
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http"):
                continue
            if any(d in href.lower() for d in self._EXCLUDED_DOMAINS):
                continue
            return href.split("?")[0].rstrip("/")

        return ""

    def _get_detail_info(self, detail_id: str):
        """
        Récupère (téléphone, site_web) depuis la page détail /pros/{id}.
        """
        if not detail_id:
            return "", ""
        try:
            url = DETAIL_URL.format(detail_id)
            soup = self._get(url)

            # Téléphone : regex FR sur le texte complet de la page
            phones = PHONE_RE.findall(soup.get_text())
            phone = phones[0] if phones else ""

            # Site web : 3 stratégies successives
            website = self._extract_website_from_soup(soup)

            return phone, website
        except Exception:
            return "", ""

    # ── Point d'entrée ───────────────────────────────────────────────────────

    def scrape(
        self,
        query: str,
        location: str = "Paris",
        max_pages: int = 10,
        fetch_phones: bool = True,
        progress_callback=None,
    ) -> List[Dict]:
        """
        Lance le scraping Pages Jaunes.

        Args:
            query:            terme de recherche (ex: "restaurant")
            location:         zone (ex: "Paris", "Île-de-France", "92")
            max_pages:        nombre max de pages (20 fiches/page)
            fetch_phones:     si True, visite chaque page détail pour le tél.
                              (plus lent mais données complètes)
            progress_callback: fonction de log optionnelle

        Returns:
            Liste de dicts prospects (14 colonnes CSV + nettoyage _detail_id)
        """
        eq = urllib.parse.quote(query)
        el = urllib.parse.quote(location)

        all_results = []

        for page in range(1, max_pages + 1):
            url = f"{BASE_URL}?quoiqui={eq}&ou={el}&page={page}"

            if progress_callback:
                progress_callback(
                    f"[Pages Jaunes] Page {page}/{max_pages} — {query} @ {location}"
                )

            try:
                soup = self._get(url)
            except Exception as e:
                if progress_callback:
                    progress_callback(f"[Pages Jaunes] Erreur page {page} : {e}")
                break

            page_results = self._parse_listing_page(soup)

            if not page_results:
                if progress_callback:
                    progress_callback(f"[Pages Jaunes] Aucun résultat page {page} — arrêt.")
                break

            # Récupérer les téléphones sur les pages détail (optionnel)
            if fetch_phones:
                for p in page_results:
                    did = p.pop("_detail_id", "")
                    if did:
                        phone, website = self._get_detail_info(did)
                        p["Téléphone"] = _clean_phone(phone)
                        # Lien = fiche PJ exacte du lieu (adresse, tél, carte)
                        # PAS le site générique (mcdonalds.fr) mais la page de CE resto précis
                        p["Lien"] = f"{PJ_DOMAIN}/pros/{did}"
                        time.sleep(self.delay)
            else:
                for p in page_results:
                    did = p.pop("_detail_id", "")
                    if did:
                        # Même sans fetch_phones, on met le lien PJ exact
                        p["Lien"] = f"{PJ_DOMAIN}/pros/{did}"

            all_results.extend(page_results)

            if progress_callback:
                progress_callback(
                    f"[Pages Jaunes] {len(page_results)} fiches extraites "
                    f"(total session : {len(all_results)})"
                )

            # Pause avant la page suivante
            time.sleep(self.delay)

        return all_results
