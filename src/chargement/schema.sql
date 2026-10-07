-- Schéma de la base db/meteo_cultures.sqlite.
-- Appliqué par creer_base.py sur une base neuve.

PRAGMA foreign_keys = ON;

-- Un poste météo ; le département est formé des deux premiers chiffres de NUM_POSTE.
CREATE TABLE station (
    num_poste    TEXT PRIMARY KEY,
    nom          TEXT,
    departement  TEXT NOT NULL,
    lat          REAL,
    lon          REAL,
    alti         REAL
);
CREATE INDEX idx_station_departement ON station (departement);

-- Mesures quotidiennes ; date au format AAAA-MM-JJ.
-- Les colonnes q_* conservent le code qualité Météo-France (9, 0, 1 ou 2).
CREATE TABLE meteo_jour (
    num_poste  TEXT NOT NULL REFERENCES station (num_poste),
    date       TEXT NOT NULL,
    rr         REAL,   -- précipitations sur 24 h, en mm
    tn         REAL,   -- température minimale sous abri, en °C
    tx         REAL,   -- température maximale sous abri, en °C
    q_rr       TEXT,
    q_tn       TEXT,
    q_tx       TEXT,
    PRIMARY KEY (num_poste, date)
);
CREATE INDEX idx_meteo_jour_date ON meteo_jour (date);

-- Référentiel des cultures suivies (libellés du référentiel officiel de l'IGN).
CREATE TABLE culture_ref (
    code_culture  TEXT PRIMARY KEY,
    libelle       TEXT NOT NULL,
    culture       TEXT NOT NULL   -- nom court : Blé tendre, Maïs, Tournesol, Seigle, Prairies
);

-- Parcelles et surfaces du RPG par campagne, département et code culture.
CREATE TABLE surface_culture (
    campagne      INTEGER NOT NULL,
    departement   TEXT NOT NULL,
    code_culture  TEXT NOT NULL REFERENCES culture_ref (code_culture),
    nb_parcelles  INTEGER,
    surface_ha    REAL,
    PRIMARY KEY (campagne, departement, code_culture)
);
CREATE INDEX idx_surface_culture_code ON surface_culture (code_culture);

-- Fichiers sources chargés, d'après les manifest.csv de data/raw.
CREATE TABLE source_fichier (
    nom                  TEXT NOT NULL,
    url                  TEXT,
    date_telechargement  TEXT,
    sha256               TEXT
);
