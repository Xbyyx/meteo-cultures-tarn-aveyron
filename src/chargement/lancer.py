"""Reconstruit toute la base db/meteo_cultures.sqlite.

Enchaîne la création de la base, le chargement de la météo et des surfaces,
puis l'application de vues.sql, et affiche le nombre de lignes de chaque
table et de chaque vue. La base est recréée à chaque lancement : le résultat
est identique d'un lancement à l'autre.

Exemple : python src/chargement/lancer.py
"""

from pathlib import Path

from charger_meteo import charger_meteo
from charger_surfaces import charger_surfaces
from creer_base import creer_base, ouvrir_base

VUES = Path(__file__).resolve().parent / "vues.sql"


def compter_lignes(connexion):
    objets = connexion.execute(
        "SELECT type, name FROM sqlite_master WHERE type IN ('table', 'view') "
        "AND name NOT LIKE 'sqlite_%' ORDER BY type DESC, name").fetchall()
    for type_, nom in objets:
        nombre = connexion.execute(f'SELECT COUNT(*) FROM "{nom}"').fetchone()[0]
        print(f"  {'table' if type_ == 'table' else 'vue  '} {nom:<20} {nombre:>8} lignes")


def main():
    creer_base()
    charger_meteo()
    charger_surfaces()
    connexion = ouvrir_base()
    with connexion:
        connexion.executescript(VUES.read_text(encoding="utf-8"))
    print("Vues appliquées. Nombre de lignes :")
    compter_lignes(connexion)
    connexion.close()


if __name__ == "__main__":
    main()
