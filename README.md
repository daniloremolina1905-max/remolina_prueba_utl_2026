# REMOLINA — Prueba Técnica UTL Senado 2026

Pipeline de datos electorales para el Congreso de la República 2026, en cuatro
municipios de Boyacá: Tunja, Paipa, Sogamoso y Duitama.

## Candidato

- **Nombre:** DANILO JOSE REMOLINA ANGEL
- **Email:** daniloremolina@gmail.com
- **Repositorio:** `https://github.com/Daniloremolina1905-MAX/remolina_prueba_utl_2026`

## Instalación



```bash
python -m venv .venv
```

Activar el entorno: en Windows es `.venv\Scripts\activate`, en macOS/Linux es
`source .venv/bin/activate`. Luego:

```bash
pip install -r requirements.txt
```

Dependencias: `requests` (scraper), `matplotlib` + `scipy` + `numpy` (viz).
El dashboard no requiere instalar nada, es un único HTML autocontenido.

### Nota sobre `db/puestos_2026.db`

El archivo pesa cerca de 88 MB, así que no viaja dentro del repositorio de
git (está en `.gitignore`). Hay dos formas de conseguirlo:

1. Regenerarlo corriendo `python scraper/scraper.py` (toma 2-3 minutos y
   siempre da el mismo resultado).
2. Descargar la copia ya armada desde el Release de GitHub:
   [`puestos_2026.db` (v1.0, 87.9 MB)](https://github.com/daniloremolina1905-max/remolina_prueba_utl_2026/releases/download/v1.0/puestos_2026.db).
   Solo hay que colocarla en `db/puestos_2026.db`.

## Pipeline de ejecución


**1) Extraer y cargar** los 4 municipios (Cámara + Senado) en `db/puestos_2026.db`:
```bash
python scraper/scraper.py
```

**2) (opcional)** Solo contar puestos/mesas sin descargar (bonus +3):
```bash
python scraper/scraper.py --preflight
```

**3) Verificar una consulta SQL manualmente** (opcional, ya las corre el manifest en el paso 6):
```bash
sqlite3 db/puestos_2026.db < sql/tarea_3_1.sql
```

**4) Generar `dashboard/data.json`** y embeberlo en `dashboard/index.html`:
```bash
python dashboard/export_data.py
```

**5) Generar las visualizaciones**:
```bash
python viz/heatmap.py
python viz/scatter.py
```

**6) Editar la sección META** de `outputs/generar_manifest.py` (nombre, email, url del repo) y generar el manifiesto de evaluación:
```bash
python outputs/generar_manifest.py
```

**7) Abrir el dashboard**: doble clic en `dashboard/index.html`. Funciona sin servidor, directo en Chrome o Firefox.

Re-ejecutar `scraper.py` en cualquier momento es seguro: las filas de `votos`
tienen `UNIQUE(mesa_id, eleccion, codpar, candidato_id)` y se insertan con
`INSERT OR IGNORE`, así que no se duplican registros (verificado: segunda
corrida inserta 0 filas nuevas, ver `carga_log`).

## API

**Base:** `https://resultadospreccongreso2026.registraduria.gov.co`
(sitio oficial de resultados en tiempo real del Congreso 2026. Está hecho en React y consume una API JSON pública, sin necesidad de login).

### Endpoints usados

| Endpoint | Método | Descripción |
|---|---|---|
| `/json/nomenclator.json` | GET | Estructura electoral completa: jerarquía país > departamento > municipio > zona > comuna > puesto > mesa, catálogo global de partidos (`partidos[]`) y de elecciones (`elec[]`). |
| `/json/web/config.json` | GET | Estado general del sitio (fase de escrutinio, si está abierto, etc.). |
| `/json/ACT/{electionSiglas}/{scopeCode}.json` | GET | Resultados de escrutinio (actas) para un ámbito. `electionSiglas` = `SE` (Senado) o `CA` (Cámara). `scopeCode` = código del ámbito **con sufijo `.json` literal** (ej. `00` nacional, `0700` Boyacá, `0700001` Tunja, `0700001010005` un puesto de Tunja). El servidor valida `scopeCode` con una regex que exige el sufijo `.json`, de lo contrario responde 404. |

Este mapeo se obtuvo inspeccionando las peticiones de red del sitio (F12,
pestaña Network) y el bundle JS minificado (`assets/index-*.js`), que expone
el contrato `ts-rest` con las rutas `getScopeAct` y `getHome`.

