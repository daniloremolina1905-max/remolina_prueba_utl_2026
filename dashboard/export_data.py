"""
Genera dashboard/data.json y embebe el mismo JSON en dashboard/index.html
(marcadores DATA_START/DATA_END) — fetch() vía file:// falla por CORS.

Uso:
    python dashboard/export_data.py
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "db" / "puestos_2026.db"
DATA_JSON_PATH = Path(__file__).resolve().parent / "data.json"
INDEX_HTML_PATH = Path(__file__).resolve().parent / "index.html"

MARK_START = "/*__DATA_START__*/"
MARK_END = "/*__DATA_END__*/"

# Homologación Verde CA->SE exigida por el enunciado (Reto 3.1 / Reto 4)
CODPAR_VERDE_CA = 5
CODPAR_VERDE_SE = 57


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def build_municipios(conn: sqlite3.Connection) -> list[str]:
    return [r["nombre"] for r in conn.execute("SELECT nombre FROM municipios ORDER BY nombre")]


def build_comparativo(conn: sqlite3.Connection) -> list[dict]:
    """Votos CA y SE totales (válidos, sin voto-solo-lista) por municipio, con conteo de puestos/mesas."""

    def votos_por_municipio(eleccion: str) -> dict[str, int]:
        rows = conn.execute(
            """
            SELECT mu.nombre AS municipio, SUM(v.votos) AS votos
            FROM votos v
            JOIN mesas me ON me.id = v.mesa_id
            JOIN puestos pu ON pu.id = me.puesto_id
            JOIN municipios mu ON mu.id = pu.municipio_id
            JOIN candidatos c ON c.id = v.candidato_id
            WHERE v.eleccion = ? AND c.nombre != 'Voto Solo Por Lista'
            GROUP BY mu.id
            """,
            (eleccion,),
        ).fetchall()
        return {r["municipio"]: r["votos"] for r in rows}

    votos_ca = votos_por_municipio("CA")
    votos_se = votos_por_municipio("SE")

    conteos = conn.execute(
        """
        SELECT mu.nombre AS municipio, COUNT(DISTINCT pu.id) AS puestos, COUNT(DISTINCT me.id) AS mesas
        FROM municipios mu
        JOIN puestos pu ON pu.municipio_id = mu.id
        JOIN mesas me ON me.puesto_id = pu.id
        GROUP BY mu.id
        ORDER BY mu.nombre
        """
    ).fetchall()

    return [
        {
            "municipio": r["municipio"],
            "votos_ca": votos_ca.get(r["municipio"], 0),
            "votos_se": votos_se.get(r["municipio"], 0),
            "puestos": r["puestos"],
            "mesas": r["mesas"],
        }
        for r in conteos
    ]


def build_por_municipio(conn: sqlite3.Connection) -> dict:
    """Por municipio: top 10 candidatos CA + partido líder SE."""
    out = {}
    municipios = build_municipios(conn)
    for muni in municipios:
        top_candidatos = conn.execute(
            """
            SELECT c.nombre AS candidato, pa.nombre AS partido, pa.color AS color, SUM(v.votos) AS votos
            FROM votos v
            JOIN mesas me ON me.id = v.mesa_id
            JOIN puestos pu ON pu.id = me.puesto_id
            JOIN municipios mu ON mu.id = pu.municipio_id
            JOIN candidatos c ON c.id = v.candidato_id
            JOIN partidos pa ON pa.codpar = v.codpar
            WHERE v.eleccion = 'CA' AND mu.nombre = ? AND c.nombre != 'Voto Solo Por Lista'
            GROUP BY v.candidato_id
            ORDER BY votos DESC
            LIMIT 10
            """,
            (muni,),
        ).fetchall()

        partidos_se = conn.execute(
            """
            SELECT pa.nombre AS partido, pa.color AS color, SUM(v.votos) AS votos
            FROM votos v
            JOIN mesas me ON me.id = v.mesa_id
            JOIN puestos pu ON pu.id = me.puesto_id
            JOIN municipios mu ON mu.id = pu.municipio_id
            JOIN partidos pa ON pa.codpar = v.codpar
            WHERE v.eleccion = 'SE' AND mu.nombre = ?
            GROUP BY v.codpar
            ORDER BY votos DESC
            LIMIT 6
            """,
            (muni,),
        ).fetchall()

        total_se_municipio = conn.execute(
            """
            SELECT SUM(v.votos) AS total
            FROM votos v
            JOIN mesas me ON me.id = v.mesa_id
            JOIN puestos pu ON pu.id = me.puesto_id
            JOIN municipios mu ON mu.id = pu.municipio_id
            WHERE v.eleccion = 'SE' AND mu.nombre = ?
            """,
            (muni,),
        ).fetchone()["total"] or 1

        lider = partidos_se[0] if partidos_se else None

        out[muni] = {
            "top_candidatos_ca": [
                {"candidato": r["candidato"], "partido": r["partido"], "color": r["color"], "votos": r["votos"]}
                for r in top_candidatos
            ],
            "partido_lider_se": (
                {
                    "partido": lider["partido"],
                    "color": lider["color"],
                    "votos": lider["votos"],
                    "pct": round(100.0 * lider["votos"] / total_se_municipio, 1),
                }
                if lider
                else None
            ),
            "partidos_se": [
                {"partido": r["partido"], "color": r["color"], "votos": r["votos"]} for r in partidos_se
            ],
        }
    return out


def build_kpis(conn: sqlite3.Connection) -> dict:
    """Indicadores globales para la fila de tarjetas KPI del dashboard."""

    def total_votos(eleccion: str) -> int:
        row = conn.execute(
            """
            SELECT SUM(v.votos) AS total
            FROM votos v
            JOIN candidatos c ON c.id = v.candidato_id
            WHERE v.eleccion = ? AND c.nombre != 'Voto Solo Por Lista'
            """,
            (eleccion,),
        ).fetchone()
        return row["total"] or 0

    puestos_total = conn.execute("SELECT COUNT(*) AS n FROM puestos").fetchone()["n"]
    mesas_total = conn.execute("SELECT COUNT(*) AS n FROM mesas").fetchone()["n"]
    municipios_total = conn.execute("SELECT COUNT(*) AS n FROM municipios").fetchone()["n"]

    return {
        "votos_ca_total": total_votos("CA"),
        "votos_se_total": total_votos("SE"),
        "puestos_total": puestos_total,
        "mesas_total": mesas_total,
        "municipios_total": municipios_total,
    }


def build_arrastre(conn: sqlite3.Connection) -> dict:
    """Ratio Verde SE/CA por puesto, agrupado por municipio (reutiliza sql/tarea_3_1.sql)."""
    sql_path = Path(__file__).resolve().parent.parent / "sql" / "tarea_3_1.sql"
    sql_text = sql_path.read_text(encoding="utf-8")
    rows = conn.execute(sql_text).fetchall()

    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["municipio"], []).append(
            {
                "puesto": r["puesto"],
                "votos_ca_verde": r["votos_ca_verde"],
                "votos_se_verde": r["votos_se_verde"],
                "ratio_arrastre": r["ratio_arrastre"],
            }
        )
    return out


def build_data() -> dict:
    conn = connect()
    data = {
        "municipios": build_municipios(conn),
        "kpis": build_kpis(conn),
        "comparativo": build_comparativo(conn),
        "por_municipio": build_por_municipio(conn),
        "arrastre": build_arrastre(conn),
    }
    conn.close()
    return data


def write_data_json(data: dict) -> None:
    DATA_JSON_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Escrito {DATA_JSON_PATH} ({DATA_JSON_PATH.stat().st_size} bytes)")


def embed_into_html(data: dict) -> None:
    html = INDEX_HTML_PATH.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(MARK_START) + r".*?" + re.escape(MARK_END), re.DOTALL)
    replacement = MARK_START + " " + json.dumps(data, ensure_ascii=False) + " " + MARK_END
    if not pattern.search(html):
        raise RuntimeError(f"No se encontraron los marcadores {MARK_START} / {MARK_END} en index.html")
    html_nuevo = pattern.sub(lambda _: replacement, html)
    INDEX_HTML_PATH.write_text(html_nuevo, encoding="utf-8")
    print(f"Datos embebidos en {INDEX_HTML_PATH}")


def main() -> None:
    data = build_data()
    write_data_json(data)
    embed_into_html(data)
    print(f"Municipios en el dashboard: {len(data['municipios'])}/4 -> {data['municipios']}")


if __name__ == "__main__":
    main()
