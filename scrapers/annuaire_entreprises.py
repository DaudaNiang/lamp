"""
scrapers/annuaire_entreprises.py — Scraper via l'API officielle data.gouv.fr.

API : https://recherche-entreprises.api.gouv.fr/search
- Gratuite, sans clé d'authentification
- Données officielles SIRENE (registre national des entreprises)
- Idéal pour PMEs, startups, commerces, associations
- Pas de téléphone mais : nom, adresse, ville, secteur (code NAF), SIRET

Documentation : https://recherche-entreprises.api.gouv.fr/docs
"""

import re
import time
from typing import Dict, List, Optional

import requests

API_URL = "https://recherche-entreprises.api.gouv.fr/search"
PER_PAGE = 25


class AnnuaireEntreprisesScraper:
    """
    Interroge l'API officielle data.gouv.fr pour récupérer des entreprises IDF.
    Aucune clé API, aucun risque de blocage.
    """

    def __init__(self, delay: float = 0.5):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "CDE-ScraperBot/1.0 (association étudiante, usage interne)",
        })

    # ── Mapping ville → département ─────────────────────────────────────────

    _DEPT_KEYWORDS: List[tuple] = [
        ("75", ["paris"]),
        ("92", ["boulogne", "nanterre", "courbevoie", "issy-les-moulineaux",
                "levallois", "neuilly", "clichy", "rueil", "colombes",
                "asnières", "antony", "montrouge", "sceaux", "clamart",
                "châtenay", "châtillon"]),
        ("93", ["saint-denis", "montreuil", "aubervilliers", "noisy-le-grand",
                "pantin", "épinay", "bobigny", "bondy", "aulnay", "drancy",
                "courneuve", "villepinte"]),
        ("94", ["créteil", "vitry-sur-seine", "champigny", "saint-maur",
                "ivry", "vincennes", "maisons-alfort", "charenton",
                "alfortville", "villejuif"]),
        ("91", ["évry", "corbeil", "massy", "palaiseau", "gif-sur-yvette",
                "les ulis", "sainte-geneviève-des-bois"]),
        ("95", ["cergy", "argenteuil", "sarcelles", "pontoise", "gonesse",
                "enghien", "garges"]),
        ("78", ["versailles", "saint-germain-en-laye", "mantes", "poissy",
                "guyancourt", "vélizy", "rambouillet"]),
        ("77", ["meaux", "melun", "chelles", "marne-la-vallée",
                "pontault-combault", "dammarie"]),
    ]

    def _dept_from_location(self, location: str) -> str:
        """Retourne le code département (2 chiffres) depuis un nom de ville IDF."""
        loc = location.lower().strip()
        # Cherche d'abord un code postal/département explicite dans la chaîne
        m = re.search(r"\b(75|77|78|91|92|93|94|95)\b", loc)
        if m:
            return m.group(1)
        for dept_code, keywords in self._DEPT_KEYWORDS:
            if any(kw in loc for kw in keywords):
                return dept_code
        return "75"  # fallback Paris

    # ── Appel API ────────────────────────────────────────────────────────────

    def _fetch_page(self, query: str, dept: str, page: int) -> Optional[dict]:
        """Appelle l'API et retourne le JSON, ou None en cas d'erreur."""
        params = {
            "q": query,
            "departement": dept,
            "per_page": PER_PAGE,
            "page": page,
            # On cible uniquement les entreprises actives
            "etat_administratif": "A",
        }
        try:
            resp = self.session.get(API_URL, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None

    # ── Conversion d'un résultat API en prospect ─────────────────────────────

    def _entry_to_prospect(self, entry: dict) -> Optional[Dict]:
        """Convertit un résultat JSON de l'API en dict prospect."""
        nom = (entry.get("nom_complet") or "").strip().title()
        if not nom:
            return None

        siege = entry.get("siege") or {}

        # Construction de l'adresse
        parts_addr = [
            siege.get("numero_voie", ""),
            siege.get("indice_repetition", ""),
            siege.get("type_voie", ""),
            siege.get("libelle_voie", ""),
        ]
        adresse = " ".join(p for p in parts_addr if p).strip().title()
        ville = (siege.get("libelle_commune") or siege.get("commune") or "").title()
        cp = siege.get("code_postal", "")

        adresse_complete = ", ".join(filter(None, [adresse, f"{cp} {ville}".strip()])).strip(", ")

        # Code NAF (secteur)
        naf_code = entry.get("activite_principale", "")
        naf_libelle = entry.get("libelle_activite_principale", "") or naf_code

        siret = siege.get("siret", "")

        return {
            "Entreprise":       nom,
            "Secteur":          naf_libelle,
            "Ville":            ville,
            "Adresse":          adresse_complete,
            "Téléphone":        "",
            "Email":            "",
            "Lien":             "",
            "_detail_id":       "",
            "LinkedIn":         "",
            "Type offre visée": "",
            "Canal recommandé": "",
            "Assigné à":        "",
            "Statut":           "À contacter",
            "Date ajout":       "",
            "Notes":            f"Source: Annuaire officiel | SIRET: {siret}",
        }

    # ── Point d'entrée ───────────────────────────────────────────────────────

    def scrape(
        self,
        query: str,
        location: str = "Paris",
        max_pages: int = 5,
        fetch_phones: bool = False,  # L'API ne fournit pas de téléphones
        progress_callback=None,
    ) -> List[Dict]:
        """
        Interroge l'Annuaire officiel des entreprises (data.gouv.fr).

        Args:
            query:             terme de recherche (ex: "restaurant", "agence marketing")
            location:          ville ou zone IDF
            max_pages:         nombre max de pages (25 résultats/page)
            fetch_phones:      ignoré (l'API ne fournit pas de téléphones)
            progress_callback: fonction de log optionnelle

        Returns:
            Liste de dicts prospects
        """
        dept = self._dept_from_location(location)
        all_results: List[Dict] = []

        for page in range(1, max_pages + 1):
            if progress_callback:
                progress_callback(
                    f"[Annuaire] Page {page}/{max_pages} — {query} @ {location} (dept {dept})"
                )

            data = self._fetch_page(query, dept, page)

            if not data:
                if progress_callback:
                    progress_callback(f"[Annuaire] Erreur réseau page {page} — arrêt.")
                break

            results = data.get("results") or []
            if not results:
                if progress_callback:
                    progress_callback(f"[Annuaire] Aucun résultat page {page} — arrêt.")
                break

            for entry in results:
                prospect = self._entry_to_prospect(entry)
                if prospect:
                    all_results.append(prospect)

            total_api = data.get("total_results", "?")
            if progress_callback:
                progress_callback(
                    f"[Annuaire] {len(results)} fiches extraites "
                    f"(total session : {len(all_results)} / {total_api} disponibles)"
                )

            # Vérifier si on a tout récupéré
            if len(all_results) >= int(total_api if str(total_api).isdigit() else 999999):
                break

            time.sleep(self.delay)

        return all_results