### Cómo obtener el nomenclátor de un municipio

1. `GET /json/nomenclator.json` devuelve `data.amb`, un arreglo por elección
   (`elec: 1` = Senado). Cada elemento tiene `ambitos[]`, un arreglo **plano**
   indexado por el campo `i`.
2. El departamento Boyacá es el ámbito con `l=2` (nivel DEPARTAMENTO) y
   `c="0700"`.
3. Sus municipios están en `boyaca.h[0].p` (índices de nivel `l=3` dentro de
   `ambitos`). Por ejemplo, Tunja es `{"i":1135,"n":"TUNJA","c":"0700001",...}`.
4. Los puestos de un municipio se resuelven recorriendo sus zonas (`h[0].p`,
   nivel `l=4`) y de ahí los puestos (`h[0].p` de cada zona, nivel `l=6`).
   Cada puesto trae `m` = número de mesas.

### 8+ campos JSON relevantes

De `/json/ACT/{SIGLAS}/{scopeCode}.json`:

| Campo | Descripción |
|---|---|
| `totales.act.metota` / `mesesc` | Mesas totales / mesas escrutadas del ámbito |
| `totales.act.votant` / `pvotant` | Votantes totales / % participación |
| `totales.act.votnul`, `votblan` | Votos nulos, votos en blanco |
| `camaras[].partotabla[].act.codpar` | Código de partido (**usa el campo `i` del catálogo global**, no `codpar`) |
| `camaras[].partotabla[].act.vot` / `pvot` | Votos totales del partido / % |
| `camaras[].partotabla[].act.cantotabla[].codcan` | Código de candidato (`0` = "solo por lista") |
| `camaras[].partotabla[].act.cantotabla[].nomcan` / `apecan` | Nombre / apellido del candidato |
| `camaras[].partotabla[].act.cantotabla[].vot` | Votos del candidato |

De `/json/nomenclator.json`: `ambitos[].i/n/c/l/m/h/p`, `partidos[].codpar/i/nombre/color`.

### Cabeceras HTTP

No requiere autenticación ni API key. El scraper envía `User-Agent` y
`Accept: application/json` estándar, por buena práctica, aunque el servidor
no los exige.

### Hallazgo importante: granularidad real de la API

La API pública del preconteo **expone resultados hasta el nivel de PUESTO de
votación**, no hasta MESA individual (formulario E-14). Se probaron varios
`scopeCode` con sufijos de mesa (`...05001`, etc.) y todos devolvieron 404.
Esto es consistente con cómo Colombia publica preconteos: el detalle por
mesa individual no forma parte del API de resultados agregados en tiempo
real.

Los Retos 3.2 (dominancia por mesa) y 5.2 (scatter por mesa) piden esa
granularidad, así que el ETL **reparte de forma determinística** el total
real de cada candidato en su puesto entre las mesas de ese puesto (semilla =
`código_puesto|eleccion|codpar|codcan`, función `repartir_votos_en_mesas()`
en `scraper/scraper.py`). La suma de los votos sintéticos por mesa siempre
cuadra exacto con el total real y oficial del puesto: solo la distribución
*entre* mesas de un mismo puesto es sintética. Esto también queda como
comentario en `db/schema.sql`.

### Si la API no responde

Si hay una caída, un cambio de red o un límite de peticiones, `scraper.py`
reintenta con backoff exponencial. Si se agotan los reintentos, usa una
copia guardada en `.scraper_cache/` de la última respuesta exitosa para esa
URL (se guarda sola en cada corrida exitosa, no hay que hacer nada extra).
`nomenclator.json` se cachea aparte en `.scraper_cache/nomenclator_cache.json`.

Para desarrollar o probar el parser sin depender de la red también están los
ejemplos reales en `sample_data/` (fixtures pequeños, de solo lectura).

## Municipios en la BD

| Municipio | Código DIVIPOLA | Puestos | Mesas |
|---|---|---|---|
| TUNJA | 0700001 | 26 | 424 |
| PAIPA | 0700181 | 7 | 95 |
| SOGAMOSO | 0700277 | 18 | 301 |
| DUITAMA | 0700079 | 22 | 287 |
| **Total** | | **73** | **1107** |

(Verificado en vivo con `python scraper/scraper.py --preflight`.)

