"""Inventaire des ressources RPG de la région Occitanie (R76).

Parcourt le flux Atom de la Géoplateforme page par page et affiche les
entrées dont la zone est R76 : titre, date d'édition et format.
Ne télécharge aucune donnée.
"""

import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

URL_FLUX = "https://data.geopf.fr/telechargement/resource/RPG"
NB_PAGES = 35
ZONE = "R76"
PAUSE = 1.0  # secondes entre deux pages, le serveur limite le débit
TENTATIVES = 4
USER_AGENT = "Mozilla/5.0"
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "gpf": "https://data.geopf.fr/annexes/ressources/xsd/gpf_dl.xsd",
}


def lire_xml(url):
    """Renvoie la racine XML de l'URL demandée, avec nouvelles tentatives sur 429."""
    # Le serveur refuse l'agent utilisateur par défaut de urllib (403).
    requete = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for tentative in range(1, TENTATIVES + 1):
        try:
            with urllib.request.urlopen(requete, timeout=60) as reponse:
                return ET.fromstring(reponse.read())
        except urllib.error.HTTPError as erreur:
            if erreur.code != 429 or tentative == TENTATIVES:
                raise
            time.sleep(5 * tentative)


def lire_page(numero):
    """Renvoie la racine XML de la page demandée."""
    return lire_xml(f"{URL_FLUX}?page={numero}")


def extraire_entree(entree):
    """Renvoie (zone, titre, date d'édition, format) pour une entrée du flux."""
    zone = entree.find("gpf:zone", NS)
    format_ = entree.find("gpf:format", NS)
    return (
        zone.get("term") if zone is not None else "",
        entree.findtext("atom:title", default="", namespaces=NS),
        entree.findtext("gpf:editionDate", default="", namespaces=NS),
        format_.get("term") if format_ is not None else "",
    )


def main():
    trouvees = 0
    for numero in range(1, NB_PAGES + 1):
        time.sleep(PAUSE)
        try:
            racine = lire_page(numero)
        except (urllib.error.URLError, ET.ParseError) as erreur:
            print(f"Page {numero} ignorée : {erreur}")
            continue
        for entree in racine.findall("atom:entry", NS):
            zone, titre, date_edition, format_ = extraire_entree(entree)
            if zone == ZONE:
                trouvees += 1
                print(f"{titre} | édition : {date_edition} | format : {format_}")
    print(f"{trouvees} entrée(s) pour la zone {ZONE}.")


if __name__ == "__main__":
    main()
