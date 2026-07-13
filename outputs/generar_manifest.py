"""
Genera outputs/evaluation_manifest.json. Valida automáticamente:
  - Reto 1/2: que la BD tenga filas de los 4 municipios ("4/4 municipios")
  - Reto 3: que las 3 queries de sql/ corran sin error ("SQL OK")
  - Reto 5: valores impresos por viz/scatter.py (r, pendiente, n_mesas)
  - Bonus detectados automáticamente en el repo

*** EDITE LA SECCIÓN META ANTES DE ENTREGAR ***

Uso:
    python outputs/generar_manifest.py
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ============================================================================
# META - EDITAR ANTES DE ENTREGAR
# ============================================================================
META = {
    "nombre": "DANILO JOSE REMOLINA ANGEL",
    "email": "daniloremolina@gmail.com",
    "repo_url": "https://github.com/Daniloremolina1905-MAX/remolina_prueba_utl_2026",
}
# ============================================================================

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "db" / "puestos_2026.db"
SQL_DIR = ROOT / "sql"
VIZ_DIR = ROOT / "viz"
DASHBOARD_DIR = ROOT / "dashboard"
OUT_PATH = Path(__file__).resolve().parent / "evaluation_manifest.json"

MUNICIPIOS_ESPERADOS = ["TUNJA", "PAIPA", "SOGAMOSO", "DUITAMA"]


def check_reto1_2() -> dict:
    """Valida que la BD tenga filas de los municipios esperados (Reto 1.3 / 2.3)."""
    if not DB_PATH.exists():
        return {
            "status": "ERROR: db/puestos_2026.db no existe. Corra `python scraper/scraper.py` primero.",
            "municipios_encontrados": 0,
            "municipios_esperados": len(MUNICIPIOS_ESPERADOS),
        }

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    detalle = {}
    encontrados = 0
    for muni in MUNICIPIOS_ESPERADOS:
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT pu.id) AS puestos, COUNT(DISTINCT me.id) AS mesas, COUNT(v.id) AS filas_votos
            FROM municipios mu
            LEFT JOIN puestos pu ON pu.municipio_id = mu.id
            LEFT JOIN mesas me ON me.puesto_id = pu.id
            LEFT JOIN votos v ON v.mesa_id = me.id
            WHERE mu.nombre = ?
            """,
            (muni,),
        ).fetchone()
        tiene_datos = row and row["filas_votos"] and row["filas_votos"] > 0
        if tiene_datos:
            encontrados += 1
        detalle[muni] = {
            "puestos": row["puestos"] if row else 0,
            "mesas": row["mesas"] if row else 0,
            "filas_votos": row["filas_votos"] if row else 0,
        }

    tablas = {}
    for t in ("municipios", "partidos", "puestos", "mesas", "candidatos", "votos", "carga_log"):
        tablas[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]

    lider_se_por_municipio = {}
    for muni in MUNICIPIOS_ESPERADOS:
        row = conn.execute(
            """
            SELECT pa.nombre AS partido, SUM(v.votos) AS votos
            FROM votos v
            JOIN mesas me ON me.id = v.mesa_id
            JOIN puestos pu ON pu.id = me.puesto_id
            JOIN municipios mu ON mu.id = pu.municipio_id
            JOIN partidos pa ON pa.codpar = v.codpar
            WHERE v.eleccion = 'SE' AND mu.nombre = ?
            GROUP BY v.codpar
            ORDER BY votos DESC
            LIMIT 1
            """,
            (muni,),
        ).fetchone()
        lider_se_por_municipio[muni] = row["partido"] if row else None

    conn.close()

    status = f"{encontrados}/{len(MUNICIPIOS_ESPERADOS)} municipios"
    return {
        "status": status,
        "municipios_esperados": len(MUNICIPIOS_ESPERADOS),
        "municipios_encontrados": encontrados,
        "detalle_por_municipio": detalle,
        "conteo_tablas": tablas,
        "partido_lider_se_por_municipio": lider_se_por_municipio,
    }


def check_reto3() -> dict:
    """Ejecuta las 3 queries de sql/ contra la BD y reporta SQL OK / ERROR."""
    resultados = {}
    if not DB_PATH.exists():
        for i in (1, 2, 3):
            resultados[f"tarea_3_{i}"] = {"status": "ERROR: BD no existe"}
        return resultados

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    for i in (1, 2, 3):
        sql_path = SQL_DIR / f"tarea_3_{i}.sql"
        try:
            sql_text = sql_path.read_text(encoding="utf-8")
            rows = conn.execute(sql_text).fetchall()
            muestra = [dict(r) for r in rows[:5]]
            resultados[f"tarea_3_{i}"] = {
                "status": "SQL OK",
                "filas_resultado": len(rows),
                "muestra": muestra,
            }
            print(f"  tarea_3_{i}.sql -> SQL OK ({len(rows)} filas)")
        except Exception as exc:  # noqa: BLE001
            resultados[f"tarea_3_{i}"] = {"status": f"ERROR: {exc}"}
            print(f"  tarea_3_{i}.sql -> ERROR: {exc}")

    conn.close()
    return resultados


