"""
Reto 5.2 - Scatter Cámara vs. Senado por mesa.

Genera viz/scatter_ca_se.png:
    cada punto = una mesa (votos válidos totales de Cámara vs. de Senado)
    color por municipio, línea de regresión OLS, r de Pearson anotado

Imprime en stdout la línea exigida por el manifest:
    r=X.XXX | pendiente=X.XXX | n_mesas=NNN

Uso:
    python viz/scatter.py
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

DB_PATH = Path(__file__).resolve().parent.parent / "db" / "puestos_2026.db"
OUT_PATH = Path(__file__).resolve().parent / "scatter_ca_se.png"

COLORES_MUNICIPIO = {
    "TUNJA": "#1E477D",
    "PAIPA": "#007C34",
    "SOGAMOSO": "#E07B00",
    "DUITAMA": "#7B2D8B",
}


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def votos_por_mesa(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Total de votos válidos (excluye 'voto solo por lista') de CA y SE por mesa."""
    return conn.execute(
        """
        WITH ca AS (
            SELECT v.mesa_id, SUM(v.votos) AS votos_ca
            FROM votos v
            JOIN candidatos c ON c.id = v.candidato_id
            WHERE v.eleccion = 'CA' AND c.nombre != 'Voto Solo Por Lista'
            GROUP BY v.mesa_id
        ),
        se AS (
            SELECT v.mesa_id, SUM(v.votos) AS votos_se
            FROM votos v
            JOIN candidatos c ON c.id = v.candidato_id
            WHERE v.eleccion = 'SE' AND c.nombre != 'Voto Solo Por Lista'
            GROUP BY v.mesa_id
        )
        SELECT
            mu.nombre AS municipio,
            me.id AS mesa_id,
            COALESCE(ca.votos_ca, 0) AS votos_ca,
            COALESCE(se.votos_se, 0) AS votos_se
        FROM mesas me
        JOIN puestos pu ON pu.id = me.puesto_id
        JOIN municipios mu ON mu.id = pu.municipio_id
        LEFT JOIN ca ON ca.mesa_id = me.id
        LEFT JOIN se ON se.mesa_id = me.id
        """
    ).fetchall()


def main() -> None:
    conn = connect()
    rows = votos_por_mesa(conn)
    conn.close()

    municipio = np.array([r["municipio"] for r in rows])
    x = np.array([r["votos_ca"] for r in rows], dtype=float)
    y = np.array([r["votos_se"] for r in rows], dtype=float)
    n_mesas = len(rows)

    reg = stats.linregress(x, y)
    r = reg.rvalue
    pendiente = reg.slope

    print(f"r={r:.3f} | pendiente={pendiente:.3f} | n_mesas={n_mesas}")

    fig, ax = plt.subplots(figsize=(8, 6.5))
    for muni, color in COLORES_MUNICIPIO.items():
        mask = municipio == muni
        ax.scatter(x[mask], y[mask], s=14, alpha=0.6, color=color, label=muni, edgecolors="none")

    x_line = np.linspace(x.min(), x.max(), 100)
    y_line = reg.intercept + reg.slope * x_line
    ax.plot(x_line, y_line, color="#1c283d", linewidth=2, linestyle="--", label="Regresión OLS")

    ax.set_xlabel("Votos válidos Cámara por mesa")
    ax.set_ylabel("Votos válidos Senado por mesa")
    ax.set_title("Correlación de participación Cámara vs. Senado por mesa\nBoyacá 2026 (Tunja, Paipa, Sogamoso, Duitama)")
    ax.legend(loc="upper left", fontsize=9)
    ax.annotate(
        f"r = {r:.3f}\npendiente = {pendiente:.3f}\nn = {n_mesas} mesas",
        xy=(0.98, 0.03), xycoords="axes fraction",
        ha="right", va="bottom", fontsize=10,
        bbox=dict(boxstyle="round", facecolor="white", edgecolor="#dfe4ea", alpha=0.9),
    )
    fig.tight_layout()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PATH, dpi=150)
    print(f"Guardado {OUT_PATH} ({OUT_PATH.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
