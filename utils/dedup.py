"""
utils/dedup.py — Détection et gestion des doublons (cross-session, cross-fichiers).

La clé de déduplication est :
    normalize(Entreprise) + "|" + normalize(Ville) + "|" + normalize_phone(Téléphone)

Le DedupManager charge les clés connues depuis TOUS les fichiers de session
(data/sessions/session_*.csv) + le fichier consolidé + le fichier doublons.
Cela garantit qu'aucun doublon n'existe entre les fichiers.
"""

import re
from pathlib import Path
from typing import Dict, Literal, Optional, Set, Tuple

import pandas as pd

from .exporter import (
    DOUBLONS_FILE,
    PROSPECTS_FILE,
    SESSIONS_DIR,
    ensure_data_dir,
    export_doublons_csv,
    export_session_csv,
)


def normalize_field(value) -> str:
    """Lowercase, strip, supprime espaces/tirets/points/parenthèses."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return re.sub(r"[\s\-\.\(\)/]", "", str(value).lower().strip())


def normalize_phone(value) -> str:
    """Garde uniquement les chiffres, retourne les 10 derniers (gère +33)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    digits = re.sub(r"\D", "", str(value))
    return digits[-10:] if len(digits) >= 10 else digits


def make_dedup_key(row: Dict) -> str:
    """Construit la clé de déduplication à partir d'un dict prospect."""
    name = normalize_field(row.get("Entreprise", ""))
    city = normalize_field(row.get("Ville", "") or row.get("Localisation", ""))
    phone = normalize_phone(row.get("Téléphone", "") or row.get("Contact", ""))
    return f"{name}|{city}|{phone}"


class DedupManager:
    """
    Gère la déduplication des prospects de façon persistante entre sessions.
    Charge les clés depuis TOUS les fichiers (sessions + consolidé + doublons).
    """

    def __init__(self):
        ensure_data_dir()
        self.known_keys: Set[str] = set()
        self.session_new: list = []
        self.session_dupes: list = []
        self._session_file: Optional[str] = None

        # Charger les clés depuis le fichier consolidé
        self.known_keys.update(self._load_keys_from_file(PROSPECTS_FILE))
        # Charger depuis le fichier doublons
        self.known_keys.update(self._load_keys_from_file(DOUBLONS_FILE))
        # Charger depuis TOUS les fichiers de session
        for f in SESSIONS_DIR.glob("session_*.csv"):
            self.known_keys.update(self._load_keys_from_file(f))

    def _load_keys_from_file(self, filepath: Path) -> Set[str]:
        """Lit un CSV et retourne l'ensemble des clés de déduplication."""
        if not filepath.exists() or filepath.stat().st_size == 0:
            return set()
        try:
            df = pd.read_csv(filepath, encoding="utf-8-sig", dtype=str)
            keys = set()
            for _, row in df.iterrows():
                keys.add(make_dedup_key(row.to_dict()))
            return keys
        except Exception:
            return set()

    def check_and_register(self, prospect: Dict) -> Literal["new", "duplicate"]:
        """
        Vérifie si le prospect est un doublon (cross-fichiers).
        - Si nouveau : l'ajoute à session_new + known_keys
        - Si doublon : l'ajoute à session_dupes
        """
        key = make_dedup_key(prospect)
        if key in self.known_keys:
            self.session_dupes.append(prospect)
            return "duplicate"
        else:
            self.known_keys.add(key)
            self.session_new.append(prospect)
            return "new"

    def flush_to_disk(self, session_file: Optional[str] = None) -> Tuple[int, int]:
        """
        Écrit les nouveaux prospects dans un fichier de session séparé.
        Écrit les doublons dans doublons_CDE.csv.
        Retourne (nb_nouveaux, nb_doublons).
        """
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
        """Retourne le nom du dernier fichier de session créé."""
        return self._session_file

    def get_stats(self) -> Dict:
        return {
            "total_known": len(self.known_keys),
            "session_new": len(self.session_new),
            "session_dupes": len(self.session_dupes),
        }
