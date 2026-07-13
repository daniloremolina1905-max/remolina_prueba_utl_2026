-- Schema BD Electoral Boyacá 2026
-- UTL Senado de la República · Prueba Técnica Analista de Datos
--
-- Granularidad real disponible en la API de la Registraduría: hasta PUESTO de
-- votación (no publica resultados por MESA individual en el preconteo). Las
-- filas de `mesas` y los votos asociados a ellas se generan por el ETL
-- repartiendo de forma determinística (seed fija) los totales reales de cada
-- puesto entre sus mesas, para poder resolver los ejercicios que piden
-- granularidad de mesa (Reto 3.2 y Reto 5.2). Esto se documenta también en el
-- README, sección "API".

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS municipios (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo  TEXT NOT NULL UNIQUE,   -- código DIVIPOLA (ej. 0700001 = Tunja)
    nombre  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS partidos (
    codpar  INTEGER PRIMARY KEY,   -- código de partido según nomenclator.json ("i")
    nombre  TEXT NOT NULL,
    color   TEXT NOT NULL          -- hex; para los 4 partidos del enunciado se fuerza el color oficial
);

CREATE TABLE IF NOT EXISTS puestos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo         TEXT NOT NULL UNIQUE,  -- código de puesto (ej. 0700001010005)
    nombre         TEXT NOT NULL,
    municipio_id   INTEGER NOT NULL REFERENCES municipios(id),
    num_mesas      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS mesas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    puesto_id   INTEGER NOT NULL REFERENCES puestos(id),
    numero      INTEGER NOT NULL,
    UNIQUE (puesto_id, numero)
);

CREATE TABLE IF NOT EXISTS candidatos (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    codcan    TEXT NOT NULL,          -- código de tarjetón; '0' = "voto solo por lista"
    nombre    TEXT NOT NULL,
    codpar    INTEGER NOT NULL REFERENCES partidos(codpar),
    eleccion  TEXT NOT NULL CHECK (eleccion IN ('CA', 'SE')),
    UNIQUE (nombre, codpar, eleccion)
);

CREATE TABLE IF NOT EXISTS votos (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    mesa_id       INTEGER NOT NULL REFERENCES mesas(id),
    eleccion      TEXT NOT NULL CHECK (eleccion IN ('CA', 'SE')),
    codpar        INTEGER NOT NULL REFERENCES partidos(codpar),
    candidato_id  INTEGER NOT NULL REFERENCES candidatos(id),
    votos         INTEGER NOT NULL CHECK (votos >= 0),
    UNIQUE (mesa_id, eleccion, codpar, candidato_id)
);

CREATE TABLE IF NOT EXISTS carga_log (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    municipio          TEXT NOT NULL,
    eleccion           TEXT NOT NULL,
    fuente             TEXT NOT NULL,   -- 'api_live' | 'sample_data'
    filas_insertadas   INTEGER NOT NULL DEFAULT 0,
    filas_omitidas     INTEGER NOT NULL DEFAULT 0,
    fecha_carga        TEXT NOT NULL    -- ISO 8601
);

-- ---------------------------------------------------------------------------
-- Índices (bonus Reto 2.1, +2 pts) — justificación de qué consulta optimiza
-- ---------------------------------------------------------------------------

-- idx_votos_mesa: acelera el JOIN mesas->votos usado en TODAS las consultas de
-- sql/tarea_3_*.sql y en viz/scatter.py, que agregan votos agrupando por mesa.
CREATE INDEX IF NOT EXISTS idx_votos_mesa ON votos(mesa_id);

-- idx_votos_codpar_eleccion: acelera el filtro "WHERE eleccion=? AND codpar=?"
-- que usa tarea_3_1.sql (arrastre Verde CA->SE) y tarea_3_3.sql (totales por
-- partido), evitando un table scan completo de la tabla `votos`.
CREATE INDEX IF NOT EXISTS idx_votos_codpar_eleccion ON votos(codpar, eleccion);

-- idx_mesas_puesto: acelera agrupar/enlazar mesas por puesto, usado en
-- tarea_3_1.sql y tarea_3_2.sql y en dashboard/export_data.py (pestaña Arrastre).
CREATE INDEX IF NOT EXISTS idx_mesas_puesto ON mesas(puesto_id);

-- idx_puestos_municipio: acelera "top 10 candidatos por municipio" del
-- dashboard y el filtro por municipio de viz/heatmap.py.
CREATE INDEX IF NOT EXISTS idx_puestos_municipio ON puestos(municipio_id);
