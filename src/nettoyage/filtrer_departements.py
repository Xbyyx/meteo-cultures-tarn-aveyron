"""Filtre du RPG (campagnes 2022, 2023 ou 2024) sur le Tarn (81) et l'Aveyron (12).

- lit le fichier de parcelles de la campagne (GeoPackage ou Shapefile) avec
  pyogrio, limité à l'emprise des deux départements ;
- compare le système de coordonnées du fichier à celui des limites et s'arrête
  s'ils diffèrent (aucune reprojection possible ici : pyproj est bloqué) ;
- rattache chaque parcelle à un département par son point représentatif
  (point garanti à l'intérieur de la parcelle, contrairement au centroïde) ;
- harmonise les codes de 2022 retirés depuis (EQUIVALENCES_CODES : MIE, PRL, RGA) ;
- garde les codes culture d'intérêt puis agrège le nombre de parcelles et la
  somme de surf_parc par département et par code culture ;
- remplace dans data/processed/surface_culture.csv les lignes de la campagne
  (colonnes campagne, departement, code_culture, nb_parcelles, surface_ha).

Les noms de colonnes sont lus sans tenir compte de la casse (RPG 2022 et 2023
en Shapefile : majuscules ; RPG 2024 en GeoPackage : minuscules).

Exemple : python src/nettoyage/filtrer_departements.py --campagne 2023
"""

import argparse
import re
import sys
import time
from pathlib import Path

import pandas as pd
import pyogrio
import shapely
from pyogrio.raw import read as lire_brut

RACINE = Path(__file__).resolve().parents[2]
LIMITES = RACINE / "data" / "raw" / "admin" / "limites_departements_12_81.geojson"
DOSSIER_RPG = RACINE / "data" / "raw" / "rpg"
SORTIE = RACINE / "data" / "processed" / "surface_culture.csv"
CAMPAGNES = ("2022", "2023", "2024")
CHAMPS_SORTIE = ["campagne", "departement", "code_culture", "nb_parcelles", "surface_ha"]
CODES_CULTURE = ["BTH", "BTP", "MIS", "MID", "TRN", "SGH", "SGP", "PPH", "PTR"]
# Changement de nomenclature du RPG entre 2022 et 2023 : des codes de 2022 ont été retirés
# et leurs parcelles reversées dans d'autres codes. Équivalences établies par comparaison
# des totaux départementaux :
#   MIE (maïs ensilage)                      -> MIS, qui couvre grain et ensilage depuis 2023 ;
#   PRL (prairie en rotation longue, 6 ans+) -> PPH ;
#   RGA (ray-grass de 5 ans ou moins)        -> PTR.
EQUIVALENCES_CODES = {"2022": {"MIE": "MIS", "PRL": "PPH", "RGA": "PTR"}}

# Lambert-93 (EPSG:2154) décrit par ses paramètres, pour comparer avec un WKT sans pyproj.
LAMBERT93 = ("lambert_conformal_conic_2sp",
             (("central_meridian", 3.0), ("false_easting", 700000.0), ("false_northing", 6600000.0),
              ("latitude_of_origin", 46.5), ("standard_parallel_1", 44.0), ("standard_parallel_2", 49.0)),
             6378137.0, 298.257222, 1.0)


def trouver_parcelles(campagne):
    """Chemin du fichier de parcelles de la campagne (GeoPackage ou Shapefile)."""
    trouves = set()
    for motif in ("**/RPG_Parcelles.gpkg", "**/PARCELLES_GRAPHIQUES.shp"):
        trouves.update(DOSSIER_RPG.glob(motif))
    trouves = sorted(chemin for chemin in trouves
                     if campagne in chemin.relative_to(DOSSIER_RPG).parts[0])
    if len(trouves) != 1:
        sys.exit(f"{len(trouves)} fichier de parcelles trouvé pour la campagne {campagne} : {trouves}")
    return trouves[0]


def signature_crs(crs):
    """Description comparable d'un système de coordonnées, sans pyproj.

    "EPSG:2154" est développé en ses paramètres ; un WKT (Shapefile) est réduit à
    la projection, ses paramètres, l'ellipsoïde et l'unité, sans les noms, qui
    varient d'une source à l'autre (« RGF93 Lambert 93 » contre EPSG:2154).
    """
    if crs is None:
        return None
    if crs == "EPSG:2154":
        return LAMBERT93
    wkt = str(crs)
    projection = re.search(r'PROJECTION\["([^"]+)"', wkt)
    ellipsoide = re.search(r'SPHEROID\["[^"]*",([\d.]+),([\d.]+)', wkt)
    unite = re.findall(r'UNIT\["[^"]*",([\d.]+)', wkt)[-1:]
    parametres = tuple(sorted((nom.lower(), float(valeur))
                              for nom, valeur in re.findall(r'PARAMETER\["([^"]+)",([-\d.]+)', wkt)))
    if not (projection and ellipsoide and unite and parametres):
        return wkt
    return (projection.group(1).lower(), parametres, round(float(ellipsoide.group(1)), 3),
            round(float(ellipsoide.group(2)), 6), float(unite[0]))


