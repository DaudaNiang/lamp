"""
scrapers/google_maps.py — Scraper Google Places API pour l'IDF.

Stratégie de couverture IDF :
- 15 points d'ancrage répartis sur les 8 départements IDF
- Rayon de 15 km par point (chevauchement léger pour ne pas avoir de zones blanches)
- ~60 résultats max par requête (type, localisation)
- Pagination via next_page_token (max 3 pages = 60 résultats par (point, type))

Note sur les coûts API :
- Nearby Search : ~$0.032 par requête
- Place Details : ~$0.017 par requête (champs basiques)
- Utiliser fetch_details=False pour économiser si nécessaire
"""

import os
import re
import time
from typing import Dict, List, Optional, Tuple

import googlemaps

# Points d'ancrage couvrant toute l'Île-de-France (lat, lng)
IDF_SEARCH_POINTS = [
    ("Paris Centre",         48.8566,  2.3522),
    ("Paris Nord",           48.8848,  2.3470),
    ("Paris Est",            48.8566,  2.4000),
    ("Paris Ouest",          48.8566,  2.2700),
    ("Paris Sud",            48.8296,  2.3522),
    ("Boulogne-Billancourt", 48.8350,  2.2400),
    ("Versailles",           48.8044,  2.1204),
    ("Saint-Denis",          48.9363,  2.3558),
    ("Argenteuil",           48.9472,  2.2467),
    ("Créteil",              48.7904,  2.4555),
    ("Évry",                 48.6234,  2.4454),
    ("Marne-la-Vallée",      48.8350,  2.6300),
    ("Pontoise",             49.0503,  2.1003),
    ("Meaux",                48.9600,  2.8900),
    ("Melun",                48.5406,  2.6564),
]

SEARCH_RADIUS_METERS = 15_000

# Codes postaux valides pour l'IDF (75, 77, 78, 91, 92, 93, 94, 95)
IDF_POSTAL_PREFIXES = {"75", "77", "78", "91", "92", "93", "94", "95"}

# Groupes de types à scraper par catégorie d'entreprise
PLACE_TYPE_GROUPS = {
    "restaurants": ["restaurant", "bakery", "cafe", "bar", "meal_takeaway"],
    "commerces": ["supermarket", "grocery_or_supermarket", "convenience_store",
                  "clothing_store", "shoe_store", "florist"],
    "services": ["beauty_salon", "hair_care", "gym", "spa", "pharmacy"],
    "bureaux_pme": ["accounting", "real_estate_agency", "insurance_agency",
                    "finance", "travel_agency"],
    "rh_recrutement": ["employment_agency"],
}

# Tous les types combinés
ALL_PLACE_TYPES = [t for types in PLACE_TYPE_GROUPS.values() for t in types]


