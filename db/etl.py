"""
ETL — carga normalizada de resultados electorales en puestos_2026.db

Expone funciones reutilizadas por scraper/scraper.py para insertar datos de
forma idempotente (INSERT OR IGNORE + UNIQUE constraints) y registrar cuántas
filas se insertaron vs. se omitieron por cada corrida (tabla carga_log).

Ejecutado directamente (`python db/etl.py`) solo inicializa el schema vacío;
la carga real de datos la orquesta scraper.py.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "puestos_2026.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()


def normalizar_nombre(nombre: str) -> str:
    """Colapsa espacios, normaliza unicode (tildes con forma NFC) y usa Title Case."""
    if not nombre:
        return ""
    nombre = unicodedata.normalize("NFC", nombre)
    nombre = re.sub(r"\s+", " ", nombre).strip()
    return nombre.title()


def get_or_create_municipio(conn: sqlite3.Connection, codigo: str, nombre: str) -> int:
    conn.execute(
        "INSERT OR IGNORE INTO municipios (codigo, nombre) VALUES (?, ?)",
        (codigo, nombre.upper()),
    )
    row = conn.execute("SELECT id FROM municipios WHERE codigo = ?", (codigo,)).fetchone()
    return row[0]


def get_or_create_partido(conn: sqlite3.Connection, codpar: int, nombre: str, color: str) -> int:
    conn.execute(
        "INSERT OR IGNORE INTO partidos (codpar, nombre, color) VALUES (?, ?, ?)",
        (codpar, nombre, color),
    )
    return codpar


def get_or_create_puesto(
    conn: sqlite3.Connection, codigo: str, nombre: str, municipio_id: int, num_mesas: int
) -> int:
    conn.execute(
        "INSERT OR IGNORE INTO puestos (codigo, nombre, municipio_id, num_mesas) VALUES (?, ?, ?, ?)",
        (codigo, nombre, municipio_id, num_mesas),
    )
    row = conn.execute("SELECT id FROM puestos WHERE codigo = ?", (codigo,)).fetchone()
    return row[0]


def get_or_create_mesa(conn: sqlite3.Connection, puesto_id: int, numero: int) -> int:
    conn.execute(
        "INSERT OR IGNORE INTO mesas (puesto_id, numero) VALUES (?, ?)",
        (puesto_id, numero),
    )
    row = conn.execute(
        "SELECT id FROM mesas WHERE puesto_id = ? AND numero = ?", (puesto_id, numero)
    ).fetchone()
    return row[0]


def get_or_create_candidato(
    conn: sqlite3.Connection, nombre: str, codpar: int, eleccion: str, codcan: str
) -> int:
    nombre_norm = normalizar_nombre(nombre)
    conn.execute(
        """INSERT OR IGNORE INTO candidatos (codcan, nombre, codpar, eleccion)
           VALUES (?, ?, ?, ?)""",
        (codcan, nombre_norm, codpar, eleccion),
    )
    row = conn.execute(
        "SELECT id FROM candidatos WHERE nombre = ? AND codpar = ? AND eleccion = ?",
        (nombre_norm, codpar, eleccion),
    ).fetchone()
    return row[0]


def insertar_voto(
    conn: sqlite3.Connection,
    mesa_id: int,
    eleccion: str,
    codpar: int,
    candidato_id: int,
    votos: int,
) -> bool:
    """Devuelve True si insertó una fila nueva, False si ya existía (idempotencia)."""
    cur = conn.execute(
        """INSERT OR IGNORE INTO votos (mesa_id, eleccion, codpar, candidato_id, votos)
           VALUES (?, ?, ?, ?, ?)""",
        (mesa_id, eleccion, codpar, candidato_id, votos),
    )
    return cur.rowcount > 0


def log_carga(
    conn: sqlite3.Connection,
    municipio: str,
    eleccion: str,
    fuente: str,
    filas_insertadas: int,
    filas_omitidas: int,
) -> None:
    conn.execute(
        """INSERT INTO carga_log (municipio, eleccion, fuente, filas_insertadas, filas_omitidas, fecha_carga)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            municipio,
            eleccion,
            fuente,
            filas_insertadas,
            filas_omitidas,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def main() -> None:
    conn = get_connection()
    init_db(conn)
    print(f"Schema inicializado en {DB_PATH}")
    conn.close()


if __name__ == "__main__":
    main()
