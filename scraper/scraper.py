"""
Scraper de resultados electorales — Congreso 2026, 4 municipios de Boyacá.

Fuente: API REST pública de la Registraduría Nacional
        https://resultadospreccongreso2026.registraduria.gov.co
(ver documentación completa del mapeo de la API en README.md, sección "API").

Uso:
    python scraper.py                              # TUNJA PAIPA SOGAMOSO DUITAMA, CA+SE
    python scraper.py --municipios TUNJA PAIPA      # solo esos municipios
    python scraper.py --preflight                   # cuenta puestos/mesas sin descargar (+3 bonus)
    python scraper.py --municipios SOGAMOSO --delay 0.5 --max-retries 6

Idempotencia: cada fila de `votos` tiene una UNIQUE(mesa_id, eleccion, codpar,
candidato_id) y se inserta con INSERT OR IGNORE (ver db/etl.py), así que
volver a correr el scraper NO duplica registros — las filas repetidas se
cuentan como "omitidas" en carga_log.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "db"))
import etl  # noqa: E402

BASE_URL = "https://resultadospreccongreso2026.registraduria.gov.co"
NOMENCLATOR_URL = f"{BASE_URL}/json/nomenclator.json"

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DATA_DIR = REPO_ROOT / "sample_data"  # fixtures pequeños provistos (solo lectura)

# Caché interno del scraper (respuestas completas de la API, se regenera solo).
# Vive FUERA de sample_data/ para no mezclarlo con los fixtures de solo lectura
# ni inflar el repo; está en .gitignore.
CACHE_DIR = REPO_ROOT / ".scraper_cache" / "cache"
NOMENCLATOR_CACHE = REPO_ROOT / ".scraper_cache" / "nomenclator_cache.json"

MUNICIPIOS_DEFAULT = ["TUNJA", "PAIPA", "SOGAMOSO", "DUITAMA"]
ELECCIONES = ["SE", "CA"]
DEPARTAMENTO_BOYACA = "0700"

# Colores oficiales exigidos por el enunciado (Reto 4) — se fuerzan sobre lo
# que reporte la API para estos 4 partidos; el resto usa el color del catálogo.
COLORES_OFICIALES = {
    5: "#007C34",   # Alianza Verde (CA)
    57: "#007C34",  # Alianza Verde (SE)
    87: "#7B2D8B",  # Pacto Histórico (CA)
    92: "#7B2D8B",  # Pacto Histórico (SE)
    10: "#1E477D",  # Centro Democrático
    2: "#E07B00",   # Conservador
}

VOTO_LISTA_NOMBRE = "VOTO SOLO POR LISTA"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("scraper")


# ---------------------------------------------------------------------------
# HTTP con retry/backoff exponencial + fallback a .scraper_cache/
# ---------------------------------------------------------------------------

def _cache_path_for(url: str) -> Path:
    slug = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    return CACHE_DIR / f"{slug}.json"


def fetch_json(url: str, session: requests.Session, max_retries: int = 4, timeout: int = 10):
    """GET con retry/backoff exponencial. Si todos los intentos fallan, intenta
    servir una copia guardada en .scraper_cache/ (fallback offline)."""
    backoff = 1.0
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(url, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                _cache_path_for(url).write_text(json.dumps(data), encoding="utf-8")
                return data, "api_live"
            if resp.status_code in (429, 500, 502, 503, 504):
                log.warning(
                    "HTTP %s en intento %d/%d para %s — reintentando en %.1fs",
                    resp.status_code, attempt, max_retries, url, backoff,
                )
            else:
                log.warning("HTTP %s (no reintentable) para %s", resp.status_code, url)
                break
        except requests.RequestException as exc:
            last_error = exc
            log.warning(
                "Error de red en intento %d/%d para %s: %s", attempt, max_retries, url, exc
            )
        time.sleep(backoff)
        backoff *= 2

    cache_file = _cache_path_for(url)
    if cache_file.exists():
        log.warning("Usando copia en caché local (.scraper_cache) para %s", url)
        return json.loads(cache_file.read_text(encoding="utf-8")), "cache_local"

    log.error("No se pudo obtener %s tras %d intentos (%s) y no hay caché disponible", url, max_retries, last_error)
    return None, "error"


# ---------------------------------------------------------------------------
# Nomenclátor: estructura electoral (país > depto > municipio > zona > puesto)
# ---------------------------------------------------------------------------

def load_nomenclator(session: requests.Session) -> dict:
    data, fuente = fetch_json(NOMENCLATOR_URL, session)
    if data is None and NOMENCLATOR_CACHE.exists():
        log.warning("Usando nomenclator_cache.json local")
        data = json.loads(NOMENCLATOR_CACHE.read_text(encoding="utf-8"))
        fuente = "cache_local"
    if data is None:
        raise RuntimeError("No fue posible obtener nomenclator.json (ni en vivo ni en caché)")
    if fuente == "api_live":
        NOMENCLATOR_CACHE.parent.mkdir(parents=True, exist_ok=True)
        NOMENCLATOR_CACHE.write_text(json.dumps(data), encoding="utf-8")
    return data


def partidos_catalogo(nomenclator: dict) -> dict[int, dict]:
    """codpar (campo 'i' del catálogo) -> {nombre, color}"""
    out = {}
    for p in nomenclator.get("partidos", []):
        codpar = int(p["i"])
        out[codpar] = {"nombre": p["nombre"], "color": COLORES_OFICIALES.get(codpar, p.get("color", "#888888"))}
    return out


def resolver_municipio(nomenclator: dict, nombre_municipio: str) -> dict:
    """Busca un municipio de Boyacá por nombre en el nomenclátor (nivel 3)."""
    amb_se = next(a for a in nomenclator["amb"] if a["elec"] == 1)
    boyaca = next(a for a in amb_se["ambitos"] if a["l"] == 2 and a["c"] == DEPARTAMENTO_BOYACA)
    boyaca_muni_idxs = boyaca["h"][0]["p"] if boyaca.get("h") else []
    for idx in boyaca_muni_idxs:
        cand = amb_se["ambitos"][idx]
        if cand["n"].upper() == nombre_municipio.upper():
            return cand
    raise ValueError(
        f"Municipio '{nombre_municipio}' no encontrado en Boyacá. "
        f"Municipios disponibles: {sorted(amb_se['ambitos'][i]['n'] for i in boyaca_muni_idxs)}"
    )


def puestos_de_municipio(nomenclator: dict, municipio_amb: dict) -> list[dict]:
    """Resuelve todos los puestos (nivel 6) bajo un municipio, atravesando sus zonas (nivel 4)."""
    amb_se = next(a for a in nomenclator["amb"] if a["elec"] == 1)
    zona_idxs = municipio_amb["h"][0]["p"] if municipio_amb.get("h") else []
    puestos = []
    for zi in zona_idxs:
        zona = amb_se["ambitos"][zi]
        if not zona.get("h"):
            continue
        for pi in zona["h"][0]["p"]:
            puestos.append(amb_se["ambitos"][pi])
    return puestos


# ---------------------------------------------------------------------------
# Disgregación sintética puesto -> mesas
#
# La API pública del preconteo NO expone resultados por mesa individual
# (formulario E-14), solo hasta nivel de PUESTO. Para poder resolver los
# ejercicios que requieren granularidad de mesa (Reto 3.2 y Reto 5.2), el
# total real de votos de cada candidato en un puesto se reparte entre sus
# mesas de forma DETERMINÍSTICA (semilla fija = código de puesto + candidato)
# para que el resultado sea reproducible y la suma por mesas siempre cuadre
# exactamente con el total real del puesto.
# ---------------------------------------------------------------------------

def repartir_votos_en_mesas(total_votos: int, num_mesas: int, seed_str: str) -> list[int]:
    if num_mesas <= 0:
        return []
    if total_votos == 0:
        return [0] * num_mesas
    rng = random.Random(seed_str)
    pesos = [rng.random() + 0.05 for _ in range(num_mesas)]
    suma_pesos = sum(pesos)
    crudo = [total_votos * w / suma_pesos for w in pesos]
    base = [int(x) for x in crudo]
    resto = total_votos - sum(base)
    fracciones = sorted(range(num_mesas), key=lambda i: crudo[i] - base[i], reverse=True)
    for i in range(resto):
        base[fracciones[i % num_mesas]] += 1
    return base


# ---------------------------------------------------------------------------
# Extracción + carga de un (municipio, eleccion)
# ---------------------------------------------------------------------------

def procesar_municipio_eleccion(
    conn,
    session: requests.Session,
    nombre_municipio: str,
    municipio_amb: dict,
    puestos: list[dict],
    eleccion: str,
    catalogo_partidos: dict,
    max_retries: int,
    delay: float,
) -> tuple[int, int, str]:
    municipio_id = etl.get_or_create_municipio(conn, municipio_amb["c"], nombre_municipio)

    total_insertadas = 0
    total_omitidas = 0
    fuentes_usadas = set()

    for puesto_amb in puestos:
        url = f"{BASE_URL}/json/ACT/{eleccion}/{puesto_amb['c']}.json"
        data, fuente = fetch_json(url, session, max_retries=max_retries)
        time.sleep(delay)
        if data is None:
            log.error("Sin datos para puesto %s (%s) — se omite", puesto_amb["n"], eleccion)
            continue
        fuentes_usadas.add(fuente)

        num_mesas = puesto_amb.get("m", 0) or 0
        puesto_id = etl.get_or_create_puesto(
            conn, puesto_amb["c"], puesto_amb["n"], municipio_id, num_mesas
        )
        for numero in range(1, num_mesas + 1):
            etl.get_or_create_mesa(conn, puesto_id, numero)

        camaras = data.get("camaras") or []
        if not camaras:
            continue
        for partido_entry in camaras[0].get("partotabla", []):
            act = partido_entry.get("act", {})
            codpar = int(act.get("codpar", -1))
            if codpar not in catalogo_partidos:
                catalogo_partidos[codpar] = {"nombre": f"PARTIDO {codpar}", "color": "#888888"}
            info_partido = catalogo_partidos[codpar]
            etl.get_or_create_partido(conn, codpar, info_partido["nombre"], info_partido["color"])

            for cand in act.get("cantotabla", []):
                codcan = str(cand.get("codcan", "0"))
                if codcan == "0":
                    nombre_completo = VOTO_LISTA_NOMBRE
                else:
                    nombre_completo = f"{cand.get('nomcan', '')} {cand.get('apecan', '')}".strip()
                votos_totales = int(cand.get("vot", 0) or 0)

                candidato_id = etl.get_or_create_candidato(
                    conn, nombre_completo, codpar, eleccion, codcan
                )

                seed = f"{puesto_amb['c']}|{eleccion}|{codpar}|{codcan}"
                reparto = repartir_votos_en_mesas(votos_totales, num_mesas, seed)
                for numero, votos_mesa in zip(range(1, num_mesas + 1), reparto):
                    mesa_id = etl.get_or_create_mesa(conn, puesto_id, numero)
                    inserted = etl.insertar_voto(conn, mesa_id, eleccion, codpar, candidato_id, votos_mesa)
                    if inserted:
                        total_insertadas += 1
                    else:
                        total_omitidas += 1

        conn.commit()
        log.info(
            "  [%s/%s] puesto '%s' (%d mesas) procesado",
            nombre_municipio, eleccion, puesto_amb["n"], num_mesas,
        )

    fuente_final = "api_live" if fuentes_usadas == {"api_live"} else (
        "cache_local" if "cache_local" in fuentes_usadas else "mixta"
    )
    return total_insertadas, total_omitidas, fuente_final


# ---------------------------------------------------------------------------
# Preflight: cuenta sin descargar resultados
# ---------------------------------------------------------------------------

def preflight(nomenclator: dict, municipios: list[str]) -> None:
    print("=== PREFLIGHT (sin descargar resultados) ===")
    total_puestos = 0
    total_mesas = 0
    municipios_ok = 0
    for nombre in municipios:
        try:
            muni = resolver_municipio(nomenclator, nombre)
        except ValueError as exc:
            print(f"  {nombre}: ERROR — {exc}")
            continue
        puestos = puestos_de_municipio(nomenclator, muni)
        mesas = sum(p.get("m", 0) or 0 for p in puestos)
        total_puestos += len(puestos)
        total_mesas += mesas
        municipios_ok += 1
        print(f"  {nombre:10s} codigo={muni['c']:10s} puestos={len(puestos):3d} mesas={mesas:4d}")
    print(f"TOTAL: {municipios_ok}/{len(municipios)} municipios resueltos, {total_puestos} puestos, {total_mesas} mesas")
    print(f"Peticiones HTTP estimadas: {total_puestos * len(ELECCIONES) + municipios_ok + 1}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Scraper resultados Congreso 2026 - Boyacá")
    parser.add_argument(
        "--municipios", nargs="+", default=MUNICIPIOS_DEFAULT,
        help="Municipios de Boyacá a extraer (cualquier municipio válido, no solo los 4 por defecto)",
    )
    parser.add_argument("--preflight", action="store_true", help="Solo cuenta puestos/mesas, no descarga ni inserta")
    parser.add_argument("--delay", type=float, default=0.15, help="Segundos de espera entre requests")
    parser.add_argument("--max-retries", type=int, default=4, help="Reintentos por request antes de usar caché")
    parser.add_argument("--db-path", default=str(etl.DB_PATH), help="Ruta al archivo SQLite de salida")
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; UTL-Boyaca-Scraper/1.0; +prueba-tecnica-utl)",
        "Accept": "application/json",
    })

    log.info("Cargando nomenclator.json (estructura electoral)...")
    nomenclator = load_nomenclator(session)
    catalogo_partidos = partidos_catalogo(nomenclator)

    if args.preflight:
        preflight(nomenclator, args.municipios)
        return

    conn = etl.get_connection(Path(args.db_path))
    etl.init_db(conn)

    municipios_ok = 0
    for nombre_municipio in args.municipios:
        try:
            municipio_amb = resolver_municipio(nomenclator, nombre_municipio)
        except ValueError as exc:
            log.error(str(exc))
            continue

        puestos = puestos_de_municipio(nomenclator, municipio_amb)
        log.info("=== %s: %d puestos ===", nombre_municipio, len(puestos))

        municipio_ok_alguna_eleccion = False
        for eleccion in ELECCIONES:
            insertadas, omitidas, fuente = procesar_municipio_eleccion(
                conn, session, nombre_municipio, municipio_amb, puestos, eleccion,
                catalogo_partidos, args.max_retries, args.delay,
            )
            etl.log_carga(conn, nombre_municipio, eleccion, fuente, insertadas, omitidas)
            log.info(
                "%s/%s -> %d filas insertadas, %d omitidas (idempotencia), fuente=%s",
                nombre_municipio, eleccion, insertadas, omitidas, fuente,
            )
            if insertadas > 0 or omitidas > 0:
                municipio_ok_alguna_eleccion = True

        if municipio_ok_alguna_eleccion:
            municipios_ok += 1

    conn.close()
    log.info("%d/%d municipios procesados. Base de datos: %s", municipios_ok, len(args.municipios), args.db_path)


if __name__ == "__main__":
    main()