class GoogleMapsScraper:
    """
    Scrape les établissements en Île-de-France via l'API Google Places.
    """

    def __init__(self, api_key: str, delay: float = 2.0):
        """
        Args:
            api_key: clé API Google Places
            delay: délai minimum entre les requêtes (secondes)
        """
        self.gmaps = googlemaps.Client(key=api_key)
        self.delay = delay

    def _nearby_search_all_pages(
        self,
        location: Tuple[float, float],
        radius: int,
        place_type: str,
    ) -> List[Dict]:
        """
        Effectue une recherche Nearby et suit la pagination via next_page_token.
        Maximum 3 pages (60 résultats) par requête.
        """
        results = []
        response = self.gmaps.places_nearby(
            location=location,
            radius=radius,
            type=place_type,
        )
        results.extend(response.get("results", []))

        # Pagination
        for _ in range(2):  # 2 pages supplémentaires max
            next_token = response.get("next_page_token")
            if not next_token:
                break
            # Le token n'est pas immédiatement valide — attendre obligatoirement
            time.sleep(2.5)
            try:
                response = self.gmaps.places_nearby(page_token=next_token)
                results.extend(response.get("results", []))
            except Exception:
                break

        return results

    def _get_place_details(self, place_id: str) -> Dict:
        """
        Récupère les détails d'un établissement (téléphone, site web, adresse complète).
        Champs minimaux pour limiter les coûts.
        """
        try:
            result = self.gmaps.place(
                place_id,
                fields=[
                    "name",
                    "formatted_address",
                    "formatted_phone_number",
                    "international_phone_number",
                    "website",
                    "types",
                ],
            )
            return result.get("result", {})
        except Exception:
            return {}

    def _extract_city(self, formatted_address: str) -> str:
        """
        Extrait la ville depuis une adresse formatée Google.
        Ex: "12 Rue de Rivoli, 75001 Paris, France" → "Paris"
        """
        if not formatted_address:
            return ""
        # Cherche un mot après le code postal IDF
        match = re.search(r"\b(75|77|78|91|92|93|94|95)\d{3}\s+([^\,]+)", formatted_address)
        if match:
            return match.group(2).strip()
        # Fallback : avant-dernier token avant "France"
        parts = [p.strip() for p in formatted_address.split(",") if p.strip()]
        if len(parts) >= 2 and parts[-1].strip().lower() in ("france", "fr"):
            city_part = parts[-2].strip()
            # Supprimer le code postal s'il est collé à la ville
            city_part = re.sub(r"^\d{5}\s*", "", city_part).strip()
            return city_part
        return ""

    def _is_in_idf(self, formatted_address: str) -> bool:
        """Vérifie que l'adresse appartient bien à l'IDF via le code postal."""
        if not formatted_address:
            return True  # Bénéfice du doute si adresse absente
        match = re.search(r"\b(\d{5})\b", formatted_address)
        if match:
            cp = match.group(1)
            return cp[:2] in IDF_POSTAL_PREFIXES
        return True

    def _normalize_result(self, raw: Dict, details: Dict) -> Dict:
        """
        Fusionne les données Nearby Search et Place Details en un dict prospect standardisé.
        """
        from utils.classifier import classify_prospect, infer_secteur_from_types

        name = details.get("name") or raw.get("name", "")
        address = details.get("formatted_address") or raw.get("vicinity", "")
        phone = (
            details.get("formatted_phone_number")
            or details.get("international_phone_number")
            or ""
        )
        website = details.get("website") or ""
        types = details.get("types") or raw.get("types", [])

        secteur = infer_secteur_from_types(types)
        ville = self._extract_city(address)
        canal, type_offre = classify_prospect(secteur, name)

        return {
            "Entreprise": name,
            "Secteur": secteur,
            "Ville": ville,
            "Adresse": address,
            "Téléphone": phone,
            "Email": "",
            "Site web": website,
            "LinkedIn": "",
            "Type offre visée": type_offre,
            "Canal recommandé": canal,
            "Assigné à": "",
            "Statut": "À contacter",
            "Date ajout": "",
            "Notes": "",
        }

    def scrape_idf(
        self,
        place_types: Optional[List[str]] = None,
        fetch_details: bool = True,
        progress_callback=None,
    ) -> List[Dict]:
        """
        Scrape tous les points IDF pour les types d'établissements demandés.

        Args:
            place_types: liste de types Google Places (None = tous les types)
            fetch_details: si True, appelle Place Details pour chaque résultat
                          (plus de données mais plus coûteux en API calls)
            progress_callback: fonction optionnelle de log

        Returns:
            Liste de dicts prospects normalisés
        """
        if place_types is None:
            place_types = ALL_PLACE_TYPES

        all_results = []
        seen_place_ids = set()  # Dédup interne par place_id

        total_tasks = len(IDF_SEARCH_POINTS) * len(place_types)
        task_num = 0

        for point_name, lat, lng in IDF_SEARCH_POINTS:
            location = (lat, lng)

            for place_type in place_types:
                task_num += 1

                if progress_callback:
                    progress_callback(
                        f"[Google Maps] {task_num}/{total_tasks} — "
                        f"{place_type} @ {point_name}"
                    )

                try:
                    raw_results = self._nearby_search_all_pages(
                        location, SEARCH_RADIUS_METERS, place_type
                    )
                except Exception as e:
                    if progress_callback:
                        progress_callback(
                            f"[Google Maps] Erreur {place_type}@{point_name}: {e}"
                        )
                    time.sleep(self.delay)
                    continue

                new_results = 0
                for raw in raw_results:
                    place_id = raw.get("place_id", "")

                    # Dédup interne (évite de récupérer les détails plusieurs fois)
                    if place_id and place_id in seen_place_ids:
                        continue
                    if place_id:
                        seen_place_ids.add(place_id)

                    # Récupérer les détails si demandé
                    details = {}
                    if fetch_details and place_id:
                        try:
                            details = self._get_place_details(place_id)
                            time.sleep(self.delay)
                        except Exception:
                            pass

                    # Normaliser
                    prospect = self._normalize_result(raw, details)

                    # Filtrer les résultats hors IDF
                    if not self._is_in_idf(prospect["Adresse"]):
                        continue

                    all_results.append(prospect)
                    new_results += 1

                if progress_callback:
                    progress_callback(
                        f"[Google Maps] {new_results} nouveaux résultats "
                        f"(total: {len(all_results)})"
                    )

                time.sleep(self.delay)

        return all_results
