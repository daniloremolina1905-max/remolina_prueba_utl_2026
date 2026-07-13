# sample_data/ (solo lectura)

Fixtures reales, capturados de la API en vivo, para desarrollar/probar el
parser sin depender de la red:

- `ejemplo_nomenclator_boyaca.json`: extracto de `nomenclator.json` (el real
  pesa ~9 MB) con solo Boyacá, sus 4 municipios objetivo y 2 puestos de
  ejemplo por zona.
- `ejemplo_resultado_puesto_SE.json` y `_CA.json`: respuesta real y completa
  de `/json/ACT/{SIGLAS}/{codigo}.json` para un puesto pequeño (Paipa, "EL
  VENADO", 1 mesa), para inspeccionar la estructura de `camaras[].partotabla[]`.

Estos archivos son solo para referencia/desarrollo. La caché funcional que
usa `scraper.py` como fallback automático en producción vive en
`.scraper_cache/` (no versionada, se regenera sola en cada corrida exitosa).
