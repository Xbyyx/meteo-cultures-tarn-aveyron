"""Création de la base SQLite db/meteo_cultures.sqlite.

Supprime l'ancienne base si elle existe, applique schema.sql puis remplit
culture_ref avec les cultures suivies. Libellés repris du référentiel officiel de l'IGN :
https://data.geopf.fr/annexes/ressources/documentation/REF_CULTURES_GROUPES_CULTURES_2024.csv

Exemple : python src/chargement/creer_base.py
"""

import sqlite3
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
CHEMIN_BASE = RACINE / "db" / "meteo_cultures.sqlite"
SCHEMA = Path(__file__).resolve().parent / "schema.sql"

# (code, libellé du référentiel IGN, nom court)
CULTURES = [
    ("BTH", "Blé tendre d’hiver", "Blé tendre"),
    ("BTP", "Blé tendre de printemps", "Blé tendre"),
    ("MIS", "Maïs (hors maïs doux)", "Maïs"),
    ("MID", "Maïs doux", "Maïs"),
    ("TRN", "Tournesol", "Tournesol"),
    ("SGH", "Seigle d’hiver", "Seigle"),
    ("SGP", "Seigle de printemps", "Seigle"),
    ("PPH", "Prairie de 6 ans ou plus (couvert herbacé)", "Prairies"),
    ("PTR", "Prairie temporaire de moins de 5 ans et autre mélange avec graminées", "Prairies"),
]


def ouvrir_base():
    """Ouvre la base existante avec les clés étrangères activées."""
    connexion = sqlite3.connect(CHEMIN_BASE)
    connexion.execute("PRAGMA foreign_keys = ON")
    return connexion


def creer_base():
    CHEMIN_BASE.parent.mkdir(parents=True, exist_ok=True)
    CHEMIN_BASE.unlink(missing_ok=True)
    connexion = ouvrir_base()
    with connexion:
        connexion.executescript(SCHEMA.read_text(encoding="utf-8"))
        connexion.executemany("INSERT INTO culture_ref (code_culture, libelle, culture) VALUES (?, ?, ?)", CULTURES)
    connexion.close()
    print(f"Base créée : {CHEMIN_BASE} ({len(CULTURES)} cultures dans culture_ref)")


if __name__ == "__main__":
    creer_base()
