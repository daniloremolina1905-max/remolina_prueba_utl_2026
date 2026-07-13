-- Tarea 3.1 — Arrastre Alianza Verde CA -> SE, por puesto y municipio
-- ratio_arrastre = votos_SE_Verde / votos_CA_Verde
-- Homologación: codpar_CA=5 -> codpar_SE=57

SELECT
    m.nombre                                                            AS municipio,
    p.nombre                                                            AS puesto,
    p.codigo                                                            AS codigo_puesto,
    COALESCE(ca.votos_ca, 0)                                            AS votos_ca_verde,
    COALESCE(se.votos_se, 0)                                            AS votos_se_verde,
    ROUND(
        CAST(COALESCE(se.votos_se, 0) AS REAL) / NULLIF(ca.votos_ca, 0),
        4
    )                                                                    AS ratio_arrastre
FROM puestos p
JOIN municipios m ON m.id = p.municipio_id
LEFT JOIN (
    SELECT me.puesto_id AS puesto_id, SUM(v.votos) AS votos_ca
    FROM votos v
    JOIN mesas me ON me.id = v.mesa_id
    WHERE v.eleccion = 'CA' AND v.codpar = 5
    GROUP BY me.puesto_id
) ca ON ca.puesto_id = p.id
LEFT JOIN (
    SELECT me.puesto_id AS puesto_id, SUM(v.votos) AS votos_se
    FROM votos v
    JOIN mesas me ON me.id = v.mesa_id
    WHERE v.eleccion = 'SE' AND v.codpar = 57
    GROUP BY me.puesto_id
) se ON se.puesto_id = p.id
ORDER BY m.nombre, p.nombre;
