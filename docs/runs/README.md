# Evidencias de corridas — Semana 2

Esta carpeta almacena artefactos por corrida del flujo parser+validador+ejecutor.

## Formato de archivos
- `YYYYMMDD_HHMMSS_<case>.jsonl`
  - Un registro por paso de ejecución.
  - Campos esperados por línea:
    - `timestamp`
    - `step.action`
    - `step.endpoint`
    - `step.request_payload_excerpt`
    - `step.response_excerpt`
    - `step.reqid`
    - `step.success`
    - `step.notes`

- `YYYYMMDD_HHMMSS_<case>.summary.json`
  - Resumen consolidado de la corrida.

## Regla de validación de proyecto
Una corrida **solo cuenta como válida** si el guardado y la verificación incluyen evidencia de red real:
- `save_task` con `reqid` y respuesta HTTP capturada.
- `verify_task` con `reqid` y respuesta HTTP capturada.

## Nota operativa
Para corridas reales (no dry-run) se requiere sesión activa en Storecheck sandbox y ejecución vía MCP Google Chrome.
