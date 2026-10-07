"""Téléchargement d'une édition du RPG pour une zone donnée.

Retrouve l'entrée correspondant à la zone et à la date d'édition dans le flux
Atom de la Géoplateforme, vérifie la taille avant tout téléchargement,
télécharge l'archive dans data/raw/rpg/, la décompresse avec un outil
système (7z ou bsdtar) puis met à jour data/raw/rpg/manifest.csv.

Exemple : python src/ingestion/download_rpg.py --zone R76 --edition 2024-01-01
"""

import argparse
import csv
import hashlib
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from list_rpg import NB_PAGES, NS, PAUSE, URL_FLUX, USER_AGENT, extraire_entree, lire_page, lire_xml

DOSSIER_SORTIE = Path(__file__).resolve().parents[2] / "data" / "raw" / "rpg"
MANIFESTE = DOSSIER_SORTIE / "manifest.csv"
CHAMPS_MANIFESTE = ["nom", "taille", "date_telechargement", "sha256"]
TAILLE_BLOC = 1024 * 1024
GO = 1000**3


def trouver_ressource(zone, edition, format_):
    """Renvoie les titres des entrées du flux qui correspondent à la zone, l'édition et le format."""
    trouvees = []
    for numero in range(1, NB_PAGES + 1):
        time.sleep(PAUSE)
        for entree in lire_page(numero).findall("atom:entry", NS):
            zone_e, titre, edition_e, format_e = extraire_entree(entree)
            if zone_e == zone and edition_e == edition and (not format_ or format_e == format_):
                trouvees.append(titre)
        if trouvees:
            break
    return trouvees


def lien_telechargement(titre):
    """Renvoie (url, taille annoncée) du fichier de la ressource."""
    time.sleep(PAUSE)
    racine = lire_xml(f"{URL_FLUX}/{titre}")
    lien = racine.find("atom:entry/atom:link", NS)
    if lien is None:
        raise RuntimeError(f"Aucun lien de téléchargement pour {titre}")
    return lien.get("href"), int(lien.get(f"{{{NS['gpf']}}}length", "0"))


def taille_distante(url):
    """Taille du fichier d'après une requête HEAD, sinon un GET avec Range."""
    entetes = {"User-Agent": USER_AGENT}
    try:
        requete = urllib.request.Request(url, headers=entetes, method="HEAD")
        with urllib.request.urlopen(requete, timeout=60) as reponse:
            return int(reponse.headers["Content-Length"])
    except Exception:
        time.sleep(PAUSE)
        requete = urllib.request.Request(url, headers={**entetes, "Range": "bytes=0-0"})
        with urllib.request.urlopen(requete, timeout=60) as reponse:
            return int(reponse.headers["Content-Range"].rsplit("/", 1)[-1])


def sha256_fichier(chemin):
    empreinte = hashlib.sha256()
    with open(chemin, "rb") as fichier:
        for bloc in iter(lambda: fichier.read(TAILLE_BLOC), b""):
            empreinte.update(bloc)
    return empreinte.hexdigest()


def telecharger(url, destination, taille_attendue):
    """Télécharge url vers destination (fichier .part renommé à la fin)."""
    partiel = destination.with_name(destination.name + ".part")
    requete = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    recu = 0
    dernier = time.monotonic()
    with urllib.request.urlopen(requete, timeout=120) as reponse, open(partiel, "wb") as sortie:
        for bloc in iter(lambda: reponse.read(TAILLE_BLOC), b""):
            sortie.write(bloc)
            recu += len(bloc)
            if time.monotonic() - dernier > 15:
                print(f"  {recu / GO:.2f} Go / {taille_attendue / GO:.2f} Go", flush=True)
                dernier = time.monotonic()
    if recu != taille_attendue:
        raise RuntimeError(f"Taille reçue {recu} différente de la taille annoncée {taille_attendue}")
    partiel.replace(destination)


def trouver_outil_extraction():
    """Renvoie (commande, style 7z) pour extraire une archive 7z : 7z/7za/7zr, sinon bsdtar."""
    for nom in ("7z", "7za", "7zr"):
        chemin = shutil.which(nom)
        if chemin:
            return [chemin, "x", "-y"], True
    candidats = [shutil.which("tar"), shutil.which("bsdtar"), r"C:\Windows\System32\tar.exe"]
    for chemin in filter(None, candidats):
        try:
            sortie = subprocess.run([chemin, "--version"], capture_output=True, text=True).stdout
        except OSError:
            continue
        if "bsdtar" in sortie:
            return [chemin, "-xf"], False
    return None, False


