"""
main.py — Point d'entrée CLI du scraper CDE.

Usage :
    python main.py --source pagesjaunes --query "restaurant" --location "Paris"
    python main.py --source google --no-details
    python main.py --source all --query "cabinet rh" --location "Île-de-France"
    python main.py --source all --dry-run  (test sans écrire sur disque)

Options :
    --source     : google | pagesjaunes | indeed | all  (défaut: all)
    --query      : terme de recherche (pour pagesjaunes et indeed)
    --location   : zone géographique (défaut: Île-de-France)
    --max-pages  : nombre max de pages par source (défaut: 10)
    --no-details : ignorer les appels Place Details Google (économise les crédits API)
    --dry-run    : afficher les résultats sans sauvegarder
"""

import argparse
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

from utils.classifier import classify_prospect
from utils.dedup import DedupManager
from utils.exporter import CSV_COLUMNS, ensure_data_dir, generate_summary_stats, read_prospects_df


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scraper de prospects CDE — Île-de-France",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--source",
        choices=["google", "pagesjaunes", "indeed", "all"],
        default="all",
        help="Source(s) à scraper (défaut: all)",
    )
    parser.add_argument(
        "--query",
        default="restaurant",
        help='Terme de recherche pour Pages Jaunes / Indeed (défaut: "restaurant")',
    )
    parser.add_argument(
        "--location",
        default="Île-de-France",
        help='Zone géographique (défaut: "Île-de-France")',
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=10,
        dest="max_pages",
        help="Nombre max de pages par source (défaut: 10)",
    )
    parser.add_argument(
        "--no-details",
        action="store_true",
        dest="no_details",
        help="Ignorer les appels Place Details Google (économise les crédits API)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Afficher les résultats sans sauvegarder sur disque",
    )
    return parser.parse_args()


def log(message: str):
    """Affiche un message horodaté."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")


def run_pagesjaunes(query: str, location: str, max_pages: int) -> list:
    """Lance le scraping Pages Jaunes."""
    from scrapers.pages_jaunes import PagesJaunesScraper

    log(f"Pages Jaunes — Requête: '{query}' @ {location} (max {max_pages} pages)")
    scraper = PagesJaunesScraper()
    results = scraper.scrape(
        query=query,
        location=location,
        max_pages=max_pages,
        progress_callback=log,
    )
    log(f"Pages Jaunes — {len(results)} fiches récupérées")
    return results


def run_google_maps(fetch_details: bool) -> list:
    """Lance le scraping Google Places."""
    api_key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
    if not api_key or api_key == "your_key_here":
        log(
            "ATTENTION: GOOGLE_PLACES_API_KEY non définie dans .env — "
            "source Google ignorée."
        )
        return []

    from scrapers.google_maps import GoogleMapsScraper

    log(f"Google Maps — Scraping IDF (fetch_details={fetch_details})")
    scraper = GoogleMapsScraper(api_key=api_key)
    results = scraper.scrape_idf(
        fetch_details=fetch_details,
        progress_callback=log,
    )
    log(f"Google Maps — {len(results)} fiches récupérées")
    return results


def run_indeed(location: str, max_pages: int) -> list:
    """Lance le scraping Indeed."""
    from scrapers.indeed import IndeedScraper

    log(f"Indeed — @ {location} (max {max_pages} pages par requête)")
    scraper = IndeedScraper()
    results = scraper.scrape(
        location=location,
        max_pages=max_pages,
        progress_callback=log,
    )
    log(f"Indeed — {len(results)} entreprises uniques récupérées")
    return results


def process_and_save(
    raw_results: list,
    dedup: DedupManager,
    dry_run: bool,
) -> tuple:
    """
    Applique classification + déduplication sur les résultats bruts.
    Retourne (nb_nouveaux, nb_doublons).
    """
    for prospect in raw_results:
        # Appliquer les règles métier si pas encore classifiés
        if not prospect.get("Canal recommandé"):
            canal, type_offre = classify_prospect(
                prospect.get("Secteur", ""),
                prospect.get("Entreprise", ""),
            )
            prospect["Canal recommandé"] = canal
            prospect["Type offre visée"] = type_offre

        # Vérification doublon
        dedup.check_and_register(prospect)

    stats = dedup.get_stats()

    if not dry_run:
        new_count, dupe_count = dedup.flush_to_disk()
    else:
        new_count = stats["session_new"]
        dupe_count = stats["session_dupes"]
        log("[DRY RUN] Aucun fichier écrit sur disque.")

    return new_count, dupe_count


def print_summary(new_count: int, dupe_count: int, total_known: int):
    """Affiche le résumé de la session."""
    print("\n" + "=" * 50)
    print("  RÉSUMÉ DE LA SESSION")
    print("=" * 50)
    print(f"  Nouveaux prospects ajoutés : {new_count}")
    print(f"  Doublons évités            : {dupe_count}")
    print(f"  Total prospects en base    : {total_known}")
    print("=" * 50)

    if new_count > 0:
        df = read_prospects_df()
        if not df.empty:
            stats = generate_summary_stats(df)
            print("\n  Répartition par canal :")
            for canal, count in stats.get("by_canal", {}).items():
                print(f"    {canal}: {count}")
            print("\n  Répartition par type d'offre :")
            for offre, count in stats.get("by_type_offre", {}).items():
                print(f"    {offre}: {count}")
            print("\n  Top 5 villes :")
            for i, (ville, count) in enumerate(
                list(stats.get("by_ville", {}).items())[:5]
            ):
                print(f"    {i+1}. {ville}: {count}")
    print()


def main():
    load_dotenv()
    ensure_data_dir()
    args = parse_args()

    log("Démarrage du scraper CDE")
    log(f"Source: {args.source} | Requête: '{args.query}' | Zone: {args.location}")

    # Charger le gestionnaire de doublons (charge les CSV existants)
    dedup = DedupManager()
    log(f"Base chargée : {len(dedup.known_keys)} prospects connus")

    all_raw_results = []

    # --- Pages Jaunes ---
    if args.source in ("pagesjaunes", "all"):
        results = run_pagesjaunes(args.query, args.location, args.max_pages)
        all_raw_results.extend(results)

    # --- Google Maps ---
    if args.source in ("google", "all"):
        results = run_google_maps(fetch_details=not args.no_details)
        all_raw_results.extend(results)

    # --- Indeed ---
    if args.source in ("indeed", "all"):
        results = run_indeed(args.location, args.max_pages)
        all_raw_results.extend(results)

    if not all_raw_results:
        log("Aucun résultat collecté. Vérifiez vos paramètres ou la connectivité.")
        sys.exit(0)

    log(f"Total brut collecté : {len(all_raw_results)} fiches")

    # Traitement + sauvegarde
    new_count, dupe_count = process_and_save(all_raw_results, dedup, args.dry_run)

    # Afficher le résumé
    print_summary(new_count, dupe_count, len(dedup.known_keys))

    if not args.dry_run and new_count > 0:
        log(f"Fichier principal : data/prospects_CDE.csv")
        if dupe_count > 0:
            log(f"Fichier doublons  : data/doublons_CDE.csv")


if __name__ == "__main__":
    main()
