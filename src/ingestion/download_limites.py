"""Téléchargement des limites départementales du Tarn (81) et de l'Aveyron (12).

Source : produit ADMIN EXPRESS de l'IGN (Licence Ouverte), service WFS de la
Géoplateforme (data.geopf.fr), couche ADMINEXPRESS-COG.LATEST:departement.
Le filtre CQL sur code_insee est appliqué côté serveur : seuls les deux
départements sont transférés, jamais la France entière. Le service renvoie
directement les géométries en Lambert-93 (EPSG:2154), le système du RPG.

Écrit data/raw/admin/limites_departements_12_81.geojson, met à jour
data/raw/admin/manifest.csv puis affiche la couche, le système de
coordonnées et les colonnes.

Exemple : python src/ingestion/download_limites.py
"""

import csv
import hashlib
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pyogrio

from list_rpg import USER_AGENT

URL_WFS = "https://data.geopf.fr/wfs/ows"
COUCHE = "ADMINEXPRESS-COG.LATEST:departement"
SRS = "EPSG:2154"
DEPARTEMENTS = ("12", "81")
DOSSIER_SORTIE = Path(__file__).resolve().parents[2] / "data" / "raw" / "admin"
FICHIER = DOSSIER_SORTIE / "limites_departements_12_81.geojson"
MANIFESTE = DOSSIER_SORTIE / "manifest.csv"
CHAMPS_MANIFESTE = ["nom", "taille", "date_telechargement", "sha256"]
TAILLE_MAX = 50 * 1000**2  # garde-fou : on s'arrête au-delà de 50 Mo (attendu : environ 1,4 Mo)
TAILLE_BLOC = 1024 * 1024


def construire_url(**extra):
    filtre = "code_insee IN ({})".format(",".join(f"'{code}'" for code in DEPARTEMENTS))
    parametres = {
        "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
        "TYPENAMES": COUCHE, "CQL_FILTER": filtre, "SRSNAME": SRS, **extra,
    }
    return f"{URL_WFS}?{urllib.parse.urlencode(parametres, quote_via=urllib.parse.quote)}"


def ouvrir(url):
    requete = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(requete, timeout=120)


def compter_entites():
    """Nombre d'entités renvoyées par le filtre (requête resultType=hits, quelques octets)."""
    with ouvrir(construire_url(resultType="hits")) as reponse:
        entete = reponse.read(4096).decode("utf-8", "replace")
    trouve = re.search(r'numberMatched="(\d+)"', entete)
    if not trouve:
        raise RuntimeError("Nombre d'entités introuvable dans la réponse du service")
    return int(trouve.group(1))


def telecharger(destination):
    """Télécharge la couche filtrée en GeoJSON, en s'arrêtant si elle dépasse TAILLE_MAX."""
    partiel = destination.with_name(destination.name + ".part")
    recu = 0
    with ouvrir(construire_url(outputFormat="application/json")) as reponse, open(partiel, "wb") as sortie:
        annonce = reponse.headers.get("Content-Length")
        if annonce and int(annonce) > TAILLE_MAX:
            sys.exit(f"Taille annoncée {annonce} octets supérieure au garde-fou : arrêt.")
        for bloc in iter(lambda: reponse.read(TAILLE_BLOC), b""):
            recu += len(bloc)
            if recu > TAILLE_MAX:
                sys.exit("Téléchargement supérieur au garde-fou de taille : arrêt.")
            sortie.write(bloc)
    partiel.replace(destination)


def sha256_fichier(chemin):
    empreinte = hashlib.sha256()
    with open(chemin, "rb") as fichier:
        for bloc in iter(lambda: fichier.read(TAILLE_BLOC), b""):
            empreinte.update(bloc)
    return empreinte.hexdigest()


def mettre_a_jour_manifeste(ligne):
    """Ajoute ou remplace la ligne du manifeste, indexée par nom."""
    existantes = {}
    if MANIFESTE.exists():
        with open(MANIFESTE, newline="", encoding="utf-8") as fichier:
            existantes = {l["nom"]: l for l in csv.DictReader(fichier)}
    existantes[ligne["nom"]] = ligne
    with open(MANIFESTE, "w", newline="", encoding="utf-8") as fichier:
        ecrivain = csv.DictWriter(fichier, fieldnames=CHAMPS_MANIFESTE)
        ecrivain.writeheader()
        ecrivain.writerows(existantes.values())


def afficher_couche(chemin):
    info = pyogrio.read_info(chemin)
    print(f"Couche : {COUCHE} ({info['features']} entités, géométrie {info['geometry_type']})")
    print(f"Système de coordonnées : {info['crs']}")
    print(f"Colonnes : {', '.join(info['fields'])}")
    print(pyogrio.read_dataframe(chemin, read_geometry=False).to_string(index=False))


def main():
    nombre = compter_entites()
    print(f"Entités correspondant au filtre {DEPARTEMENTS} : {nombre}")
    if nombre != len(DEPARTEMENTS):
        sys.exit(f"{len(DEPARTEMENTS)} départements attendus, {nombre} trouvés : arrêt.")

    DOSSIER_SORTIE.mkdir(parents=True, exist_ok=True)
    time.sleep(1.0)  # le service limite le débit à 1 requête par seconde
    telecharger(FICHIER)
    maintenant = datetime.now(timezone.utc).isoformat(timespec="seconds")
    mettre_a_jour_manifeste({"nom": FICHIER.name, "taille": FICHIER.stat().st_size,
                             "date_telechargement": maintenant, "sha256": sha256_fichier(FICHIER)})
    print(f"Fichier : {FICHIER.name} ({FICHIER.stat().st_size} octets)\nManifeste : {MANIFESTE}")
    afficher_couche(FICHIER)


if __name__ == "__main__":
    main()