def decompresser(archive, dossier):
    """Décompresse l'archive dans dossier et renvoie la liste des nouveaux fichiers."""
    commande, style_7z = trouver_outil_extraction()
    if commande is None:
        sys.exit("Aucun outil de décompression 7z trouvé (7z, 7za, 7zr ou bsdtar). Installez 7-Zip.")
    avant = {p for p in dossier.rglob("*") if p.is_file()}
    if style_7z:
        commande = commande + [f"-o{dossier}", str(archive)]
    else:
        commande = commande + [str(archive), "-C", str(dossier)]
    print(f"Décompression : {' '.join(commande)}", flush=True)
    subprocess.run(commande, check=True)
    return sorted(p for p in dossier.rglob("*") if p.is_file() and p not in avant)


def mettre_a_jour_manifeste(lignes):
    """Ajoute ou remplace les lignes du manifeste, indexées par nom."""
    existantes = {}
    if MANIFESTE.exists():
        with open(MANIFESTE, newline="", encoding="utf-8") as fichier:
            existantes = {ligne["nom"]: ligne for ligne in csv.DictReader(fichier)}
    for ligne in lignes:
        existantes[ligne["nom"]] = ligne
    with open(MANIFESTE, "w", newline="", encoding="utf-8") as fichier:
        ecrivain = csv.DictWriter(fichier, fieldnames=CHAMPS_MANIFESTE)
        ecrivain.writeheader()
        ecrivain.writerows(existantes.values())


def main():
    analyseur = argparse.ArgumentParser(description="Télécharge une édition du RPG.")
    analyseur.add_argument("--zone", required=True, help="code de zone, par exemple R76")
    analyseur.add_argument("--edition", required=True, help="date d'édition, par exemple 2024-01-01")
    analyseur.add_argument("--format", default="GPKG", help="format de la ressource (défaut : GPKG)")
    analyseur.add_argument("--taille-max-go", type=float, default=1.5,
                           help="taille au-delà de laquelle le script s'arrête (défaut : 1,5 Go)")
    analyseur.add_argument("--confirme", action="store_true",
                           help="autorise le téléchargement même au-delà de la taille maximale")
    args = analyseur.parse_args()

    trouvees = trouver_ressource(args.zone, args.edition, args.format)
    if len(trouvees) != 1:
        sys.exit(f"{len(trouvees)} ressource(s) pour {args.zone} / {args.edition} / {args.format} : {trouvees}")
    titre = trouvees[0]
    url, taille_annoncee = lien_telechargement(titre)
    time.sleep(PAUSE)
    taille = taille_distante(url)
    print(f"Ressource : {titre}\nLien : {url}\nTaille : {taille} octets ({taille / GO:.2f} Go)")
    if taille_annoncee and taille_annoncee != taille:
        print(f"Attention : taille annoncée par le flux différente ({taille_annoncee} octets).")
    if taille > args.taille_max_go * GO and not args.confirme:
        sys.exit(f"Taille supérieure à {args.taille_max_go} Go : relancez avec --confirme pour télécharger.")

    DOSSIER_SORTIE.mkdir(parents=True, exist_ok=True)
    archive = DOSSIER_SORTIE / url.rsplit("/", 1)[-1]
    if archive.exists() and archive.stat().st_size == taille:
        print(f"Archive déjà présente : {archive.name}")
    else:
        print(f"Téléchargement de {archive.name} ...", flush=True)
        telecharger(url, archive, taille)

    maintenant = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lignes = [{"nom": archive.name, "taille": archive.stat().st_size,
               "date_telechargement": maintenant, "sha256": sha256_fichier(archive)}]

    if archive.name.endswith((".7z", ".7z.001")):  # volume unique nommé .7z.001 pour certaines éditions
        for fichier in decompresser(archive, DOSSIER_SORTIE):
            lignes.append({"nom": fichier.relative_to(DOSSIER_SORTIE).as_posix(),
                           "taille": fichier.stat().st_size, "date_telechargement": maintenant,
                           "sha256": sha256_fichier(fichier)})
    mettre_a_jour_manifeste(lignes)
    print(f"Manifeste mis à jour : {MANIFESTE}")


if __name__ == "__main__":
    main()