def check_reto5() -> dict:
    """Corre viz/scatter.py y parsea 'r=X.XXX | pendiente=X.XXX | n_mesas=NNN'."""
    out = {"scatter": None, "heatmap_png_kb": None, "scatter_png_kb": None}

    heatmap_png = VIZ_DIR / "heatmap_municipios.png"
    scatter_png = VIZ_DIR / "scatter_ca_se.png"

    try:
        proc = subprocess.run(
            [sys.executable, str(VIZ_DIR / "scatter.py")],
            capture_output=True, text=True, cwd=ROOT, timeout=120,
        )
        match = re.search(r"r=([\-\d.]+)\s*\|\s*pendiente=([\-\d.]+)\s*\|\s*n_mesas=(\d+)", proc.stdout)
        if match:
            out["scatter"] = {
                "r": float(match.group(1)),
                "pendiente": float(match.group(2)),
                "n_mesas": int(match.group(3)),
            }
        else:
            out["scatter"] = {"error": "No se encontró la línea r=... en la salida de scatter.py", "stdout": proc.stdout[-500:]}
    except Exception as exc:  # noqa: BLE001
        out["scatter"] = {"error": str(exc)}

    if heatmap_png.exists():
        out["heatmap_png_kb"] = round(heatmap_png.stat().st_size / 1024, 1)
    if scatter_png.exists():
        out["scatter_png_kb"] = round(scatter_png.stat().st_size / 1024, 1)

    return out


def check_bonus() -> list[str]:
    bonus = []

    scraper_src = (ROOT / "scraper" / "scraper.py").read_text(encoding="utf-8")
    if "--preflight" in scraper_src:
        bonus.append("1.2 preflight (+3)")

    schema_src = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    if schema_src.count("CREATE INDEX") >= 3:
        bonus.append("2.1 indices_justificados (+2)")

    readme_src = (ROOT / "README.md").read_text(encoding="utf-8") if (ROOT / "README.md").exists() else ""
    if "atribución" in readme_src.lower() and "top ca" in readme_src.lower():
        bonus.append("3.3 explicacion_top_ca_vs_atribucion_se (+2)")

    dashboard_src = (DASHBOARD_DIR / "index.html").read_text(encoding="utf-8") if (DASHBOARD_DIR / "index.html").exists() else ""
    if ("data-theme" in dashboard_src or "data-tema" in dashboard_src) and (
        "themeToggleBtn" in dashboard_src or "btn-tema" in dashboard_src
    ):
        bonus.append("4 dark_mode (+3)")
    if "exportCsvBtn" in dashboard_src or "btn-csv" in dashboard_src:
        bonus.append("4 export_csv (+2)")

    if "--municipios" in scraper_src and "resolver_municipio" in scraper_src:
        bonus.append("libre municipios_adicionales (+3)")

    return bonus


def main() -> None:
    print("=== Reto 1/2: verificando base de datos ===")
    reto1_2 = check_reto1_2()
    print(f"  {reto1_2['status']}")

    print("=== Reto 3: ejecutando consultas SQL ===")
    reto3 = check_reto3()

    print("=== Reto 5: ejecutando visualizaciones ===")
    reto5 = check_reto5()
    if reto5["scatter"] and "r" in reto5["scatter"]:
        s = reto5["scatter"]
        print(f"  r={s['r']:.3f} | pendiente={s['pendiente']:.3f} | n_mesas={s['n_mesas']}")

    print("=== Bonus detectados en el repo ===")
    bonus = check_bonus()
    for b in bonus:
        print(f"  + {b}")

    manifest = {
        "meta": META,
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "reto1_2_extraccion_y_bd": reto1_2,
        "reto3_sql": reto3,
        "reto5_viz": reto5,
        "bonus_detectados": bonus,
    }

    OUT_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nManifiesto escrito en {OUT_PATH}")
    print(f"RESUMEN: {reto1_2['status']} | "
          f"SQL: {sum(1 for k in reto3 if reto3[k]['status']=='SQL OK')}/3 OK | "
          f"bonus: {len(bonus)}")


if __name__ == "__main__":
    main()
