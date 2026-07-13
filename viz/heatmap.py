"""
Reto 5.1 - Heatmap de participación por candidato y municipio.

Genera viz/heatmap_municipios.png:
    filas    = top 8 candidatos de Cámara (por votos totales en los 4 municipios)
    columnas = los 4 municipios
    valores  = % que representa ese candidato sobre el total de votos válidos
               de Cámara EN ESE municipio (no sobre el total nacional/consolidado)

Uso:
    python viz/heatmap.py
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

DB_PATH = Path(__file__).resolve().parent.parent / "db" / "puestos_2026.db"
OUT_PATH = Path(__file__).resolve().parent / "heatmap_municipios.png"
TOP_N = 8


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def top_candidatos(conn: sqlite3.Connection, n: int) -> list[str]:
    rows = conn.execute(
        """
        SELECT c.nombre AS candidato, SUM(v.votos) AS total
        FROM votos v
        JOIN candidatos c ON c.id = v.candidato_id
        WHERE v.eleccion = 'CA' AND c.nombre != 'Voto Solo Por Lista'
        GROUP BY v.candidato_id
        ORDER BY total DESC
        LIMIT ?
        """,
        (n,),
    ).fetchall()
    return [r["candidato"] for r in rows]


def municipios(conn: sqlite3.Connection) -> list[str]:
    return [r["nombre"] for r in conn.execute("SELECT nombre FROM municipios ORDER BY nombre")]


def totales_ca_por_municipio(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT mu.nombre AS municipio, SUM(v.votos) AS total
        FROM votos v
        JOIN mesas me ON me.id = v.mesa_id
        JOIN puestos pu ON pu.id = me.puesto_id
        JOIN municipios mu ON mu.id = pu.municipio_id
        JOIN candidatos c ON c.id = v.candidato_id
        WHERE v.eleccion = 'CA' AND c.nombre != 'Voto Solo Por Lista'
        GROUP BY mu.id
        """
    ).fetchall()
    return {r["municipio"]: r["total"] for r in rows}


def votos_candidato_por_municipio(conn: sqlite3.Connection, candidato: str) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT mu.nombre AS municipio, SUM(v.votos) AS total
        FROM votos v
        JOIN mesas me ON me.id = v.mesa_id
        JOIN puestos pu ON pu.id = me.puesto_id
        JOIN municipios mu ON mu.id = pu.municipio_id
        JOIN candidatos c ON c.id = v.candidato_id
        WHERE v.eleccion = 'CA' AND c.nombre = ?
        GROUP BY mu.id
        """,
        (candidato,),
    ).fetchall()
    return {r["municipio"]: r["total"] for r in rows}


def main() -> None:
    conn = connect()
    candidatos = top_candidatos(conn, TOP_N)
    munis = municipios(conn)
    totales = totales_ca_por_municipio(conn)

    matriz = np.zeros((len(candidatos), len(munis)))
    for i, cand in enumerate(candidatos):
        votos_muni = votos_candidato_por_municipio(conn, cand)
        for j, muni in enumerate(munis):
            total_muni = totales.get(muni, 0) or 1
            matriz[i, j] = 100.0 * votos_muni.get(muni, 0) / total_muni

    conn.close()

    fig, ax = plt.subplots(figsize=(1.6 * len(munis) + 3, 0.55 * len(candidatos) + 2.2))
    im = ax.imshow(matriz, cmap="YlGnBu", aspect="auto")

    ax.set_xticks(range(len(munis)))
    ax.set_xticklabels(munis)
    ax.set_yticks(range(len(candidatos)))
    ax.set_yticklabels(candidatos)

    for i in range(len(candidatos)):
        for j in range(len(munis)):
            valor = matriz[i, j]
            color = "white" if valor > matriz.max() * 0.6 else "black"
            ax.text(j, i, f"{valor:.1f}%", ha="center", va="center", color=color, fontsize=9)

    ax.set_title(f"Top {TOP_N} candidatos Cámara - % de votos válidos por municipio\nBoyacá 2026", fontsize=11)
    fig.colorbar(im, ax=ax, label="% del total de Cámara en el municipio")
    fig.tight_layout()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PATH, dpi=150)
    print(f"Guardado {OUT_PATH} ({OUT_PATH.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
