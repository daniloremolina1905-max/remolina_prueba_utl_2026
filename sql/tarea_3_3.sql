-- Tarea 3.3 — Atribución determinística, Top 5 candidatos por atribución SE consolidada
-- A_ij = (votos_cand_i / votos_partido_j_CA) * votos_SE_partido_homologado_j
-- Homologación fijada por el enunciado: 5->57, 87->92. Resto: codpar_SE = codpar_CA
-- (ver README, "Hallazgos principales").

WITH homologacion AS (
    SELECT 5  AS codpar_ca, 57 AS codpar_se UNION ALL
    SELECT 87 AS codpar_ca, 92 AS codpar_se UNION ALL
    SELECT 10 AS codpar_ca, 10 AS codpar_se UNION ALL
    SELECT 2  AS codpar_ca, 2  AS codpar_se
),
votos_ca_partido AS (
    SELECT codpar, SUM(votos) AS total_ca_partido
    FROM votos WHERE eleccion = 'CA' GROUP BY codpar
),
votos_se_partido AS (
    SELECT codpar, SUM(votos) AS total_se_partido
    FROM votos WHERE eleccion = 'SE' GROUP BY codpar
),
votos_ca_candidato AS (
    SELECT v.codpar, v.candidato_id, c.nombre AS candidato, SUM(v.votos) AS votos_cand
    FROM votos v
    JOIN candidatos c ON c.id = v.candidato_id
    WHERE v.eleccion = 'CA' AND c.nombre != 'Voto Solo Por Lista'
    GROUP BY v.codpar, v.candidato_id
)
SELECT
    vc.candidato,
    pa.nombre                                                            AS partido_ca,
    vc.votos_cand,
    vcp.total_ca_partido,
    COALESCE(h.codpar_se, vc.codpar)                                     AS codpar_se_usado,
    COALESCE(vsp.total_se_partido, 0)                                    AS total_se_partido,
    ROUND(
        (CAST(vc.votos_cand AS REAL) / vcp.total_ca_partido) * COALESCE(vsp.total_se_partido, 0),
        2
    )                                                                     AS atribucion_se
FROM votos_ca_candidato vc
JOIN votos_ca_partido vcp ON vcp.codpar = vc.codpar
JOIN partidos pa          ON pa.codpar = vc.codpar
LEFT JOIN homologacion h  ON h.codpar_ca = vc.codpar
LEFT JOIN votos_se_partido vsp ON vsp.codpar = COALESCE(h.codpar_se, vc.codpar)
ORDER BY atribucion_se DESC
LIMIT 5;
