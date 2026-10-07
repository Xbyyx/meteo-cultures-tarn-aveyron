"""Filtre du RPG 2024 sur le Tarn (81) et l'Aveyron (12).

- lit RPG_Parcelles.gpkg avec pyogrio, limité à l'emprise des deux départements ;
- rattache chaque parcelle à un département par son point représentatif
  (point garanti à l'intérieur de la parcelle, contrairement au centroïde) ;
- garde les codes culture d'intérêt puis agrège le nombre de parcelles et la
  somme de surf_parc par département et par code culture ;
- écrit data/processed/surface_culture_2024.csv.

Les limites doivent déjà être en EPSG:2154 (c'est le cas du fichier produit par
src/ingestion/download_limites.py) : pyproj est bloqué par une stratégie de
contrôle d'application de cette machine, donc aucune reprojection n'est faite ici.

Exemple : python src/nettoyage/filtrer_departements.py
"""

import sys
import time
import warnings
from pathlib import Path

import pandas as pd
import pyogrio
import shapely

RACINE = Path(__file__).resolve().parents[2]
LIMITES = RACINE / "data" / "raw" / "admin" / "limites_departements_12_81.geojson"
DOSSIER_RPG = RACINE / "data" / "raw" / "rpg"
SORTIE = RACINE / "data" / "processed" / "surface_culture_2024.csv"
CODES_CULTURE = ["BTH", "BTP", "MIS", "MID", "TRN", "SGH", "SGP", "PPH", "PTR"]
CRS_ATTENDU = "EPSG:2154"

# geopandas signale que pyproj est inutilisable ; le système de coordonnées est vérifié avec pyogrio.
warnings.filterwarnings("ignore", message="Cannot set the CRS")


def trouver_parcelles():
    """Chemin du RPG_Parcelles.gpkg de l'édition 2024."""
    trouves = sorted(set(DOSSIER_RPG.glob("**/RPG_Parcelles.gpkg")))
    trouves = [chemin for chemin in trouves if "2024" in chemin.relative_to(DOSSIER_RPG).parts[0]]
    if len(trouves) != 1:
        sys.exit(f"{len(trouves)} fichier(s) RPG_Parcelles.gpkg 2024 trouvé(s) : {trouves}")
    return trouves[0]


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
    """Renvoie (codes, géométries) des départements, après vérification du système de coordonnées."""
    crs = pyogrio.read_info(LIMITES)["crs"]
    if crs != CRS_ATTENDU:
        sys.exit(f"Limites en {crs} au lieu de {CRS_ATTENDU} : relancez download_limites.py.")
    donnees = pyogrio.read_dataframe(LIMITES, columns=["code_insee"])
    return donnees["code_insee"].to_numpy(), donnees.geometry.to_numpy()


def main():
    debut = time.perf_counter()
    codes, limites = lire_limites()
    emprise = tuple(shapely.total_bounds(limites))
    print(f"Emprise des limites (EPSG:2154) : {tuple(round(x) for x in emprise)}")

    fichier = trouver_parcelles()
    info = pyogrio.read_info(fichier)
    if info["crs"] != CRS_ATTENDU:
        sys.exit(f"Parcelles en {info['crs']} au lieu de {CRS_ATTENDU}.")
    # Lecture limitée à l'emprise : seules les parcelles dont l'enveloppe touche le rectangle sont lues.
    parcelles = pyogrio.read_dataframe(fichier, bbox=emprise, columns=["code_cultu", "surf_parc"])
    total = len(parcelles)
    print(f"Parcelles lues dans l'emprise : {total} (sur {info['features']} pour l'Occitanie)")

    # Point représentatif : toujours à l'intérieur de la parcelle, même non convexe.
    points = shapely.point_on_surface(parcelles.geometry.to_numpy())
    arbre = shapely.STRtree(limites)
    index_point, index_dep = arbre.query(points, predicate="intersects")
    attribution = pd.Series(codes[index_dep], index=index_point)
    attribution = attribution[~attribution.index.duplicated()]  # point exactement sur une limite commune
    parcelles["departement"] = attribution.reindex(range(total)).to_numpy()

    parcelles = parcelles.drop(columns="geometry")
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
                .reset_index())
    resultat["surface_ha"] = resultat["surface_ha"].round(2)
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    resultat.to_csv(SORTIE, index=False, encoding="utf-8")
    print(f"\nÉcrit : {SORTIE}\n{resultat.to_string(index=False)}")
    print(f"\nDurée : {time.perf_counter() - debut:.1f} s ; mémoire maximale : {memoire_max_mo():.0f} Mo")


if __name__ == "__main__":
    main()
