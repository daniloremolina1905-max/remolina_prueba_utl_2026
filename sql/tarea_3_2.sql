-- Tarea 3.2 — Dominancia extrema
--
-- Mesas donde un candidato concentra más del 60% de los votos de SU PROPIO
-- partido en esa misma mesa (mismo mesa_id + eleccion + codpar).
-- Se excluye el pseudo-candidato "VOTO SOLO POR LISTA" porque no es una
-- persona candidata, es el remanente de votos marcados solo por el partido.
--
-- Se exige además total_partido_mesa >= 5: con menos de 5 votos totales del
-- partido en la mesa, superar 60% es casi automático (p.ej. 1 de 1 voto) y
-- no aporta señal real de dominancia; este umbral es un criterio analítico
-- para evitar ruido estadístico en mesas con muestras minúsculas.

WITH votos_partido_mesa AS (
    SELECT mesa_id, eleccion, codpar, SUM(votos) AS total_partido_mesa
    FROM votos
    GROUP BY mesa_id, eleccion, codpar
)
SELECT
    mu.nombre                                                     AS municipio,
    pu.nombre                                                     AS puesto,
    me.numero                                                     AS mesa,
    v.eleccion,
    pa.nombre                                                     AS partido,
    c.nombre                                                      AS candidato,
    v.votos                                                       AS votos_candidato,
    vpm.total_partido_mesa,
    ROUND(CAST(v.votos AS REAL) / vpm.total_partido_mesa, 4)      AS pct_del_partido
FROM votos v
JOIN votos_partido_mesa vpm
    ON vpm.mesa_id = v.mesa_id AND vpm.eleccion = v.eleccion AND vpm.codpar = v.codpar
JOIN mesas me      ON me.id = v.mesa_id
JOIN puestos pu    ON pu.id = me.puesto_id
JOIN municipios mu ON mu.id = pu.municipio_id
JOIN partidos pa   ON pa.codpar = v.codpar
JOIN candidatos c  ON c.id = v.candidato_id
WHERE vpm.total_partido_mesa >= 5
  AND CAST(v.votos AS REAL) / vpm.total_partido_mesa > 0.60
  AND c.nombre != 'Voto Solo Por Lista'
ORDER BY pct_del_partido DESC, votos_candidato DESC;
