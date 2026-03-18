# Matriz de pruebas — Herramienta de Tareas (MCP + DevTools)

## 1) Objetivo
Validar y documentar todas las combinaciones posibles de bloques, propiedades, condiciones y anidaciones en la herramienta de Tareas.

## 2) Alcance de esta matriz
- Entorno: Sandbox / QA (no productivo)
- Actor: Usuario con permisos de creación/edición de tareas
- Plataforma: Web (desktop) y resultado en app móvil
- Cobertura: reglas funcionales, validaciones UI y comportamiento de guardado/despliegue

## 3) Diccionario de estado
- ✅ Válida: la combinación guarda y se despliega correctamente
- ⚠️ Parcial: guarda con restricciones o comportamiento inesperado menor
- ❌ Inválida: bloquea por validación o error
- 🐞 Bug: comportamiento incorrecto respecto a la regla esperada

## 4) Campos a capturar por prueba
Usa esta tabla como plantilla (copiar/pegar por cada caso):

| ID | Tipo bloque padre | Propiedad padre | Condición | Bloque hijo (SI) | Propiedad hijo (SI) | Bloque hijo (NO) | Propiedad hijo (NO) | Profundidad | Precondiciones | Pasos resumidos | Resultado esperado | Resultado real | Estado | Evidencia (URL/captura) | Request/Endpoint | Payload clave | Observaciones |
|---|---|---|---|---|---|---|---|---:|---|---|---|---|---|---|---|---|---|
| TSK-001 | Pregunta Sí/No | Requerida | Respuesta=Sí | Captura | Foto | Lista única | Opción única | 1 | Usuario editor | Crear bloque + configurar ramas | Se muestran botones esperados y permite guardar | Panel de Si/No no muestra UI de ramas al crear. Mecanismo inferido via hidden inputs parentCaptureDataType + typeConditionSelected | ⚠️ Parcial | — | /moduleCapture/update | pendiente | Requiere exploración adicional del flujo de ramas |
| TSK-DIS-001 | Disponibilidad | mandatory=true, hasPrecapture=true | — | — | — | — | — | 0 | — | Leer window.module.moduleCapture | Block serializado con precaptureType, countProductLvl, productOption | ✅ Válida | — | — | — | elementId=2075612, captureDataType=17, precaptureType='3'(Llenado previo), countProductLvl='3', productOption=1 | Tipo especial KPI |

## 5) Paquete mínimo de combinaciones (MVP)

### 5.1 Bloques simples
1. Texto informativo sin condiciones
2. Pregunta Sí/No sin hijos
3. Pregunta Sí/No con solo rama Sí
4. Pregunta Sí/No con solo rama No
5. Pregunta Sí/No con ambas ramas
6. Lista selección única con 1 opción
7. Lista selección única con múltiples opciones
8. Bloque Foto obligatorio
9. Bloque Foto opcional

### 5.2 Dependencias y validaciones
10. Guardar sin título de tarea
11. Guardar con bloque incompleto
12. Eliminar bloque padre con hijos
13. Duplicar bloque con condiciones
14. Reordenar bloques con drag & drop
15. Cambiar tipo de propiedad tras configurar hijos

### 5.3 Anidaciones
16. Profundidad 1 (padre -> hijos)
17. Profundidad 2 (padre -> hijo -> nieto)
18. Profundidad máxima permitida (descubrir límite)
19. Mezcla de tipos en ramas anidadas
20. Condiciones cruzadas (múltiples sí/no consecutivos)

### 5.4 Persistencia y despliegue
21. Guardar y recargar web mantiene estructura
22. Publicar/desplegar y validar en móvil
23. Edición posterior de tarea publicada
24. Compatibilidad entre versiones (si aplica)

### 5.5 Resiliencia
25. Sesión expirada durante edición
26. Error de red al guardar
27. Campos largos / caracteres especiales
28. Opciones vacías o duplicadas en listas

## 6) Estrategia de ejecución
1. Crear una tarea base vacía.
2. Ejecutar combinaciones de menor a mayor complejidad.
3. Por cada caso, capturar:
   - Snapshot visual (antes/después)
   - Requests `xhr/fetch` relevantes
   - Payload enviado al guardar
