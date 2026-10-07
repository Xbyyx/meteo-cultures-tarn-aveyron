-- Vues d'analyse de la base db/meteo_cultures.sqlite. Appliqué par lancer.py.
--
-- Méthode de calcul
--
-- parametres_meteo
--   Une ligne : le seuil de forte chaleur (tx >= seuil_chaleur_c, en °C) et la
--   complétude annuelle minimale (completude_min, 0.9 = 90 %). Pour changer un
--   seuil, modifier cette vue : toutes les autres la lisent.
--
-- station_completude
--   Une ligne par station et par année civile, pour les années où la station a
--   au moins une ligne dans meteo_jour. jours_rr, jours_tn, jours_tx comptent les
--   jours dont la valeur n'est pas NULL (le code qualité n'est pas utilisé, rien
--   n'est exclu). taux_* = jours renseignés / nombre de jours de l'année
--   (365 ou 366), non arrondi pour que la comparaison au seuil soit exacte.
--
-- meteo_mensuelle
--   Une ligne par département, mois (AAAA-MM) et campagne (= année civile du
--   mois). On calcule d'abord, pour chaque station, sa valeur du mois : somme de
--   rr, moyenne de tn, moyenne de tx, nombre de jours avec tx >= seuil. Puis on
--   moyenne ces valeurs entre les stations du département, chaque station
--   comptant pour un. Une station n'entre dans le calcul d'une mesure que si son
--   taux de complétude de l'année pour cette mesure (rr, tn ou tx) atteint
--   completude_min ; nb_stations_* donne le nombre de stations retenues.
--   Les jours sans mesure ne sont pas remplacés : le cumul de pluie d'un mois
--   incomplet est donc sous-estimé.
--
-- surface_vs_meteo
--   Une ligne par campagne, département et culture (nom court de culture_ref :
--   BTH et BTP forment « Blé tendre », etc.) : nombre de parcelles et surface
--   totale, avec les indicateurs météo de l'année civile de la campagne dans le
--   département : pluie cumulée annuelle (somme de rr sur l'année) et nombre de
--   jours de forte chaleur de l'année, chacun moyenné entre les stations
--   retenues (complétude annuelle de la mesure >= completude_min).

DROP VIEW IF EXISTS surface_vs_meteo;
DROP VIEW IF EXISTS meteo_mensuelle;
DROP VIEW IF EXISTS station_completude;
DROP VIEW IF EXISTS parametres_meteo;

CREATE VIEW parametres_meteo AS
SELECT 30.0 AS seuil_chaleur_c,   -- seuil de forte chaleur : tx >= 30 °C
       0.9  AS completude_min;    -- complétude annuelle minimale : 90 %

CREATE VIEW station_completude AS
SELECT num_poste,
       departement,
       annee,
       jours_annee,
       jours_rr,
       jours_tn,
       jours_tx,
       1.0 * jours_rr / jours_annee AS taux_rr,
       1.0 * jours_tn / jours_annee AS taux_tn,
       1.0 * jours_tx / jours_annee AS taux_tx
FROM (
    SELECT m.num_poste,
           s.departement,
           CAST(substr(m.date, 1, 4) AS INTEGER) AS annee,
           CASE WHEN CAST(substr(m.date, 1, 4) AS INTEGER) % 4 = 0
                 AND (CAST(substr(m.date, 1, 4) AS INTEGER) % 100 <> 0
                      OR CAST(substr(m.date, 1, 4) AS INTEGER) % 400 = 0)
                THEN 366 ELSE 365 END AS jours_annee,
           COUNT(m.rr) AS jours_rr,
           COUNT(m.tn) AS jours_tn,
           COUNT(m.tx) AS jours_tx
    FROM meteo_jour m
    JOIN station s ON s.num_poste = m.num_poste
    GROUP BY m.num_poste, annee
);

CREATE VIEW meteo_mensuelle AS
WITH station_mois AS (
    SELECT m.num_poste,
           c.departement,
           substr(m.date, 1, 7) AS mois,
           c.annee AS campagne,
           CASE WHEN c.taux_rr >= p.completude_min THEN SUM(m.rr) END AS cumul_rr,
           CASE WHEN c.taux_tn >= p.completude_min THEN AVG(m.tn) END AS tn_moyenne,
           CASE WHEN c.taux_tx >= p.completude_min THEN AVG(m.tx) END AS tx_moyenne,
           CASE WHEN c.taux_tx >= p.completude_min THEN SUM(m.tx >= p.seuil_chaleur_c) END AS jours_chaleur
    FROM meteo_jour m
    JOIN station_completude c ON c.num_poste = m.num_poste
                             AND c.annee = CAST(substr(m.date, 1, 4) AS INTEGER)
    CROSS JOIN parametres_meteo p
    GROUP BY m.num_poste, mois, c.taux_rr, c.taux_tn, c.taux_tx, p.completude_min, p.seuil_chaleur_c
)
SELECT departement,
       mois,
       campagne,
       ROUND(AVG(cumul_rr), 1)      AS pluie_mm_moyenne_station,
       ROUND(AVG(tn_moyenne), 2)    AS tmin_moyenne,
       ROUND(AVG(tx_moyenne), 2)    AS tmax_moyenne,
       ROUND(AVG(jours_chaleur), 2) AS jours_chaleur_moyen_station,
       COUNT(cumul_rr)              AS nb_stations_rr,
       COUNT(tn_moyenne)            AS nb_stations_tn,
       COUNT(tx_moyenne)            AS nb_stations_tx
FROM station_mois
GROUP BY departement, mois, campagne;

CREATE VIEW surface_vs_meteo AS
WITH station_annee AS (
    SELECT c.num_poste,
           c.departement,
           c.annee,
           CASE WHEN c.taux_rr >= p.completude_min THEN SUM(m.rr) END AS pluie_annuelle,
           CASE WHEN c.taux_tx >= p.completude_min THEN SUM(m.tx >= p.seuil_chaleur_c) END AS jours_chaleur
    FROM meteo_jour m
    JOIN station_completude c ON c.num_poste = m.num_poste
                             AND c.annee = CAST(substr(m.date, 1, 4) AS INTEGER)
    CROSS JOIN parametres_meteo p
    GROUP BY c.num_poste, c.annee, c.taux_rr, c.taux_tx, p.completude_min, p.seuil_chaleur_c
),
meteo AS (
    SELECT departement,
           annee AS campagne,
           AVG(pluie_annuelle)  AS pluie_annuelle_mm_moyenne_station,
           AVG(jours_chaleur)   AS jours_chaleur_moyen_station,
           COUNT(pluie_annuelle) AS nb_stations_rr,
           COUNT(jours_chaleur)  AS nb_stations_tx
    FROM station_annee
    GROUP BY departement, annee
),
surface AS (
    SELECT sc.campagne,
           sc.departement,
           cr.culture,
           SUM(sc.nb_parcelles) AS nb_parcelles,
           SUM(sc.surface_ha)   AS surface_ha
    FROM surface_culture sc
    JOIN culture_ref cr ON cr.code_culture = sc.code_culture
    GROUP BY sc.campagne, sc.departement, cr.culture
)
SELECT s.campagne,
       s.departement,
       s.culture,
       s.nb_parcelles,
       ROUND(s.surface_ha, 2)                           AS surface_ha,
       ROUND(m.pluie_annuelle_mm_moyenne_station, 1)    AS pluie_annuelle_mm_moyenne_station,
       ROUND(m.jours_chaleur_moyen_station, 2)          AS jours_chaleur_moyen_station,
       m.nb_stations_rr,
       m.nb_stations_tx
FROM surface s
LEFT JOIN meteo m ON m.departement = s.departement AND m.campagne = s.campagne;
