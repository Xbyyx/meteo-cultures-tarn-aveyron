"""Chargement de data/processed/surface_culture.csv dans surface_culture.

Si le fichier n'existe pas, affiche un message et ne fait rien. Sinon charge
aussi source_fichier avec les manifest.csv du RPG et des limites
départementales, dont sont issues les surfaces.

Exemple : python src/chargement/charger_surfaces.py
"""

import csv

from creer_base import RACINE, ouvrir_base

FICHIER = RACINE / "data" / "processed" / "surface_culture.csv"
MANIFESTES = [RACINE / "data" / "raw" / "rpg" / "manifest.csv", RACINE / "data" / "raw" / "admin" / "manifest.csv"]
URL_RPG = "https://data.geopf.fr/telechargement/download/RPG/{titre}/{nom}"
URL_LIMITES = "https://data.geopf.fr/wfs/ows (couche ADMINEXPRESS-COG.LATEST:departement, code_insee 12 et 81)"


def url_source(nom):
    """URL connue d'un fichier du manifeste, sinon None (fichiers extraits d'une archive)."""
    if nom.endswith((".7z", ".7z.001")):
        return URL_RPG.format(titre=nom.split(".7z")[0], nom=nom)
    if nom.startswith("limites_departements"):
        return URL_LIMITES
    return None


def charger_surfaces():
    if not FICHIER.exists():
        print(f"{FICHIER} absent : aucune surface chargée (lancez src/nettoyage/filtrer_departements.py).")
        return
    with open(FICHIER, newline="", encoding="utf-8") as fichier:
        lignes = [(int(l["campagne"]), l["departement"], l["code_culture"],
                   int(l["nb_parcelles"]), float(l["surface_ha"])) for l in csv.DictReader(fichier)]
    connexion = ouvrir_base()
    with connexion:
        connexion.executemany("INSERT INTO surface_culture VALUES (?, ?, ?, ?, ?)", lignes)
        for manifeste in MANIFESTES:
            with open(manifeste, newline="", encoding="utf-8") as fichier:
                for l in csv.DictReader(fichier):
                    connexion.execute("INSERT INTO source_fichier VALUES (?, ?, ?, ?)",
                                      (l["nom"], url_source(l["nom"]), l["date_telechargement"], l["sha256"]))
    connexion.close()
    print(f"{len(lignes)} lignes chargées dans surface_culture")


if __name__ == "__main__":
    charger_surfaces()