## Hallazgos principales

- **Pacto Histórico lidera Senado en los 4 municipios** de la muestra, con
  Alianza Verde/coalición homologada (`codpar` 57, "Alianza Por Colombia" en
  el tarjetón real de Senado) y Centro Democrático disputando el segundo
  lugar según el municipio.
- **Arrastre Verde CA a SE** (Reto 3.1): en Duitama y Tunja el ratio SE/CA está
  mayoritariamente por encima de 1.0 (el partido "creció" en Senado respecto
  a Cámara en la mayoría de sus puestos), mientras que en Paipa el patrón se
  invierte (ratio consistentemente menor a 1, entre 0.18 y 0.63). Probablemente
  se debe a que el candidato más fuerte de Cámara en Paipa (Yamit Noe Hurtado
  Neira, cerca del 38% del total de Cámara en ese municipio, ver
  `viz/heatmap_municipios.png`) tiene un arrastre personal mucho más fuerte
  que el de su lista de Senado.
- **Correlación Cámara-Senado por mesa** (Reto 5.2): `r ≈ 0.69`, correlación
  moderada-alta y positiva. Las mesas con mayor participación en Cámara
  también tienden a tener mayor participación en Senado, como era de
  esperarse al votarse el mismo día con el mismo electorado, aunque no es una
  relación 1:1 perfecta (parte de esa variación acá también viene de la
  disgregación sintética por mesa, ver sección "API" arriba).
- **Por qué el top de Cámara no siempre coincide con el top de atribución SE
  consolidada** (Reto 3.3, bonus +2): la fórmula `A_ij = (votos_cand /
  votos_partido_CA) * votos_SE_partido_homologado` pondera a cada candidato
  por su *peso relativo dentro de su propio partido en Cámara*, y luego lo
  multiplica por el tamaño del "pastel" de Senado de ese partido. Un
  candidato puede ser top-1 en votos absolutos de Cámara pero pertenecer a un
  partido con un total de Senado homologado pequeño (atribución baja), mientras
  que un candidato con menos votos absolutos pero que pesa mucho *dentro de un
  partido con un Senado grande* (como Pacto Histórico o Alianza Verde en esta
  muestra) puede desplazarlo en el ranking de atribución. Es decir: la métrica
  de Cámara mide fuerza personal absoluta; la atribución SE mide fuerza
  personal relativa *ponderada por el tamaño de la maquinaria de Senado de su
  partido*.
- **Supuesto de homologación de partidos** (Reto 3.3): el enunciado fija
  explícitamente Alianza Verde (`5` a `57`) y Pacto Histórico (`87` a `92`).
  Para el resto de partidos (incluyendo Centro Democrático `10` y
  Conservador `2`, que en este ciclo comparten el mismo `codpar` en ambas
  elecciones) se asume homologación por identidad de código. Ver comentario
  en `sql/tarea_3_3.sql`.

## Bonus implementados

| Bonus | Dónde | Pts |
|---|---|---|
| `--preflight` en el scraper | `scraper/scraper.py` (flag `--preflight`) | +3 |
| 3+ índices SQLite justificados | `db/schema.sql` (4 índices, cada uno con comentario de qué consulta optimiza) | +2 |
| Explicación top CA vs. top atribución SE | Esta sección, "Hallazgos principales" | +2 |
| Dark mode con CSS custom properties | `dashboard/index.html` (`--papel`, `--panel`, `--tinta`, etc. + `[data-tema="oscuro"]`, botón "Modo oscuro") | +3 |
| Botón Exportar CSV funcional | `dashboard/index.html` (`#btn-csv`, exporta la tabla de arrastre visible) | +2 |
| Extender el scraper a municipios adicionales | `scraper/scraper.py --municipios <NOMBRE>` acepta **cualquier** municipio de Boyacá válido (no solo los 4 por defecto), resolviéndolo dinámicamente contra `nomenclator.json` (`resolver_municipio()`) | +3 |

**Nota técnica sobre el dashboard:** los gráficos se dibujan con SVG nativo,
sin Chart.js ni Plotly por CDN, para que `index.html` sea realmente
autocontenido y funcione sin conexión a internet. En pruebas se detectó que
las dependencias de CDN pueden fallar en silencio según la red de quien lo
abra, lo cual violaría el requisito de "sin errores en DevTools Console".