4. Marcar estado y observaciones inmediatamente.
5. Consolidar reglas descubiertas al final del día.

## 7) Checklist de sesión de pruebas
- [ ] Login en entorno de pruebas
- [ ] DevTools abierto (Network + Console)
- [ ] Filtro de `xhr/fetch` activo
- [ ] Preservar logs habilitado
- [ ] Plantilla de matriz abierta
- [ ] Capturas/videncias almacenadas
- [ ] Casos marcados con estado

## 8) Criterios de salida
- Cobertura de todos los tipos de bloque disponibles
- Identificación de límites de anidación
- Lista de combinaciones válidas e inválidas confirmadas
- Registro de endpoints/payloads clave para futura automatización

## 9) Hallazgos (sección viva)

### Cierre Semana 1 (2026-03-17)
- **Estado**: ✅ Cerrada con **20 ejemplos reales trazables** (MCP Chrome + Network).
- **Tarea validada de cierre**: "FUNDAMENTALES X SKU DH" — task UI ID **177281**, moduleId **447911**.
- **Resultado final de conteo**: 20/20 exitosos en catálogo (`docs/catalogo_bloques_template.json`), con historial de fallo+retry documentado para tipo 34.
- **Regla aplicada**: ejemplo sin request/response no cuenta; toda evidencia quedó trazada por `reqid`.

#### Tabla ejecutiva 20/20

| Métrica | Valor |
|---|---:|
| Objetivo mínimo Semana 1 | 20 |
| Ejemplos reales capturados | 20 |
| Ejemplos exitosos finales | 20 |
| Ejemplos fallidos finales | 0 |
| Tarea (UI ID / moduleId) | 177281 / 447911 |
| Endpoint principal validado | `POST /moduleCapture/update` |
| Retry crítico resuelto | Tipo 34 (`reqid 1607` → `reqid 1613`) |

#### Evidencia clave de red (cierre)
- **Batch principal (ejemplos 1–20)**: requests `1581..1605` y `1607` sobre `POST /moduleCapture/update` (`type=element`).
- **Fallo inicial tipo 34**: `reqid=1607`, HTTP 500, respuesta `An error has occurred`.
- **Retry exitoso tipo 34**: `reqid=1613`, HTTP 200, respuesta `[]`.
- **Verificación de persistencia**: `reqid=1614` (`syncTaskData moduleDefinition`) confirma `elementId=2076179` con `captureDataType="34"`.
- **Control de contaminación**: bloque temporal restaurado a estado neutral (`captureDataType="1"`, nombre `TMP-W1-NEUTRAL`).

### Datos de entorno confirmados
- **URL de creación**: `https://webapp.storecheck.com/moduleCapture/create`
- **Versión plataforma**: 1.50.19
- **Tarea base exploración inicial**: "Exhibiciones Walmart PRUEBA" — task UI ID: 214669, module ID interno: 447349
- **Tarea usada para cierre Semana 1**: "FUNDAMENTALES X SKU DH" — task UI ID: 177281, module ID interno: 447911
- **Bloque temporal de pruebas de cierre**: elementId 2076179
- **Objeto JS con toda la estructura**: `window.module.moduleCapture`

### Tipos de bloque (39 confirmados)

