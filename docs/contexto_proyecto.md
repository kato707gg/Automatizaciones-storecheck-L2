# Contexto del proyecto — Automatización de tareas Storecheck con lenguaje natural

## 1) Propósito
Construir una solución que permita **definir tareas de Storecheck usando lenguaje natural** y que el sistema las **configure automáticamente** en la página de creación/edición de tareas.

Objetivo práctico:
- El usuario escribe cómo quiere su tarea.
- El sistema interpreta ese texto.
- El sistema valida la estructura.
- El sistema ejecuta la configuración directamente en Storecheck (sandbox/QA).

---

## 2) Visión de uso final
Habrá una **interfaz** (aún no construida) donde el usuario escribirá algo como:

> "Crea una tarea con una pregunta Sí/No; si responde Sí, pedir foto obligatoria; si responde No, pedir lista única con 3 opciones."

Luego, cuando el usuario esté dentro de la página de tareas de Storecheck, el sistema aplicará automáticamente esa definición en la UI.

---

## 3) Estado actual del proyecto

### Semana 1 (cerrada)
- Catálogo de bloques documentado.
- Schema JSON documentado con evidencia real.
- 20 ejemplos reales trazables capturados.
- Matriz de pruebas consolidada.

Referencias:
- `docs/matriz_pruebas_tareas.md`
- `docs/catalogo_bloques_template.json`

### Semana 2 (en curso)
Pendientes de implementación:
1. Parser LLM (texto natural -> JSON de tarea)
2. Validador (schema + reglas de negocio)
3. Ejecutor sandbox (aplica configuración en Storecheck)
4. Bucle de corrección (si falla validación/ejecución, corregir y reintentar)

---

## 4) Restricciones operativas críticas
1. **Las pruebas reales deben ejecutarse con MCP de Google Chrome**.
2. Sin evidencia de red (request/response), la prueba no cuenta como validada.
3. Priorizar siempre entorno sandbox/QA (no productivo).
4. Documentar cualquier fallo con evidencia y resultado de retry.

---

## 5) Flujo técnico objetivo (MVP)
1. **Entrada**: texto natural del usuario.
2. **Parser**: genera JSON compatible con el schema del proyecto.
3. **Validador**: revisa campos obligatorios, tipos, condiciones y anidación.
4. **Ejecutor**: aplica pasos en la web de Storecheck con MCP Chrome.
5. **Verificación**: confirma guardado por UI + network.
6. **Salida**: reporte final con cambios aplicados y evidencia.

---

## 6) Criterios de éxito del proyecto
- Reducir al mínimo la configuración manual de tareas.
- Mantener alta trazabilidad (qué se pidió, qué se creó, qué se guardó).
- Lograr ejecución confiable de tareas comunes desde lenguaje natural.
- Poder depurar rápido con evidencia de red y logs de validación.

---

## 7) Instrucciones para nuevos chats (copiar/pegar)
Usar este contexto como base:

- Proyecto: automatizar creación de tareas Storecheck desde lenguaje natural.
- Semana 1: cerrada (catálogo + schema + 20 ejemplos reales).
- Semana 2: implementar parser LLM, validador y ejecutor sandbox.
- Restricción clave: pruebas solo con MCP de Google Chrome, con evidencia request/response.
- Archivos fuente: `docs/matriz_pruebas_tareas.md` y `docs/catalogo_bloques_template.json`.

Pedir siempre:
- pasos concretos,
- ejecución real,
- evidencia,
- y actualización de documentación al final.

---

## 8) Tecnologías y arquitectura objetivo

### Stack principal (MVP)
- **Backend/API**: Python 3.11+ con FastAPI.
- **Modelado y validación**: Pydantic + JSON Schema (alineado con `docs/catalogo_bloques_template.json`).
- **Persistencia de evidencias**: JSONL/archivos estructurados por corrida (fase MVP).
- **UI interna (opcional MVP)**: interfaz mínima para prompt, preview de JSON y ejecución.

### Arquitectura por capas
1. **Entrada**: texto natural del usuario.
2. **Parser IA**: convierte texto a JSON objetivo de tarea.
3. **Validador determinista**: aplica schema + reglas de negocio Storecheck.
4. **Ejecutor determinista**: opera la UI de Storecheck en sandbox.
5. **Verificador**: confirma resultado por UI y por request/response.
6. **Reporte**: entrega resultado final con trazabilidad.

### Ejecutor web
- Canal principal: **MCP de Google Chrome**.
- Objetivo: ejecución reproducible con pasos explícitos (sin decisiones autónomas en tiempo real).
- Estrategia: acciones atómicas + checkpoints + retry controlado.
- Resultado esperado: misma entrada validada produce mismos pasos y mismo resultado operativo.

### Límite de uso de IA (política del proyecto)
- **Permitido**: interpretar lenguaje natural y proponer JSON de tarea.
- **No permitido**: decidir clics o navegación en caliente durante la ejecución.
- **No permitido**: saltar validaciones schema/reglas por “criterio” del modelo.
- **Obligatorio**: toda ejecución pasa por validador determinista antes del ejecutor.

### Tecnologías alternativas (solo contingencia)
- Selenium/Playwright directo fuera de MCP se considera plan alterno, no camino principal del MVP.
- Cualquier cambio de canal debe mantener el mismo estándar de evidencia (UI + network).
