"""
utils/exporter.py — Export CSV aligné sur le CRM Google Sheets.

Colonnes CRM (ordre exact) :
    Semaine | Membre responsable | Lien | Entreprise | Contact | SCORE |
    Type de partenariat(Leads) | Date du premier contact | Localisation |
    Canal de contact | Statut | Prochain Action | Remarque

Architecture par session :
    Chaque scraping → data/sessions/session_YYYYMMDD_HHMM.csv
    Consolidé → data/prospects_CDE.csv
    Doublons → data/doublons_CDE.csv

Encodage : utf-8-sig (BOM) pour Excel et Google Sheets.
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

# Chemins
DATA_DIR = Path("data")
SESSIONS_DIR = DATA_DIR / "sessions"
PROSPECTS_FILE = DATA_DIR / "prospects_CDE.csv"
DOUBLONS_FILE = DATA_DIR / "doublons_CDE.csv"

# ─── Colonnes CRM (ordre exact) ──────────────────────────────────────────────
CSV_COLUMNS = [
    "Semaine",                      # vide — rempli manuellement
    "Membre responsable",           # vide — rempli manuellement
    "Lien",                         # URL fiche PJ ou source
    "Entreprise",                   # nom de l'établissement
    "Catégorie",                    # Restaurant, Baby-sitting, Vente, etc.
    "Contact",                      # téléphone direct
    "SCORE",                        # score /10 calculé automatiquement
    "Type de partenariat(Leads)",   # "SAJ Job" par défaut
    "Date du premier contact",      # vide — rempli manuellement
    "Localisation",                 # ville / arrondissement
    "Canal de contact",             # "Appel" par défaut
    "Statut",                       # "À contacter" par défaut
    "Prochain Action",              # vide — rempli manuellement
    "Remarque",                     # détail du score (2-3 critères)
]


def ensure_data_dir():
    """Crée les répertoires data/ et data/sessions/."""
    DATA_DIR.mkdir(exist_ok=True)
    SESSIONS_DIR.mkdir(exist_ok=True)


def _normalize_prospect(prospect: Dict) -> Dict:
    """Convertit un dict interne du scraper en ligne CRM."""
    # Contact = téléphone en priorité
    contact = (
        prospect.get("Téléphone", "").strip()
        or prospect.get("Email", "").strip()
        or prospect.get("Contact", "").strip()
        or ""
    )

    # Score /10 (déjà calculé par qualifier.py)
    score = prospect.get("SCORE", "")

    # Remarque = détail du score
    remarque = (
        prospect.get("_score_reasons", "")
        or prospect.get("Remarque", "")
        or prospect.get("Notes", "")
        or ""
    )

    # Catégorie (Restaurant, Baby-sitting, etc.)
    from utils.categories import classify_offer
    categorie = (
        prospect.get("Catégorie", "")
        or classify_offer(
            prospect.get("Secteur", ""),
            prospect.get("Notes", ""),
            prospect.get("Entreprise", ""),
        )
    )

    row = {
        "Semaine":                     prospect.get("Semaine", ""),
        "Membre responsable":          prospect.get("Membre responsable", ""),
        "Lien":                        prospect.get("Lien", "") or prospect.get("Site web", ""),
        "Entreprise":                  prospect.get("Entreprise", ""),
        "Catégorie":                   categorie,
        "Contact":                     contact,
        "SCORE":                       score,
        "Type de partenariat(Leads)":  prospect.get("Type de partenariat(Leads)", "") or "SAJ Job",
        "Date du premier contact":     prospect.get("Date du premier contact", ""),
        "Localisation":                prospect.get("Localisation", "") or prospect.get("Ville", ""),
        "Canal de contact":            prospect.get("Canal de contact", "") or "Appel",
        "Statut":                      prospect.get("Statut", "") or "À contacter",
        "Prochain Action":             prospect.get("Prochain Action", ""),
        "Remarque":                    remarque,
    }
    return row


# ─── Export session ───────────────────────────────────────────────────────────

def create_session_filename() -> str:
    return f"session_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"


def export_session_csv(prospects: List[Dict], session_file: Optional[str] = None) -> Path:
    """
    Exporte dans un fichier de session séparé + le fichier consolidé.
    Les prospects doivent déjà être scorés et triés.
    """
    ensure_data_dir()
    rows = [_normalize_prospect(p) for p in prospects]
    new_df = pd.DataFrame(rows, columns=CSV_COLUMNS)

    if not session_file:
        session_file = create_session_filename()
    session_path = SESSIONS_DIR / session_file

    # Fichier de session (nouveau)
    new_df.to_csv(session_path, index=False, encoding="utf-8-sig")

    # Fichier consolidé (append)
    if PROSPECTS_FILE.exists() and PROSPECTS_FILE.stat().st_size > 0:
        try:
            existing_df = pd.read_csv(PROSPECTS_FILE, encoding="utf-8-sig", dtype=str)
            for col in CSV_COLUMNS:
                if col not in existing_df.columns:
                    existing_df[col] = ""
            combined_df = pd.concat(
                [existing_df[CSV_COLUMNS], new_df], ignore_index=True
            )
        except pd.errors.EmptyDataError:
            combined_df = new_df
    else:
        combined_df = new_df

    combined_df.to_csv(PROSPECTS_FILE, index=False, encoding="utf-8-sig")
    return session_path


def export_prospects_csv(
    prospects: List[Dict], filepath: Path = PROSPECTS_FILE
) -> Path:
    """Ajoute les prospects au CSV (crée si nécessaire)."""
    ensure_data_dir()
    rows = [_normalize_prospect(p) for p in prospects]
    new_df = pd.DataFrame(rows, columns=CSV_COLUMNS)

    if filepath.exists() and filepath.stat().st_size > 0:
        try:
            existing_df = pd.read_csv(filepath, encoding="utf-8-sig", dtype=str)
            for col in CSV_COLUMNS:
                if col not in existing_df.columns:
                    existing_df[col] = ""
            combined_df = pd.concat(
                [existing_df[CSV_COLUMNS], new_df], ignore_index=True
            )
        except pd.errors.EmptyDataError:
            combined_df = new_df
    else:
        combined_df = new_df

    combined_df.to_csv(filepath, index=False, encoding="utf-8-sig")
    return filepath


def export_doublons_csv(
    doublons: List[Dict], filepath: Path = DOUBLONS_FILE
) -> Path:
    return export_prospects_csv(doublons, filepath=filepath)


# ─── Lecture ──────────────────────────────────────────────────────────────────

def list_sessions() -> List[Dict]:
    """Liste toutes les sessions (plus récente en premier)."""
    ensure_data_dir()
    sessions = []
    for f in sorted(SESSIONS_DIR.glob("session_*.csv"), reverse=True):
        stem = f.stem
        try:
            parts = stem.replace("session_", "")
            dt = datetime.strptime(parts, "%Y%m%d_%H%M")
            date_str = dt.strftime("%d/%m/%Y %H:%M")
        except ValueError:
            date_str = stem
        try:
            df = pd.read_csv(f, encoding="utf-8-sig", dtype=str)
            count = len(df)
        except Exception:
            count = 0
        sessions.append({
            "filename": f.name,
            "date": date_str,
            "count": count,
            "path": f,
        })
    return sessions


def read_session_df(session_path: Path) -> pd.DataFrame:
    """Lit un fichier de session."""
    if not session_path.exists() or session_path.stat().st_size == 0:
        return pd.DataFrame(columns=CSV_COLUMNS)
    try:
        df = pd.read_csv(session_path, encoding="utf-8-sig", dtype=str)
        for col in CSV_COLUMNS:
            if col not in df.columns:
                df[col] = ""
        return df[CSV_COLUMNS]
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=CSV_COLUMNS)


def read_prospects_df(filepath: Path = PROSPECTS_FILE) -> pd.DataFrame:
    """Lit le CSV consolidé."""
    if not filepath.exists() or filepath.stat().st_size == 0:
        return pd.DataFrame(columns=CSV_COLUMNS)
    try:
        df = pd.read_csv(filepath, encoding="utf-8-sig", dtype=str)
        for col in CSV_COLUMNS:
            if col not in df.columns:
                df[col] = ""
        return df[CSV_COLUMNS]
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=CSV_COLUMNS)


def clear_prospects(backup: bool = True) -> bool:
    """Vide tout (consolidé + sessions). Sauvegarde optionnelle."""
    try:
        if PROSPECTS_FILE.exists() and backup:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = DATA_DIR / f"prospects_CDE_backup_{ts}.csv"
            PROSPECTS_FILE.rename(backup_path)
        elif PROSPECTS_FILE.exists():
            PROSPECTS_FILE.unlink()

        if DOUBLONS_FILE.exists():
            DOUBLONS_FILE.unlink()

        for f in SESSIONS_DIR.glob("session_*.csv"):
            if backup:
                backup_dir = DATA_DIR / "backups"
                backup_dir.mkdir(exist_ok=True)
                f.rename(backup_dir / f.name)
            else:
                f.unlink()

        return True
    except Exception:
        return False


def generate_summary_stats(df: pd.DataFrame) -> Dict:
    """Stats de synthèse."""
    if df.empty:
        return {"total": 0, "by_canal": {}, "by_type_offre": {}, "by_ville": {}, "avg_score": 0}

    avg_score = 0
    if "SCORE" in df.columns:
        scores = pd.to_numeric(df["SCORE"], errors="coerce")
        avg_score = round(scores.mean(), 1) if not scores.isna().all() else 0

    return {
        "total": len(df),
        "by_canal": df["Canal de contact"].value_counts().to_dict()
        if "Canal de contact" in df.columns else {},
        "by_type_offre": df["Type de partenariat(Leads)"].value_counts().to_dict()
        if "Type de partenariat(Leads)" in df.columns else {},
        "by_ville": df["Localisation"].value_counts().head(10).to_dict()
        if "Localisation" in df.columns else {},
        "avg_score": avg_score,
    }