def memoire_max_mo():
    """Pic de mémoire (working set) du processus, en Mo."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Compteurs(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

        compteurs = Compteurs()
        compteurs.cb = ctypes.sizeof(Compteurs)
        # Les prototypes explicites évitent de tronquer le handle (64 bits) du processus.
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Compteurs), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(compteurs), compteurs.cb):
            return float("nan")
        return compteurs.PeakWorkingSetSize / 1024**2
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def lire_limites():
    """Renvoie (crs, codes de département, géométries) des limites."""
    meta, _, geometries, champs = lire_brut(LIMITES, columns=["code_insee"])
    return meta["crs"], champs[0], shapely.from_wkb(geometries)


def lire_parcelles(fichier, emprise):
    """Lit les parcelles dans l'emprise : renvoie (DataFrame code_cultu/surf_parc, géométries)."""
    noms = {nom.lower(): nom for nom in pyogrio.read_info(fichier)["fields"]}
    manquants = {"code_cultu", "surf_parc"} - noms.keys()
    if manquants:
        sys.exit(f"Colonnes absentes de {fichier.name} : {sorted(manquants)} (présentes : {sorted(noms)})")
    # Lecture limitée à l'emprise : seules les parcelles dont l'enveloppe touche le rectangle sont lues.
    meta, _, geometries, champs = lire_brut(fichier, bbox=emprise,
                                            columns=[noms["code_cultu"], noms["surf_parc"]])
    # Les champs sont renvoyés dans l'ordre du fichier, pas celui demandé : on les associe par nom.
    donnees = pd.DataFrame({nom.lower(): valeurs for nom, valeurs in zip(meta["fields"], champs)})
    return donnees, shapely.from_wkb(geometries)


def main():
    analyseur = argparse.ArgumentParser(description="Agrège le RPG par département et code culture.")
    analyseur.add_argument("--campagne", required=True, choices=CAMPAGNES, help="année du RPG")
    campagne = analyseur.parse_args().campagne

    debut = time.perf_counter()
    crs_limites, codes, limites = lire_limites()
    emprise = tuple(shapely.total_bounds(limites))
    print(f"Campagne {campagne}. Emprise des limites : {tuple(round(x) for x in emprise)}")

    fichier = trouver_parcelles(campagne)
    info = pyogrio.read_info(fichier)
    print(f"Fichier : {fichier.name} ({info['features']} parcelles pour l'Occitanie)")
    if signature_crs(info["crs"]) != signature_crs(crs_limites):
        sys.exit("Systèmes de coordonnées différents, arrêt (aucune reprojection possible ici).\n"
                 f"  parcelles : {info['crs']}\n  limites   : {crs_limites}")

    parcelles, geometries = lire_parcelles(fichier, emprise)
    total = len(parcelles)
    print(f"Parcelles lues dans l'emprise : {total}")

    # Point représentatif : toujours à l'intérieur de la parcelle, même non convexe.
    points = shapely.point_on_surface(geometries)
    arbre = shapely.STRtree(limites)
    index_point, index_dep = arbre.query(points, predicate="intersects")
    attribution = pd.Series(codes[index_dep], index=index_point)
    attribution = attribution[~attribution.index.duplicated()]  # point exactement sur une limite commune
    parcelles["departement"] = attribution.reindex(range(total)).to_numpy()

    parcelles["code_cultu"] = parcelles["code_cultu"].replace(EQUIVALENCES_CODES.get(campagne, {}))
    rattachees = parcelles["departement"].notna()
    gardees = parcelles["code_cultu"].isin(CODES_CULTURE)
    print(f"Non rattachées à 12 ou 81 : {(~rattachees).sum()} sur {total} ({100 * (~rattachees).mean():.2f} %)")
    nb_gardees = int(gardees.sum())
    non_rattachees_gardees = int((gardees & ~rattachees).sum())
    print(f"Parcelles aux codes retenus : {nb_gardees}, dont non rattachées : {non_rattachees_gardees} "
          f"({100 * non_rattachees_gardees / nb_gardees:.2f} %)")

    resultat = (parcelles[rattachees & gardees]
                .groupby(["departement", "code_cultu"])
                .agg(nb_parcelles=("surf_parc", "size"), surface_ha=("surf_parc", "sum"))
                .reset_index()
                .rename(columns={"code_cultu": "code_culture"}))
    resultat["surface_ha"] = resultat["surface_ha"].round(2)
    resultat.insert(0, "campagne", int(campagne))

    # Le fichier unique garde les autres campagnes et remplace celle-ci.
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    if SORTIE.exists():
        existant = pd.read_csv(SORTIE, dtype={"departement": str})
        resultat = pd.concat([existant[existant["campagne"] != int(campagne)], resultat])
    resultat = resultat.sort_values(["campagne", "departement", "code_culture"])[CHAMPS_SORTIE]
    resultat.to_csv(SORTIE, index=False, encoding="utf-8")
    print(f"Écrit : {SORTIE} ({len(resultat)} lignes, toutes campagnes)")
    print(f"Durée : {time.perf_counter() - debut:.1f} s ; mémoire maximale : {memoire_max_mo():.0f} Mo")


if __name__ == "__main__":
    main()
