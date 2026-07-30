"""
utils/residence_exporter.py — Export CSV des résidences étudiantes privées.

Architecture par session (comme les jobs) :
    Chaque scraping → data/residences_sessions/session_YYYYMMDD_HHMM.csv
    Consolidé → data/residences_CDE.csv
    Doublons → data/residences_doublons_CDE.csv

Pas de téléphone (demande explicite) : Lien, Instagram, Email uniquement.
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

DATA_DIR = Path("data")
RESIDENCE_SESSIONS_DIR = DATA_DIR / "residences_sessions"
RESIDENCE_PROSPECTS_FILE = DATA_DIR / "residences_CDE.csv"
RESIDENCE_DOUBLONS_FILE = DATA_DIR / "residences_doublons_CDE.csv"

RESIDENCE_CSV_COLUMNS = [
    "Semaine",
    "Membre responsable",
    "Nom résidence",
    "Gestionnaire",
    "Lien",
    "Instagram",
    "Email",
    "Adresse",
    "Ville",
    "Département",
    "Région",
    "Canal de contact",
    "Statut",
    "Date premier contact",
    "Prochaine action",
    "Remarque",
]


def ensure_data_dir():
    DATA_DIR.mkdir(exist_ok=True)
    RESIDENCE_SESSIONS_DIR.mkdir(exist_ok=True)


def _normalize_residence(r: Dict) -> Dict:
    return {
        "Semaine":              r.get("Semaine", ""),
        "Membre responsable":   r.get("Membre responsable", ""),
        "Nom résidence":        r.get("Nom résidence", ""),
        "Gestionnaire":         r.get("Gestionnaire", ""),
        "Lien":                 r.get("Lien", ""),
        "Instagram":            r.get("Instagram", ""),
        "Email":                r.get("Email", ""),
        "Adresse":              r.get("Adresse", ""),
        "Ville":                r.get("Ville", ""),
        "Département":          r.get("Département", ""),
        "Région":               r.get("Région", ""),
        "Canal de contact":     r.get("Canal de contact", "") or "Email",
        "Statut":               r.get("Statut", "") or "À contacter",
        "Date premier contact": r.get("Date premier contact", ""),
        "Prochaine action":     r.get("Prochaine action", ""),
        "Remarque":             r.get("Remarque", "") or r.get("Notes", ""),
    }


def create_session_filename() -> str:
    return f"session_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"


def export_session_csv(residences: List[Dict], session_file: Optional[str] = None) -> Path:
    ensure_data_dir()
    rows = [_normalize_residence(r) for r in residences]
    new_df = pd.DataFrame(rows, columns=RESIDENCE_CSV_COLUMNS)

    if not session_file:
        session_file = create_session_filename()
    session_path = RESIDENCE_SESSIONS_DIR / session_file
    new_df.to_csv(session_path, index=False, encoding="utf-8-sig")

    if RESIDENCE_PROSPECTS_FILE.exists() and RESIDENCE_PROSPECTS_FILE.stat().st_size > 0:
        try:
            existing_df = pd.read_csv(RESIDENCE_PROSPECTS_FILE, encoding="utf-8-sig", dtype=str)
            for col in RESIDENCE_CSV_COLUMNS:
                if col not in existing_df.columns:
                    existing_df[col] = ""
            combined_df = pd.concat([existing_df[RESIDENCE_CSV_COLUMNS], new_df], ignore_index=True)
        except pd.errors.EmptyDataError:
            combined_df = new_df
    else:
        combined_df = new_df

    combined_df.to_csv(RESIDENCE_PROSPECTS_FILE, index=False, encoding="utf-8-sig")
    return session_path


def export_doublons_csv(doublons: List[Dict]) -> Path:
    ensure_data_dir()
    rows = [_normalize_residence(r) for r in doublons]
    new_df = pd.DataFrame(rows, columns=RESIDENCE_CSV_COLUMNS)

    if RESIDENCE_DOUBLONS_FILE.exists() and RESIDENCE_DOUBLONS_FILE.stat().st_size > 0:
        try:
            existing_df = pd.read_csv(RESIDENCE_DOUBLONS_FILE, encoding="utf-8-sig", dtype=str)
            for col in RESIDENCE_CSV_COLUMNS:
                if col not in existing_df.columns:
                    existing_df[col] = ""
            combined_df = pd.concat([existing_df[RESIDENCE_CSV_COLUMNS], new_df], ignore_index=True)
        except pd.errors.EmptyDataError:
            combined_df = new_df
    else:
        combined_df = new_df

    combined_df.to_csv(RESIDENCE_DOUBLONS_FILE, index=False, encoding="utf-8-sig")
    return RESIDENCE_DOUBLONS_FILE


def list_sessions() -> List[Dict]:
    ensure_data_dir()
    sessions = []
    for f in sorted(RESIDENCE_SESSIONS_DIR.glob("session_*.csv"), reverse=True):
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
        sessions.append({"filename": f.name, "date": date_str, "count": count, "path": f})
    return sessions


def read_session_df(session_path: Path) -> pd.DataFrame:
    if not session_path.exists() or session_path.stat().st_size == 0:
        return pd.DataFrame(columns=RESIDENCE_CSV_COLUMNS)
    try:
        df = pd.read_csv(session_path, encoding="utf-8-sig", dtype=str)
        for col in RESIDENCE_CSV_COLUMNS:
            if col not in df.columns:
                df[col] = ""
        return df[RESIDENCE_CSV_COLUMNS]
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=RESIDENCE_CSV_COLUMNS)


def read_prospects_df(filepath: Path = RESIDENCE_PROSPECTS_FILE) -> pd.DataFrame:
    if not filepath.exists() or filepath.stat().st_size == 0:
        return pd.DataFrame(columns=RESIDENCE_CSV_COLUMNS)
    try:
        df = pd.read_csv(filepath, encoding="utf-8-sig", dtype=str)
        for col in RESIDENCE_CSV_COLUMNS:
            if col not in df.columns:
                df[col] = ""
        return df[RESIDENCE_CSV_COLUMNS]
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=RESIDENCE_CSV_COLUMNS)


def clear_residences(backup: bool = True) -> bool:
    try:
        if RESIDENCE_PROSPECTS_FILE.exists() and backup:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = DATA_DIR / f"residences_CDE_backup_{ts}.csv"
            RESIDENCE_PROSPECTS_FILE.rename(backup_path)
        elif RESIDENCE_PROSPECTS_FILE.exists():
            RESIDENCE_PROSPECTS_FILE.unlink()

        if RESIDENCE_DOUBLONS_FILE.exists():
            RESIDENCE_DOUBLONS_FILE.unlink()

        for f in RESIDENCE_SESSIONS_DIR.glob("session_*.csv"):
            if backup:
                backup_dir = DATA_DIR / "backups"
                backup_dir.mkdir(exist_ok=True)
                f.rename(backup_dir / f.name)
            else:
                f.unlink()
        return True
    except Exception:
        return False


def group_chain_residences(residences: List[Dict]) -> List[Dict]:
    """
    Regroupe les résidences d'un même gestionnaire national en UNE seule ligne
    de contact (même Instagram/site/email pour toutes leurs résidences —
    inutile de contacter 7 fois le même compte).

    Les résidences indépendantes (sans gestionnaire détecté) restent
    inchangées, une ligne chacune.
    """
    from collections import defaultdict

    grouped_by_chain = defaultdict(list)
    independents = []

    for r in residences:
        gest = (r.get("Gestionnaire") or "").strip()
        if gest:
            grouped_by_chain[gest].append(r)
        else:
            independents.append(r)

    result = list(independents)

    for gest, items in grouped_by_chain.items():
        first = items[0]
        villes = sorted({i.get("Ville", "") for i in items if i.get("Ville")})
        villes_str = ", ".join(villes[:5])
        if len(villes) > 5:
            villes_str += f" +{len(villes) - 5} autres"

        depts = {i.get("Département", "") for i in items}
        regions = {i.get("Région", "") for i in items}

        details = [
            f"{i.get('Nom résidence', '')} ({i.get('Ville', '')})" for i in items
        ]

        result.append({
            "Nom résidence": gest,
            "Gestionnaire": gest,
            "Lien": first.get("Lien", ""),
            "Instagram": first.get("Instagram", ""),
            "Email": first.get("Email", ""),
            "Adresse": "",
            "Ville": villes_str,
            "Département": next(iter(depts)) if len(depts) == 1 else "",
            "Région": next(iter(regions)) if len(regions) == 1 else "",
            "Statut": "À contacter",
            "Canal de contact": first.get("Canal de contact", "Email"),
            "Remarque": f"{len(items)} résidences trouvées : " + " | ".join(details),
        })

    return result


def generate_summary_stats(df: pd.DataFrame) -> Dict:
    if df.empty:
        return {"total": 0, "by_gestionnaire": {}, "by_region": {}, "with_email": 0, "with_instagram": 0}

    return {
        "total": len(df),
        "by_gestionnaire": df["Gestionnaire"].replace("", "Indépendant").value_counts().to_dict()
        if "Gestionnaire" in df.columns else {},
        "by_region": df["Région"].value_counts().to_dict() if "Région" in df.columns else {},
        "with_email": int((df["Email"].fillna("") != "").sum()) if "Email" in df.columns else 0,
        "with_instagram": int((df["Instagram"].fillna("") != "").sum()) if "Instagram" in df.columns else 0,
    }
