"""Chargement des données météo quotidiennes dans station et meteo_jour.

Lit data/raw/meteo/Q_<dep>_*.csv.gz (départements 12 et 81, séparateur
point-virgule, UTF-8), ne garde que les dates du 2022-01-01 au 2024-12-31,
convertit AAAAMMJJ en AAAA-MM-JJ et charge une ligne par poste ayant au moins
une mesure sur la période. Les codes qualité sont conservés tels quels, aucune
mesure n'est supprimée ; les valeurs vides deviennent NULL. Remplit aussi
source_fichier d'après data/raw/meteo/manifest.csv.

Exemple : python src/chargement/charger_meteo.py
"""

import csv
import gzip
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingestion"))
from creer_base import RACINE, ouvrir_base  # noqa: E402
from download_meteo import DEPARTEMENTS, URL_MODELE  # noqa: E402

DOSSIER_METEO = RACINE / "data" / "raw" / "meteo"
DEBUT, FIN = "20220101", "20241231"


def nombre(texte):
    """Valeur vide -> None, sinon nombre décimal."""
    return float(texte) if texte.strip() else None


def qualite(texte):
    """Code qualité vide -> None, sinon le code tel quel."""
    return texte.strip() or None


def date_iso(texte):
    return f"{texte[:4]}-{texte[4:6]}-{texte[6:]}"


def lire_fichier(chemin, departement):
    """Renvoie (stations, mesures) du fichier pour la période retenue."""
    stations, mesures = {}, []
    with gzip.open(chemin, "rt", encoding="utf-8", newline="") as fichier:
        for ligne in csv.DictReader(fichier, delimiter=";"):
            if not DEBUT <= ligne["AAAAMMJJ"] <= FIN:
                continue
            poste = ligne["NUM_POSTE"]
            if poste[:2] != departement:
                raise ValueError(f"Poste {poste} hors du département {departement} dans {chemin.name}")
            stations[poste] = (poste, ligne["NOM_USUEL"], departement, nombre(ligne["LAT"]),
                               nombre(ligne["LON"]), nombre(ligne["ALTI"]))
            mesures.append((poste, date_iso(ligne["AAAAMMJJ"]),
                            nombre(ligne["RR"]), nombre(ligne["TN"]), nombre(ligne["TX"]),
                            qualite(ligne["QRR"]), qualite(ligne["QTN"]), qualite(ligne["QTX"])))
    return stations, mesures


def charger_meteo():
    connexion = ouvrir_base()
    with connexion:
        for departement in DEPARTEMENTS:
            chemins = sorted(DOSSIER_METEO.glob(f"Q_{departement}_*.csv.gz"))
            if len(chemins) != 1:
                sys.exit(f"{len(chemins)} fichier(s) météo pour le département {departement} : {chemins}")
            stations, mesures = lire_fichier(chemins[0], departement)
            connexion.executemany("INSERT INTO station VALUES (?, ?, ?, ?, ?, ?)", stations.values())
            connexion.executemany("INSERT INTO meteo_jour VALUES (?, ?, ?, ?, ?, ?, ?, ?)", mesures)
            print(f"Département {departement} : {len(stations)} stations, {len(mesures)} mesures")

        with open(DOSSIER_METEO / "manifest.csv", newline="", encoding="utf-8") as fichier:
            for ligne in csv.DictReader(fichier):
                departement = ligne["nom"].split("_")[1]
                connexion.execute("INSERT INTO source_fichier VALUES (?, ?, ?, ?)",
                                  (ligne["nom"], URL_MODELE.format(dep=departement),
                                   ligne["date_telechargement"], ligne["sha256"]))
    connexion.close()


if __name__ == "__main__":
    charger_meteo()
