"""Téléchargement des données climatologiques quotidiennes de Météo-France.

Pour chaque département ciblé, télécharge le fichier CSV compressé
(périodes antérieures, paramètres RR-T-Vent) dans data/raw/meteo/ et
tient à jour un manifeste data/raw/meteo/manifest.csv.
"""

import csv
import hashlib
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEPARTEMENTS = ["12", "81"]
URL_MODELE = (
    "https://meteofrance.s3.sbg.io.cloud.ovh.net/data/synchro_ftp/BASE/QUOT/"
    "Q_{dep}_previous-1950-2024_RR-T-Vent.csv.gz"
)
DOSSIER_SORTIE = Path(__file__).resolve().parents[2] / "data" / "raw" / "meteo"
MANIFESTE = DOSSIER_SORTIE / "manifest.csv"
CHAMPS_MANIFESTE = ["nom", "taille", "date_telechargement", "sha256"]
TAILLE_BLOC = 1024 * 1024


def telecharger(url, destination):
    """Télécharge url vers destination et renvoie l'empreinte SHA-256 et la taille."""
    empreinte = hashlib.sha256()
    taille = 0
    with urllib.request.urlopen(url, timeout=120) as reponse, open(destination, "wb") as sortie:
        while True:
            bloc = reponse.read(TAILLE_BLOC)
            if not bloc:
                break
            sortie.write(bloc)
            empreinte.update(bloc)
            taille += len(bloc)
    return empreinte.hexdigest(), taille


def main():
    DOSSIER_SORTIE.mkdir(parents=True, exist_ok=True)
    lignes = []

    for dep in DEPARTEMENTS:
        url = URL_MODELE.format(dep=dep)
        nom = url.rsplit("/", 1)[-1]
        destination = DOSSIER_SORTIE / nom
        print(f"Téléchargement de {nom} ...")
        try:
            sha256, taille = telecharger(url, destination)
        except urllib.error.HTTPError as erreur:
            destination.unlink(missing_ok=True)
            if erreur.code == 404:
                print(f"  Fichier introuvable (404) pour le département {dep} : {url}")
            else:
                print(f"  Erreur HTTP {erreur.code} pour le département {dep} : {url}")
            continue
        except urllib.error.URLError as erreur:
            destination.unlink(missing_ok=True)
            print(f"  Échec de connexion pour le département {dep} : {erreur.reason}")
            continue

        lignes.append(
            {
                "nom": nom,
                "taille": taille,
                "date_telechargement": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "sha256": sha256,
            }
        )
        print(f"  OK ({taille} octets)")

    if lignes:
        with open(MANIFESTE, "w", newline="", encoding="utf-8") as fichier:
            ecrivain = csv.DictWriter(fichier, fieldnames=CHAMPS_MANIFESTE)
            ecrivain.writeheader()
            ecrivain.writerows(lignes)
        print(f"Manifeste écrit : {MANIFESTE}")
    else:
        print("Aucun fichier téléchargé, manifeste non modifié.")


if __name__ == "__main__":
    main()