| captureDataType | Nombre | Grupo |
|---|---|---|
| 36 | Código de barras | Acciones simples |
| 35 | Código QR | Acciones simples |
| 2 | Decimal | Acciones simples |
| 1 | Entero | Acciones simples |
| 8 | Fecha | Acciones simples |
| 10 | Fecha y Hora | Acciones simples |
| 37 | Firma | Acciones simples |
| 12 | Foto | Acciones simples |
| 7 | Hecho | Acciones simples |
| 9 | Hora | Acciones simples |
| 5 | Lista de ranking | Acciones simples |
| 4 | Lista de selección múltiple | Acciones simples |
| 3 | Lista de selección única | Acciones simples |
| 40 | PDF Online | Acciones simples |
| 38 | Reporte SQL | Acciones simples |
| 39 | Reporte URL | Acciones simples |
| 13 | Satisfacción | Acciones simples |
| 6 | Si / No | Acciones simples |
| 11 | Texto | Acciones simples |
| 31 | Abordos | Acciones vinculadas a un KPI |
| 18 | Agotamiento | Acciones vinculadas a un KPI |
| 28 | Caducidad (entero) | Acciones vinculadas a un KPI |
| 27 | Caducidad (fecha) | Acciones vinculadas a un KPI |
| 16 | Catalogación | Acciones vinculadas a un KPI |
| 15 | Comunicación de precio | Acciones vinculadas a un KPI |
| 17 | Disponibilidad | Acciones vinculadas a un KPI |
| 22 | Fondos (decimal) | Acciones vinculadas a un KPI |
| 21 | Fondos (entero) | Acciones vinculadas a un KPI |
| 20 | Frentes (decimal) | Acciones vinculadas a un KPI |
| 19 | Frentes (entero) | Acciones vinculadas a un KPI |
| 24 | Inventario (decimal) | Acciones vinculadas a un KPI |
| 23 | Inventario (entero) | Acciones vinculadas a un KPI |
| 26 | Pedido (decimal) | Acciones vinculadas a un KPI |
| 25 | Pedido (entero) | Acciones vinculadas a un KPI |
| 14 | Precios | Acciones vinculadas a un KPI |
| 30 | Ventas (decimal) | Acciones vinculadas a un KPI |
| 29 | Ventas (entero) | Acciones vinculadas a un KPI |
| 33 | Acciones múltiples | Otro |
| 34 | Reconocimiento de imagen | Otro |

### Reglas confirmadas
- El campo **Nombre de la acción es obligatorio** — validación en frontend: "Campo es obligatorio" al intentar guardar con nombre vacío.
- El tipo predeterminado al agregar un nuevo bloque es **captureDataType="1" (Entero)**.
- **Tipo Texto** — propiedades en panel de config: Nombre (req), Fotos (Permitida/Obligatoria/Múltiples), Adjuntos, Captura previa, Asociar productos, Info adicional, NA, Obligatorio.
- **Tipo Si/No** — panel idéntico al Texto. Sin UI de ramas visible al crear el bloque.
- **Tipo Entero** — tiene sección adicional "DEFINIR LÍMITES" con al menos una opción "Sin límites".
- El **autosave** se dispara ~2 segundos después de inactividad (llamadas a `/moduleCapture/update`).

### Endpoints confirmados
| Endpoint | Método | Función JS | Propósito |
|---|---|---|---|
| `/moduleCapture/update` | POST | `saveAllProfilesAllFormatsAjax` | Guardar configuración de perfiles/formatos |
| `/moduleCapture/scopeServices` | POST | `saveAjaxScopeElementProAndExh` | Guardar alcance exhibición/ubicación |

### Hidden inputs del bloque (para serialización)
`elementId`, `orderElement`, `attachmentId`, `precaptureType`, `precaptureTypeDsc`, `countProductLvl`, `showHubInfoType`, `showHubInfoTypeDsc`, `parentCaptureDataType`, `typeConditionSelected`

### Restricciones confirmadas
- En la tarea de cierre (`moduleId=447911`) el selector UI de `captureDataType` **no expone** el tipo `34` (Reconocimiento de imagen), aunque backend sí lo persiste cuando se envía explícitamente en `elementsArray`.

### Pendientes prioritarios
1. **Semana 2 — profundización de reglas de UI por módulo**: mapear por qué `captureDataType=34` no aparece en ciertos módulos aunque sea persistible vía backend.
2. **Semana 2 — validación funcional de tipo 34**: comprobar comportamiento completo de configuración/ejecución (no solo persistencia).
3. **Semana 2 — robustez**: cubrir casos de resiliencia (sesión expirada, error de red, campos extremos) con evidencia de red por caso.
4. **Semana 2 — publicación/despliegue**: validar impacto en flujo de publicación y consumo móvil para combinaciones críticas.

### Bugs encontrados
- **Candidato a bug funcional/UI**: inconsistencia entre catálogo backend y UI de selección de tipos para `captureDataType=34` en `moduleId=447911`.
