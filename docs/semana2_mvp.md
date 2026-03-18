# Semana 2 — MVP técnico inicial

## Objetivo de este arranque
Dejar una base funcional para el flujo:
1. Parser de lenguaje natural a IR (TaskIR)
2. Validador determinista de reglas críticas
3. Orquestador con contratos claros
4. Ejecutor H3 con playbook determinista + evidencia JSONL
5. Stub de autocorrección para extensión en siguiente hito

## Archivos creados
- core/semana2/models.py
- core/semana2/contracts.py
- core/semana2/parser_mvp.py
- core/semana2/validator.py
- core/semana2/orchestrator.py
- core/semana2/playbook.py
- core/semana2/executor_h3.py
- core/semana2/evidence.py
- core/semana2/autofix_stub.py
- core/semana2/demo_semana2.py

## Contratos I/O implementados

### Parser
Entrada:
- prompt (str)
- context (dict opcional)

Salida:
- ParseResult { ir, warnings }

### Validador
Entrada:
- TaskIR

Salida:
- ValidationResult { valid, issues, normalized_ir }

### Executor (contrato)
Entrada:
- TaskIR validado

Salida:
- ExecutionResult { executed, success, steps, final_snapshot }

Implementación actual:
- `PlaybookExecutor` (modo simulación por defecto)
- Construye plan determinista de acciones (`open`, `create`, `update`, `condition`, `save`, `verify`)
- Exige evidencia de red en `save_task` y `verify_task` para marcar éxito completo

### Auto-corrector (contrato)
Entrada:
- TaskIR + ExecutionResult

Salida:
- AutoFixResult { fixed_ir, reason, should_retry }

## Cómo probar el arranque (dry-run + artefactos)
Desde la raíz del proyecto:

python -m core.semana2.demo_semana2 "crear una tarea con pregunta sí/no, rama sí con foto obligatoria y rama no con lista única con 3 opciones" --output-dir docs/runs

Se generan:
- `*.jsonl` con evidencia por paso
- `*.summary.json` con resumen de ejecución

## Qué valida hoy
- Nombre de tarea obligatorio
- Al menos 1 bloque
- block_id únicos
- captureDataType permitido en MVP
- Lista única con mínimo 2 opciones
- Integridad de edges (parent/child existentes)
- Condiciones stage 0/1 solo con padre tipo 6 (Sí/No)

## Siguiente hito recomendado (H4)
Conectar `PlaybookExecutor.runner` a un bridge MCP Chrome real:
- ejecutar cada acción del playbook contra Storecheck sandbox
- capturar `reqid`, endpoint, payload y response por paso
- activar bucle de autocorrección sobre errores reales de red/UI

## Estado real MCP (actualizado)
- Se ejecutó corrida real en `moduleCapture/create` con sesión activa.
- Evidencia en `docs/runs/20260317_224716_semana2_e2e_real_permcheck.jsonl` y `docs/runs/20260317_224716_semana2_e2e_real_permcheck.summary.json`.
- `save_task` real se ejecuta y responde HTTP 200, pero devuelve `permit:false` (sin persistencia efectiva).
- `verify_task` real confirma que la definición no cambia (estado original intacto).

Implicación:
- El pipeline H3 ya está validado con tráfico real, pero el cierre funcional depende de usar un módulo/tarea con permisos de edición efectiva.

## Cierre en verde (MCP real)
- Se ejecutó el mismo flujo en una tarea nueva editable (`task_ui_id=218101`, `module_id=448010`).
- Evidencia en `docs/runs/20260317_225149_semana2_e2e_real_green.jsonl` y `docs/runs/20260317_225149_semana2_e2e_real_green.summary.json`.
- `save_task` exitoso: `reqid=868` (`POST /moduleCapture/update`, `type=moduleScopeType`, respuesta `[]`).
- `verify_task` exitoso: `reqid=869` (`GET /moduleCapture/syncTaskData?type=moduleDefinition&moduleId=448010`) con `moduleScopeTypeId=1`.
- Rollback validado: `reqid=870` + `reqid=871` regresando `moduleScopeTypeId=0`.

## Runner real conectado (registro automático de reqid)
Se añadió en `core/semana2/executor_h3.py`:
- `NetworkCallEvidence`
- `ScopeTypeBackend` (contrato de transporte)
- `ScopeTypePatternRunner` (patrón save/verify con `moduleScopeType`)

Uso esperado:
1. Implementar un backend que cumpla `ScopeTypeBackend` usando tu bridge MCP.
2. Construir `ScopeTypePatternRunner(module_id, original_scope_type, target_scope_type, backend, restore_on_verify=...)`.
3. Inyectarlo en `PlaybookExecutor(runner=...)`.

Resultado:
- `save_task` y `verify_task` quedan registrados automáticamente con `reqid`, `endpoint`, `request_payload_excerpt` y `response_excerpt` dentro de `ExecutionStepEvidence`.

## Backend MCP concreto implementado
Se añadió `core/semana2/mcp_backend.py` con:
- `McpScopeTypeBackend` (implementación real del backend)
- `CallableMcpChromeBridge` (adapter para conectar funciones MCP existentes)

Funciones implementadas (solicitadas):
1. `update_module_scope_type(module_id, scope_type_id)`
	- Ejecuta `POST /moduleCapture/update` vía `evaluate_script(fetch...)`.
	- Captura `reqid` por diff de red (`list_network_requests` antes/después).
	- Enriquece evidencia con `get_network_request(reqid)`.

2. `get_module_definition(module_id)`
	- Ejecuta `GET /moduleCapture/syncTaskData?type=moduleDefinition&moduleId=...`.
	- Captura `reqid` por diff de red y adjunta respuesta JSON para verificación.

Con esto, el `ScopeTypePatternRunner` ya puede operar en corridas reales y registrar reqids automáticamente sin código ad-hoc adicional.
