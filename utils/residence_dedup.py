"""
utils/residence_dedup.py — Déduplication cross-session des résidences étudiantes.

Clé de dédup : normalize(Nom résidence) + "|" + normalize(Ville)
"""

import re
from pathlib import Path
from typing import Dict, Literal, Optional, Set, Tuple

import pandas as pd

from .residence_exporter import (
    RESIDENCE_DOUBLONS_FILE,
    RESIDENCE_PROSPECTS_FILE,
    RESIDENCE_SESSIONS_DIR,
    ensure_data_dir,
    export_doublons_csv,
    export_session_csv,
)


def normalize_field(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return re.sub(r"[\s\-\.\(\)/']", "", str(value).lower().strip())


def make_residence_key(row: Dict) -> str:
    gest = normalize_field(row.get("Gestionnaire", ""))
    if gest:
        # Une chaîne nationale = une seule clé stable, peu importe le nombre
        # de résidences regroupées dessous (même contact partout).
        return f"chain|{gest}"
    name = normalize_field(row.get("Nom résidence", ""))
    city = normalize_field(row.get("Ville", ""))
    return f"{name}|{city}"


class ResidenceDedupManager:
    """Déduplication persistante entre sessions de scraping résidences."""

    def __init__(self):
        ensure_data_dir()
        self.known_keys: Set[str] = set()
        self.session_new: list = []
        self.session_dupes: list = []
        self._session_file: Optional[str] = None

        self.known_keys.update(self._load_keys_from_file(RESIDENCE_PROSPECTS_FILE))
        self.known_keys.update(self._load_keys_from_file(RESIDENCE_DOUBLONS_FILE))
        for f in RESIDENCE_SESSIONS_DIR.glob("session_*.csv"):
            self.known_keys.update(self._load_keys_from_file(f))

    def _load_keys_from_file(self, filepath: Path) -> Set[str]:
        if not filepath.exists() or filepath.stat().st_size == 0:
            return set()
        try:
            df = pd.read_csv(filepath, encoding="utf-8-sig", dtype=str)
            return {make_residence_key(row.to_dict()) for _, row in df.iterrows()}
        except Exception:
            return set()

    def check_and_register(self, residence: Dict) -> Literal["new", "duplicate"]:
        key = make_residence_key(residence)
        if key in self.known_keys:
            self.session_dupes.append(residence)
            return "duplicate"
        self.known_keys.add(key)
        self.session_new.append(residence)
        return "new"

    def flush_to_disk(self, session_file: Optional[str] = None) -> Tuple[int, int]:
        new_count = len(self.session_new)
        dupe_count = len(self.session_dupes)

        if self.session_new:
            path = export_session_csv(self.session_new, session_file=session_file)
            self._session_file = path.name

        if self.session_dupes:
            export_doublons_csv(self.session_dupes)

        self.session_new.clear()
        self.session_dupes.clear()
        return new_count, dupe_count

    @property
    def last_session_file(self) -> Optional[str]:
        return self._session_file

    def get_stats(self) -> Dict:
        return {
            "total_known": len(self.known_keys),
            "session_new": len(self.session_new),
            "session_dupes": len(self.session_dupes),
        }
