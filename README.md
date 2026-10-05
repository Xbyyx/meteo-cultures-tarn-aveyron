# Météo et cultures : Tarn et Aveyron

## Objectif

Pipeline de données (Python + SQLite) qui ingère le Registre parcellaire graphique (RPG) et les données météorologiques quotidiennes de Météo-France pour les départements de l'Aveyron (12) et du Tarn (81), sur les campagnes 2022 à 2024, afin de croiser cultures et conditions climatiques.

## Sources de données

| Source | Producteur | Lien | Licence |
|---|---|---|---|
| Registre parcellaire graphique (RPG) | IGN / ASP | https://www.data.gouv.fr/datasets/rpg | Licence Ouverte 2.0 |
| Données climatologiques de base quotidiennes | Météo-France | https://www.data.gouv.fr/datasets/donnees-climatologiques-de-base-quotidiennes | Licence Ouverte 2.0 |

## Architecture

```
data/            données brutes (ignorées par git)
  raw/meteo/     fichiers CSV compressés Météo-France et manifest.csv
  raw/rpg/       archives RPG
src/
  ingestion/     téléchargement et inventaire des sources
  nettoyage/     nettoyage et normalisation
  chargement/    chargement dans SQLite
db/              base SQLite (ignorée par git)
dashboard/       tableau de bord
docs/            documentation
```

## Installation

Python 3 est requis. Aucune dépendance externe n'est nécessaire pour l'instant.

```bash
python -m venv .venv
```

## Lancement

Télécharger les données météo (départements 12 et 81) :

```bash
python src/ingestion/download_meteo.py
```

Lister les ressources RPG disponibles pour l'Occitanie (aucun téléchargement) :

```bash
python src/ingestion/list_rpg.py
```

## Captures

À compléter.
