"""
Actualizar catálogo de lugares (layout_places)
-----------------------------------------------
Compara el Maestro de lugares del cliente contra nuestro catálogo (layout_places)
y actualiza los campos que hayan cambiado:

  Cliente (Maestro)               →  Sistema (layout_places)
  ────────────────────────────────────────────────────────────
    STORECHECK ID                   →  Código Interno  (clave de búsqueda)
  NOMBRE DE LA TIENDA / Nombre Lugar →  Nombre Lugar
  ESTADO                          →  tags_ESTADO  +  tags_region_precios
  LATITUD                         →  Latitud
  LONGITUD                        →  Longitud
  STATUS OPERACIONES / Activo     →  Activo  (ACTIVO→1, INACTIVO→0, 1/0 pasan directo)
    RUTA / RUTA CALENDARIO FORMAX   →  tags_CANAL + tags_REGION + tags_SUBREGION + tags_RUTA

Cuando una fila es modificada se pone "UPDATE" en la columna Acción.
El resultado se guarda en carpeta_salida con el nombre del layout_places original.
"""

import os
import shutil
import unicodedata
from difflib import SequenceMatcher
import openpyxl


# ── Columnas del archivo del cliente ─────────────────────────────────
# Las columnas marcadas como opcionales no son obligatorias; se usan si están presentes.
_COLS_CLIENTE = [
    "STORECHECK ID",
    "BRANCHID",           # opcional: alternativa a STORECHECK ID
    "CODIGO INTERNO",     # opcional: alternativa a STORECHECK ID
    "Código Interno",     # opcional: alternativa a STORECHECK ID
    "NOMBRE DE LA TIENDA",
    "Nombre Lugar",        # opcional: alternativa a NOMBRE DE LA TIENDA
    "ESTADO",
    "CANAL",               # opcional
    "CANAL 1",             # opcional: alternativa a CANAL
    "SUBCANAL",            # opcional
    "Canal II",            # opcional: alternativa a SUBCANAL
    "CADENA",              # opcional
    "Cadena",              # opcional: alternativa a CADENA
    "FORMATO CLIENTE",     # opcional
    "Formato",             # opcional: alternativa a FORMATO CLIENTE
    "FORMATO",             # opcional
    "AREA NIELSEN",        # opcional
    "Area Nielsen",        # opcional: alternativa a AREA NIELSEN
    "DETERMINANTE",        # opcional
    "CLIENTE SELL-IN (SAP)",  # opcional
    "RUTA CALENDARIO FORMAX",  # opcional
    "RUTA",               # opcional: alternativa a RUTA CALENDARIO FORMAX
    "LATITUD",
    "LONGITUD",
    "STATUS OPERACIONES",  # opcional: fuente para columna Activo
    "Activo",              # opcional: alternativa a STATUS OPERACIONES
]

# Columnas que DEBEN existir (al menos una de cada grupo alternativo)
_COLS_CLIENTE_REQUERIDAS = ["STORECHECK ID", "ESTADO", "LATITUD", "LONGITUD"]
_COLS_NOMBRE_TIENDA = ["NOMBRE DE LA TIENDA", "Nombre Lugar"]  # al menos una
_COLS_ACTIVO = ["STATUS OPERACIONES", "Activo"]                # ambas opcionales

# ── Columnas del sistema (layout_places) ─────────────────────────────
_COLS_SISTEMA = [
    "Código Interno",
    "Nombre Lugar",
    "Cadena",
    "Canal",
    "Formato",
    "Area Nielsen",
    "tags_ESTADO",
    "tags_ESTATUS",
    "tags_CANAL",
    "tags_REGION",
    "tags_RUTA",
    "tags_SUBREGION",
    "tags_region_precios",
    "tags_CANAL 1",
    "tags_CLIENTE SELL-IN (SAP)",
    "tags_DETERMINANTE",
    "tags_FORMATO",
    "Latitud",
    "Longitud",
    "Activo",
    "Acción",
]

# ── Mapeo: columna cliente → columna(s) sistema ───────────────────────
# El valor puede ser un str o una lista de str cuando se actualiza en varios lugares.
# Nota: "NOMBRE DE LA TIENDA" → "Nombre Lugar" se maneja por separado porque
# el nombre canónico se construye como: Código Interno + Cadena (catálogo) + Nombre Tienda.
_MAPEO = {
    "ESTADO":  ["tags_ESTADO", "tags_region_precios"],
    "CANAL": "tags_CANAL 1",
    "CLIENTE SELL-IN (SAP)": "tags_CLIENTE SELL-IN (SAP)",
    "LATITUD": "Latitud",
    "LONGITUD": "Longitud",
}

# ── Mapeo extra SOLO para filas nuevas (ADD) ────────────────────────
_MAPEO_ADD = (
    (("AREA NIELSEN",), "Area Nielsen"),
    (("SUBCANAL",), "Canal"),
    (("CADENA",), "Cadena"),
    (("FORMATO CLIENTE", "FORMATO"), "Formato"),
    (("DETERMINANTE",), "tags_DETERMINANTE"),
    (("FORMATO_EXACTO",), "tags_FORMATO"),
)

# ── Nombres de hoja esperados ────────────────────────────────────────
_HOJAS_CLIENTE = ("BD", "CATALOGO DE LUGARES")
_HOJA_SISTEMA = "Lugares"

# ── Límite de registros por archivo de salida ────────────────────────
_LIMITE_REGISTROS = 25_000


# ══════════════════════════════════════════════════════════════════════
# Utilidades internas
# ══════════════════════════════════════════════════════════════════════

def _encontrar_fila_encabezados(ws, columnas_clave: list[str], max_filas: int = 40) -> int:
    """
    Devuelve el número de fila (1-based) donde están los encabezados.
    Busca la fila con el mayor número de coincidencias con columnas_clave.
    Esto maneja archivos del cliente que tienen filas extra arriba del encabezado.
    """
    clave_lower = {c.strip().lower() for c in columnas_clave}
    mejor_fila = 1
    mejor_hits = 0

    for fila_idx, fila in enumerate(
            ws.iter_rows(min_row=1, max_row=max_filas, values_only=True), start=1):
        vals = {str(v).strip().lower() for v in fila if v is not None}
        hits = len(clave_lower & vals)
        if hits > mejor_hits:
            mejor_hits = hits
            mejor_fila = fila_idx

    return mejor_fila


def _mapear_indices(ws, fila_enc: int, nombres: set) -> dict[str, int]:
    """
    Dado el número de fila de encabezados, devuelve {nombre_columna: col_idx_1based}
    para los nombres que se encuentren en esa fila.
    """
    fila = list(ws.iter_rows(
        min_row=fila_enc, max_row=fila_enc, values_only=True))[0]
    mapa = {}
    for col_idx, v in enumerate(fila, start=1):
        if v is None:
            continue
        nombre = str(v).strip()
        if nombre in nombres:
            mapa[nombre] = col_idx
    return mapa


def _normalizar_encabezado(nombre: str) -> str:
    """
    Normaliza encabezados para comparación flexible:
    - elimina acentos
    - colapsa espacios
    - compara en mayúsculas
    """
    s = unicodedata.normalize("NFKD", str(nombre))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = " ".join(s.strip().split())
    return s.upper()


def _mapear_indices_alias(ws, fila_enc: int, alias_por_canonico: dict[str, tuple[str, ...]]) -> dict[str, int]:
    """
    Devuelve {nombre_canonico: col_idx_1based} permitiendo alias y variantes
    de mayúsculas/minúsculas, acentos y espacios.
    """
    fila = list(ws.iter_rows(
        min_row=fila_enc, max_row=fila_enc, values_only=True))[0]
    alias_norm = {
        _normalizar_encabezado(alias): canonico
        for canonico, aliases in alias_por_canonico.items()
        for alias in aliases
    }
    mapa = {}
    for col_idx, v in enumerate(fila, start=1):
        if v is None:
            continue
        nombre_norm = _normalizar_encabezado(v)
        canonico = alias_norm.get(nombre_norm)
        if canonico:
            mapa[canonico] = col_idx
    return mapa


def _mapear_indice_exacto(ws, fila_enc: int, encabezado_exacto: str) -> int | None:
    """Busca un encabezado exacto (case-sensitive) en la fila indicada."""
    fila = list(ws.iter_rows(
        min_row=fila_enc, max_row=fila_enc, values_only=True))[0]
    for col_idx, v in enumerate(fila, start=1):
        if v is None:
            continue
        if str(v).strip() == encabezado_exacto:
            return col_idx
    return None


def _normalizar_nombre_hoja(nombre: str) -> str:
    """
    Normaliza nombres de hoja para comparación flexible:
    - elimina acentos
    - colapsa espacios múltiples
    - compara en mayúsculas
    """
    s = unicodedata.normalize("NFKD", str(nombre))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = " ".join(s.strip().split())
    return s.upper()


def _normalizar_palabra(palabra: str) -> str:
    """
    Normaliza una palabra para comparación de duplicados (maneja singular/plural).
    Quita la 'S' final si la palabra tiene más de 3 letras.
    """
    palabra = palabra.upper().strip()
    if palabra.endswith('S') and len(palabra) > 3:
        return palabra[:-1]
    return palabra


def _palabras_similares(p1: str, p2: str) -> bool:
    """Verdadero si dos palabras son iguales o una es singular/plural de la otra."""
    return _normalizar_palabra(p1) == _normalizar_palabra(p2)


def _eliminar_duplicados_consecutivos(texto: str) -> str:
    """
    Elimina secuencias de palabras duplicadas consecutivas.
    Prueba longitudes desde la más larga posible hasta 1 para cubrir
    cadenas de cualquier número de palabras.
    Ejemplos:
      'SANTA CRUZ SANTA CRUZ CALVARIO'                         →  'SANTA CRUZ CALVARIO'
      'WELTON WELTON PROGRESO'                                 →  'WELTON PROGRESO'
      'FARMACIAS LA MAS BARATA FARMACIAS LA MAS BARATA MACRO'  →  'FARMACIAS LA MAS BARATA MACRO'
    """
    palabras = texto.split()
    n = len(palabras)
    if n < 2:
        return texto

    resultado = []
    i = 0
    while i < n:
        encontrado = False
        max_longitud = (n - i) // 2  # mayor secuencia posible desde la posición actual
        for longitud in range(max_longitud, 0, -1):
            if i + longitud * 2 <= n:
                seq1 = palabras[i:i + longitud]
                seq2 = palabras[i + longitud:i + longitud * 2]
                if all(_palabras_similares(seq1[j], seq2[j]) for j in range(longitud)):
                    resultado.extend(seq1)
                    i += longitud * 2
                    encontrado = True
                    break
        if not encontrado:
            resultado.append(palabras[i])
            i += 1

    return " ".join(resultado)


# Palabras que se ignoran al calcular siglas de una cadena
_STOP_SIGLAS = {
    'DE', 'DEL', 'LA', 'LAS', 'EL', 'LOS', 'Y', 'E', 'A',
    'EN', 'CON', 'SAN', 'SANTA', 'SANTO',
}


def _abreviatura_cadena(cadena: str) -> str:
    """
    Genera las siglas de una cadena tomando la primera letra de cada palabra
    significativa (omite artículos, preposiciones y conjunciones comunes).
    Retorna '' si el resultado tiene menos de 2 caracteres (muy genérico).
    Ejemplos:
      'FARMACIAS DEL AHORRO'  →  'FA'
      'FARMACIA GUADALAJARA'  →  'FG'
      'OXXO'                  →  ''   (una sola inicial, no se usa)
    """
    palabras = cadena.upper().split()
    siglas = "".join(p[0] for p in palabras if p and p not in _STOP_SIGLAS)
    return siglas if len(siglas) >= 2 else ""


def _quitar_siglas_cadena(nombre_tienda: str, cadena: str) -> str:
    """
    Si el nombre de tienda empieza con el nombre completo de la cadena o con
    sus siglas (como palabra(s) completa(s) al inicio), los elimina.
    Siempre compara en mayúsculas para no depender del formato del maestro.
    Ejemplos:
      ('FA JOSEFA',               'FARMACIAS DEL AHORRO')  →  'JOSEFA'
      ('FG LOMAS',                'FARMACIA GUADALAJARA')   →  'LOMAS'
      ('FARMACIAS LA MAS BARATA MACRO', 'FARMACIAS LA MAS BARATA')  →  'MACRO'
      ('JOSEFA',                  'FARMACIAS DEL AHORRO')   →  'JOSEFA'  (sin cambio)
    """
    if not cadena or not nombre_tienda:
        return nombre_tienda
    nombre_upper = nombre_tienda.upper()
    cadena_upper = cadena.upper()

    # 1. Verificar si el nombre empieza con el nombre completo de la cadena
    if nombre_upper == cadena_upper:
        return ""
    if nombre_upper.startswith(cadena_upper + " "):
        return nombre_tienda[len(cadena):].strip()

    # 2. Verificar con siglas de la cadena
    siglas = _abreviatura_cadena(cadena)
    if not siglas:
        return nombre_tienda
    if nombre_upper == siglas:
        return ""
    if nombre_upper.startswith(siglas + " "):
        return nombre_tienda[len(siglas):].strip()

    return nombre_tienda


def _normalizar(valor) -> str:
    """
    Convierte un valor de celda a str limpio y canónico para comparación.
    - None              → ""
    - int               → "12345"
    - float entero      → "12345"   (12345.0 → "12345")
    - str "12345.0"     → "12345"   (texto que parece entero → forma canónica)
    - str "12345"       → "12345"   (stripeado de espacios e invisibles)
    Garantiza que el mismo código almacenado como número o como texto siempre
    produzca el mismo resultado.
    """
    if valor is None:
        return ""
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, float):
        if valor == int(valor):
            return str(int(valor))
        return str(valor)
    # --- tipo str u otro ---
    s = str(valor)
    # Eliminar caracteres invisibles comunes (espacio no rompible, zero-width,
    # BOM, soft-hyphen) que podrían venir de copiar/pegar o de Excel.
    for ch in ('\xa0', '\u200b', '\u200c', '\u200d', '\ufeff', '\u00ad'):
        s = s.replace(ch, '')
    s = s.strip()
    # Si el texto parece un número entero ("12345" o "12345.0"), normalizarlo
    # a la forma canónica para que coincida con valores numéricos del otro archivo.
    try:
        f = float(s)
        if f == int(f):
            return str(int(f))
    except (ValueError, OverflowError):
        pass
    return s


def _normalizar_texto_catalogo(valor) -> str:
    """Normaliza textos de negocio para comparar catálogos (canal/cadena/formato)."""
    s = _normalizar_encabezado(_normalizar(valor))
    # Se conserva '/' porque distingue combinaciones válidas del catálogo.
    for ch in ("-", "_", ",", ".", ";", ":", "(", ")"):
        s = s.replace(ch, " ")
    s = " ".join(s.split())
    partes = [" ".join(p.split()) for p in s.split("/")]
    return "/".join(partes)


def _similaridad_texto(a: str, b: str) -> float:
    """Devuelve similitud entre 0 y 1 entre dos textos normalizados."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _normalizar_activo(estado_raw: str):
    """
    Convierte estado de activo desde texto a valor de sistema.
    Acepta: ACTIVO/INACTIVO/1/0 y devuelve 1/0.
    """
    if not estado_raw:
        return None
    estado_upper = _normalizar(estado_raw).upper()
    if estado_upper == "ACTIVO":
        return 1
    if estado_upper == "INACTIVO":
        return 0
    if estado_upper in ("1", "0"):
        return int(estado_upper)
    return None


def _descomponer_ruta(ruta_raw: str) -> dict[str, str]:
    """Descompone una ruta tipo NTE_BAJ_CEL01_CEL02 en tags de sistema."""
    if not ruta_raw:
        return {}
    ruta_norm = _normalizar(ruta_raw).strip().upper()
    if not ruta_norm:
        return {}
    partes = [parte.strip() for parte in ruta_norm.split("_") if parte.strip()]
    destinos = ("tags_CANAL", "tags_REGION", "tags_SUBREGION", "tags_RUTA")
    return {destino: parte for destino, parte in zip(destinos, partes) if parte}


def _cargar_datos_maestro_lugares(ruta_maestro: str) -> tuple[dict[str, dict[str, str]], str, int, int]:
    """Carga un maestro de lugares y devuelve sus datos normalizados por STORECHECK ID."""
    try:
        wb_cliente = openpyxl.load_workbook(ruta_maestro, read_only=True, data_only=True, keep_links=False)
    except PermissionError:
        raise RuntimeError("El Maestro de lugares está abierto en Excel. Ciérralo e intenta de nuevo.")
    except Exception as exc:
        raise RuntimeError(f"No se pudo abrir el Maestro de lugares: {exc}")

    try:
        hojas_cliente_norm = {
            _normalizar_nombre_hoja(h): h for h in wb_cliente.sheetnames
        }
        hoja_cliente = None
        for esperada in _HOJAS_CLIENTE:
            esperada_norm = _normalizar_nombre_hoja(esperada)
            if esperada_norm in hojas_cliente_norm:
                hoja_cliente = hojas_cliente_norm[esperada_norm]
                break
        if hoja_cliente is None:
            available = ", ".join(wb_cliente.sheetnames)
            esperadas = " o ".join(f"'{h}'" for h in _HOJAS_CLIENTE)
            raise RuntimeError(f"No se encontró ninguna hoja esperada ({esperadas}) "
                               f"en el Maestro de lugares.\n"
                               f"Hojas disponibles: {available}")

        ws_cliente = wb_cliente[hoja_cliente]
        fila_enc_cliente = _encontrar_fila_encabezados(ws_cliente, _COLS_CLIENTE)
        mapa_cliente = _mapear_indices_alias(ws_cliente, fila_enc_cliente, {
            "STORECHECK ID": ("STORECHECK ID", "BRANCHID", "CODIGO INTERNO", "CÓDIGO INTERNO"),
            "NOMBRE DE LA TIENDA": ("NOMBRE DE LA TIENDA",),
            "Nombre Lugar": ("Nombre Lugar", "NOMBRE LUGAR"),
            "ESTADO": ("ESTADO",),
            "CANAL": ("CANAL", "CANAL 1"),
            "SUBCANAL": ("SUBCANAL", "CANAL II"),
            "CADENA": ("CADENA",),
            "FORMATO CLIENTE": ("FORMATO CLIENTE",),
            "FORMATO": ("FORMATO",),
            "AREA NIELSEN": ("AREA NIELSEN",),
            "DETERMINANTE": ("DETERMINANTE",),
            "CLIENTE SELL-IN (SAP)": ("CLIENTE SELL-IN (SAP)",),
            "RUTA": ("RUTA CALENDARIO FORMAX", "RUTA"),
            "LATITUD": ("LATITUD",),
            "LONGITUD": ("LONGITUD",),
            "STATUS OPERACIONES": ("STATUS OPERACIONES",),
            "Activo": ("Activo", "ACTIVO"),
        })

        idx_formato_exacto = _mapear_indice_exacto(ws_cliente, fila_enc_cliente, "FORMATO")
        if idx_formato_exacto is not None:
            mapa_cliente["FORMATO_EXACTO"] = idx_formato_exacto

        faltantes = [c for c in _COLS_CLIENTE_REQUERIDAS if c not in mapa_cliente]
        if faltantes:
            raise RuntimeError(f"Columnas no encontradas en Maestro de lugares: {faltantes}\n"
                               f"Encabezados detectados en fila {fila_enc_cliente}.")
        if not any(c in mapa_cliente for c in _COLS_NOMBRE_TIENDA):
            raise RuntimeError(f"No se encontró ninguna columna de nombre de tienda "
                               f"({' / '.join(_COLS_NOMBRE_TIENDA)}) en el Maestro.\n"
                               f"Encabezados detectados en fila {fila_enc_cliente}.")

        datos_cliente: dict[str, dict[str, str]] = {}
        col_branch = mapa_cliente["STORECHECK ID"]
        for fila in ws_cliente.iter_rows(min_row=fila_enc_cliente + 1, values_only=True):
            branch_raw = fila[col_branch - 1]
            if branch_raw is None:
                continue
            branch_id = _normalizar(branch_raw)
            if not branch_id:
                continue
            datos_cliente[branch_id] = {
                col: _normalizar(fila[idx - 1])
                for col, idx in mapa_cliente.items()
            }

        return datos_cliente, hoja_cliente, fila_enc_cliente, col_branch
    finally:
        wb_cliente.close()


def _fusionar_maestros(principal: dict[str, dict[str, str]], secundario: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    """Fusiona dos maestros dando prioridad al primero cuando una columna se repite."""
    fusionado = {branch_id: dict(datos) for branch_id, datos in principal.items()}
    for branch_id, datos_extra in secundario.items():
        if branch_id not in fusionado:
            fusionado[branch_id] = dict(datos_extra)
            continue

        destino = fusionado[branch_id]
        for col, valor in datos_extra.items():
            if not destino.get(col) and valor:
                destino[col] = valor
    return fusionado


def _activo_a_tags_estatus(valor_activo: int | None) -> str | None:
    """Convierte 1/0 a ACTIVO/INACTIVO para la columna tags_ESTATUS."""
    if valor_activo == 1:
        return "ACTIVO"
    if valor_activo == 0:
        return "INACTIVO"
    return None


def _construir_catalogo_combinaciones_formato(wb) -> dict:
    """
    Construye catálogo de combinaciones válidas (Canal, Cadena, Formato)
    usando hojas ocultas Formatos, Cadenas y Canales.
    """
    def _buscar_hoja(nombre_objetivo: str):
        objetivo_norm = _normalizar_nombre_hoja(nombre_objetivo)
        for nombre in wb.sheetnames:
            if _normalizar_nombre_hoja(nombre) == objetivo_norm:
                return wb[nombre]
        return None

    ws_formatos = _buscar_hoja("Formatos")
    ws_cadenas = _buscar_hoja("Cadenas")
    ws_canales = _buscar_hoja("Canales")
    if not ws_formatos or not ws_cadenas or not ws_canales:
        return {"combos": [], "exactos": {}}

    def _resolver_mapa_hoja(ws, alias_por_canonico: dict[str, tuple[str, ...]], fallback_por_canonico: dict[str, int]):
        candidatos = [alias for aliases in alias_por_canonico.values() for alias in aliases]
        fila_enc = _encontrar_fila_encabezados(ws, candidatos, max_filas=20)
        mapa = _mapear_indices_alias(ws, fila_enc, alias_por_canonico)
        for canonico, fallback_col in fallback_por_canonico.items():
            if canonico not in mapa and fallback_col <= ws.max_column:
                mapa[canonico] = fallback_col
        return fila_enc, mapa

    fila_enc_cad, mapa_cad = _resolver_mapa_hoja(
        ws_cadenas,
        {
            "id": ("id", "chain_id", "cadena_id", "id cadena"),
            "dsc": ("chain_dsc", "cadena_dsc", "cadena", "description", "descripcion", "nombre cadena"),
        },
        {"id": 1, "dsc": 2},
    )
    fila_enc_can, mapa_can = _resolver_mapa_hoja(
        ws_canales,
        {
            "id": ("id", "channel_id", "canal_id", "id canal"),
            "dsc": ("channel_dsc", "canal_dsc", "canal", "description", "descripcion", "nombre canal"),
        },
        {"id": 1, "dsc": 2},
    )
    fila_enc_fmt, mapa_fmt = _resolver_mapa_hoja(
        ws_formatos,
        {
            "format_dsc": ("format_dsc", "formato_dsc", "formato", "nombre formato"),
            "chain_id": ("chain_id", "cadena_id", "id cadena"),
            "channel_id": ("channel_id", "canal_id", "id canal"),
        },
        {"format_dsc": 2, "chain_id": 3, "channel_id": 4},
    )

    cadenas_por_id = {}
    for fila in ws_cadenas.iter_rows(min_row=fila_enc_cad + 1, values_only=True):
        val_id = _normalizar(fila[mapa_cad["id"] - 1]) if "id" in mapa_cad else ""
        val_dsc = _normalizar(fila[mapa_cad["dsc"] - 1]) if "dsc" in mapa_cad else ""
        if val_id and val_dsc:
            cadenas_por_id[val_id] = val_dsc

    canales_por_id = {}
    for fila in ws_canales.iter_rows(min_row=fila_enc_can + 1, values_only=True):
        val_id = _normalizar(fila[mapa_can["id"] - 1]) if "id" in mapa_can else ""
        val_dsc = _normalizar(fila[mapa_can["dsc"] - 1]) if "dsc" in mapa_can else ""
        if val_id and val_dsc:
            canales_por_id[val_id] = val_dsc

    combos = []
    exactos = {}
    for fila in ws_formatos.iter_rows(min_row=fila_enc_fmt + 1, values_only=True):
        format_dsc = _normalizar(fila[mapa_fmt["format_dsc"] - 1]) if "format_dsc" in mapa_fmt else ""
        chain_id = _normalizar(fila[mapa_fmt["chain_id"] - 1]) if "chain_id" in mapa_fmt else ""
        channel_id = _normalizar(fila[mapa_fmt["channel_id"] - 1]) if "channel_id" in mapa_fmt else ""
        if not (format_dsc and chain_id and channel_id):
            continue

        chain_dsc = cadenas_por_id.get(chain_id, "")
        channel_dsc = canales_por_id.get(channel_id, "")
        if not (chain_dsc and channel_dsc):
            continue

        canal_norm = _normalizar_texto_catalogo(channel_dsc)
        cadena_norm = _normalizar_texto_catalogo(chain_dsc)
        formato_norm = _normalizar_texto_catalogo(format_dsc)
        if not (canal_norm and cadena_norm and formato_norm):
            continue

        combo = {
            "canal": channel_dsc,
            "cadena": chain_dsc,
            "formato": format_dsc,
            "canal_norm": canal_norm,
            "cadena_norm": cadena_norm,
            "formato_norm": formato_norm,
        }
        key = (canal_norm, cadena_norm, formato_norm)
        if key not in exactos:
            exactos[key] = combo
            combos.append(combo)

    return {"combos": combos, "exactos": exactos}


def _resolver_combinacion_mas_cercana(canal: str, cadena: str, formato: str, catalogo: dict):
    """
    Resuelve combinación contra catálogo válido.
    Retorna (combo, es_match_exacto).
    """
    combos = catalogo.get("combos", [])
    exactos = catalogo.get("exactos", {})
    if not combos:
        return None, False

    canal_norm = _normalizar_texto_catalogo(canal)
    cadena_norm = _normalizar_texto_catalogo(cadena)
    formato_norm = _normalizar_texto_catalogo(formato)

    if not (canal_norm or cadena_norm or formato_norm):
        return None, False

    key = (canal_norm, cadena_norm, formato_norm)
    if key in exactos:
        return exactos[key], True

    mejor_combo = None
    mejor_score = -1.0
    for combo in combos:
        score = 0.0
        peso = 0.0
        if formato_norm:
            score += 0.50 * _similaridad_texto(formato_norm, combo["formato_norm"])
            peso += 0.50
        if cadena_norm:
            score += 0.30 * _similaridad_texto(cadena_norm, combo["cadena_norm"])
            peso += 0.30
        if canal_norm:
            score += 0.20 * _similaridad_texto(canal_norm, combo["canal_norm"])
            peso += 0.20
        if peso == 0:
            continue
        score_final = score / peso
        if score_final > mejor_score:
            mejor_score = score_final
            mejor_combo = combo

    return mejor_combo, False


# ══════════════════════════════════════════════════════════════════════
# Función principal
# ══════════════════════════════════════════════════════════════════════

def actualizar_catalogo_lugares(
    ruta_maestro: str,
        ruta_layout_places: str,
    carpeta_salida: str,
    ruta_maestro_extra: str | None = None) -> bool:
    """
    Actualiza layout_places con los datos del Maestro de lugares.

    Args:
        ruta_maestro:       Ruta al archivo Maestro de lugares principal (cliente).
        ruta_maestro_extra:  Ruta al segundo Maestro de lugares opcional.
        ruta_layout_places: Ruta al archivo layout_places (nuestro catálogo).
        carpeta_salida:     Carpeta donde se guardará el resultado.

    Returns:
        True si el proceso terminó correctamente, False si hubo un error grave.
    """

    print("=" * 55)
    print("--- Actualizar Catálogo de Lugares ---")
    print("=" * 55)
    print(f"  Maestro 1: {os.path.basename(ruta_maestro)}")
    if ruta_maestro_extra:
        print(f"  Maestro 2: {os.path.basename(ruta_maestro_extra)}")
    print(f"  Catálogo: {os.path.basename(ruta_layout_places)}")

    # ── 1. Cargar Maestro(s) de lugares (cliente) ────────────────────
    datos_cliente, hoja_cliente, fila_enc_cliente, col_branch = _cargar_datos_maestro_lugares(ruta_maestro)
    if ruta_maestro_extra:
        datos_maestro_extra, _, _, _ = _cargar_datos_maestro_lugares(ruta_maestro_extra)
        datos_cliente = _fusionar_maestros(datos_cliente, datos_maestro_extra)

    print(f"  Registros en Maestro: {len(datos_cliente)}")

    # ── 2. Copiar layout_places a la carpeta de salida ────────────────
    ext_salida = os.path.splitext(ruta_layout_places)[1]
    nombre_salida = f"layout_places_actualizado{ext_salida}"
    ruta_salida = os.path.join(carpeta_salida, nombre_salida)
    try:
        shutil.copy2(ruta_layout_places, ruta_salida)
    except Exception as exc:
        raise RuntimeError(f"No se pudo copiar layout_places: {exc}")

    # ── 3. Abrir la copia y actualizar ───────────────────────────────
    try:
        wb_sistema = openpyxl.load_workbook(ruta_salida, keep_links=False)
    except Exception as exc:
        raise RuntimeError(f"No se pudo abrir layout_places: {exc}")

    if _HOJA_SISTEMA not in wb_sistema.sheetnames:
        available = ", ".join(wb_sistema.sheetnames)
        wb_sistema.close()
        raise RuntimeError(f"No se encontró la hoja '{_HOJA_SISTEMA}' en layout_places.\n"
                           f"Hojas disponibles: {available}")
    ws_sistema = wb_sistema[_HOJA_SISTEMA]

    fila_enc_sistema = _encontrar_fila_encabezados(ws_sistema, _COLS_SISTEMA)
    print(f"  Fila de encabezados (layout_places): {fila_enc_sistema}")

    mapa_sistema = _mapear_indices(ws_sistema, fila_enc_sistema, set(_COLS_SISTEMA))

    # Verificar columnas críticas del sistema
    for col_req in ("Código Interno", "Acción"):
        if col_req not in mapa_sistema:
            wb_sistema.close()
            raise RuntimeError(f"No se encontró la columna '{col_req}' en layout_places.\n"
                               f"Encabezados detectados en fila {fila_enc_sistema}.")

    col_codigo_int = mapa_sistema["Código Interno"]
    col_accion     = mapa_sistema["Acción"]

    # ── 3b. Detectar códigos del Maestro que NO están en el catálogo ──
    codigos_catalogo: set[str] = set()
    for fila in ws_sistema.iter_rows(min_row=fila_enc_sistema + 1, values_only=True):
        val = fila[col_codigo_int - 1]
        if val is not None:
            codigos_catalogo.add(_normalizar(val))

    faltantes_maestro = [branch_id for branch_id in datos_cliente if branch_id not in codigos_catalogo]

    if faltantes_maestro:
        ruta_faltantes = os.path.join(carpeta_salida, "codigos_no_encontrados_en_catalogo.xlsx")
        shutil.copy2(ruta_layout_places, ruta_faltantes)
        wb_falt = openpyxl.load_workbook(ruta_faltantes, keep_links=False)
        ws_falt = wb_falt[_HOJA_SISTEMA]
        catalogo_combos = _construir_catalogo_combinaciones_formato(wb_falt)
        ajustes_combinacion = 0

        fila_base_falt = fila_enc_sistema + 1
        for offset, branch_id in enumerate(faltantes_maestro):
            fila_destino = fila_base_falt + offset

            if fila_destino > ws_falt.max_row:
                ws_falt.append([None] * ws_falt.max_column)

            for col_idx in range(1, ws_falt.max_column + 1):
                ws_falt.cell(row=fila_destino, column=col_idx).value = None

            datos = datos_cliente.get(branch_id, {})

            if "Código Interno" in mapa_sistema:
                ws_falt.cell(row=fila_destino, column=mapa_sistema["Código Interno"]).value = branch_id

            for col_cliente, destino in _MAPEO.items():
                nuevo_val_str = datos.get(col_cliente, "")
                if not nuevo_val_str:
                    continue
                destinos = [destino] if isinstance(destino, str) else destino
                for col_sis in destinos:
                    if col_sis not in mapa_sistema:
                        continue
                    cell = ws_falt.cell(row=fila_destino, column=mapa_sistema[col_sis])
                    if col_sis in ("Latitud", "Longitud"):
                        try:
                            cell.value = float(nuevo_val_str)
                        except ValueError:
                            cell.value = nuevo_val_str
                    else:
                        cell.value = nuevo_val_str

            # Mapeos extra que solo aplican para archivo de altas (ADD)
            for fuentes_cliente, col_sis in _MAPEO_ADD:
                if col_sis not in mapa_sistema:
                    continue
                valor = ""
                for fuente in fuentes_cliente:
                    valor = datos.get(fuente, "")
                    if valor:
                        break
                if valor:
                    ws_falt.cell(row=fila_destino, column=mapa_sistema[col_sis]).value = valor

            # RUTA: descomponer en tags_CANAL / tags_REGION / tags_SUBREGION / tags_RUTA
            ruta_descompuesta = _descomponer_ruta(datos.get("RUTA", ""))
            for col_sis, valor in ruta_descompuesta.items():
                if col_sis in mapa_sistema:
                    ws_falt.cell(row=fila_destino, column=mapa_sistema[col_sis]).value = valor

            # Activo/tags_ESTATUS para ADD: STATUS OPERACIONES / Activo -> 1/0 y ACTIVO/INACTIVO
            if "Activo" in mapa_sistema or "tags_ESTATUS" in mapa_sistema:
                nuevo_activo = _normalizar_activo(
                    datos.get("STATUS OPERACIONES") or datos.get("Activo", "")
                )
                if nuevo_activo is not None:
                    if "Activo" in mapa_sistema:
                        ws_falt.cell(row=fila_destino, column=mapa_sistema["Activo"]).value = nuevo_activo
                    if "tags_ESTATUS" in mapa_sistema:
                        ws_falt.cell(row=fila_destino, column=mapa_sistema["tags_ESTATUS"]).value = (
                            _activo_a_tags_estatus(nuevo_activo)
                        )

            # Ajustar combinación Canal/Cadena/Formato contra catálogo válido de la plantilla
            if all(c in mapa_sistema for c in ("Canal", "Cadena", "Formato")):
                val_canal = _normalizar(ws_falt.cell(row=fila_destino, column=mapa_sistema["Canal"]).value)
                val_cadena = _normalizar(ws_falt.cell(row=fila_destino, column=mapa_sistema["Cadena"]).value)
                val_formato = _normalizar(ws_falt.cell(row=fila_destino, column=mapa_sistema["Formato"]).value)

                if val_canal and val_cadena and val_formato:
                    combo, exacto = _resolver_combinacion_mas_cercana(
                        val_canal,
                        val_cadena,
                        val_formato,
                        catalogo_combos,
                    )
                    if combo and not exacto:
                        ws_falt.cell(row=fila_destino, column=mapa_sistema["Canal"]).value = combo["canal"]
                        ws_falt.cell(row=fila_destino, column=mapa_sistema["Cadena"]).value = combo["cadena"]
                        ws_falt.cell(row=fila_destino, column=mapa_sistema["Formato"]).value = combo["formato"]
                        ajustes_combinacion += 1

            # Nombre canónico usando la Cadena + Nombre Tienda (fila ADD)
            if "Nombre Lugar" in mapa_sistema:
                nombre_tienda_nuevo = datos.get("NOMBRE DE LA TIENDA") or datos.get("Nombre Lugar", "")
                cadena = ""
                if "Cadena" in mapa_sistema:
                    cadena = _normalizar(ws_falt.cell(row=fila_destino, column=mapa_sistema["Cadena"]).value)
                if nombre_tienda_nuevo:
                    nombre_tienda_limpio = _quitar_siglas_cadena(nombre_tienda_nuevo, cadena)
                    partes = [p for p in [cadena, nombre_tienda_limpio] if p]
                    nombre_nuevo = _eliminar_duplicados_consecutivos(" ".join(partes))
                    nombre_nuevo = " ".join(nombre_nuevo.split())
                    if len(nombre_nuevo) > 60:
                        nombre_nuevo = nombre_nuevo[:60]
                    ws_falt.cell(row=fila_destino, column=mapa_sistema["Nombre Lugar"]).value = nombre_nuevo

            if "Acción" in mapa_sistema:
                ws_falt.cell(row=fila_destino, column=mapa_sistema["Acción"]).value = "ADD"

        ultima_fila_util = fila_base_falt + len(faltantes_maestro) - 1
        if ws_falt.max_row > ultima_fila_util:
            ws_falt.delete_rows(ultima_fila_util + 1, ws_falt.max_row - ultima_fila_util)

        wb_falt.save(ruta_faltantes)
        wb_falt.close()
        print(f"  Códigos del Maestro no encontrados en catálogo: {len(faltantes_maestro)}")
        if ajustes_combinacion:
            print(f"  Combinaciones Canal/Cadena/Formato ajustadas por similitud: {ajustes_combinacion}")
        print(f"  Archivo generado: {os.path.basename(ruta_faltantes)}")

    actualizados   = 0
    sin_cambios    = 0
    no_encontrados = 0
    filas_update = []

    # Pre-cargar todas las filas de datos como objetos de celda en memoria
    # Esto evita llamadas repetidas a ws.cell(row, col) que son lentas
    todas_las_filas = list(ws_sistema.iter_rows(min_row=fila_enc_sistema + 1))

    for fila_cells in todas_las_filas:

        codigo_raw = fila_cells[col_codigo_int - 1].value
        if codigo_raw is None:
            continue
        codigo_str = _normalizar(codigo_raw)
        if not codigo_str:
            continue

        if codigo_str not in datos_cliente:
            no_encontrados += 1
            continue

        datos = datos_cliente[codigo_str]
        fila_modificada = False

        # Recorrer el mapeo cliente → sistema
        for col_cliente, destino in _MAPEO.items():
            nuevo_val_str = datos.get(col_cliente, "")
            if not nuevo_val_str:
                # No sobreescribir con vacío
                continue

            # destino puede ser str o lista de str
            destinos = [destino] if isinstance(destino, str) else destino

            for col_sis in destinos:
                if col_sis not in mapa_sistema:
                    continue

                cell = fila_cells[mapa_sistema[col_sis] - 1]
                actual_str = _normalizar(cell.value)

                if nuevo_val_str == actual_str:
                    continue  # Sin cambio

                # Intentar preservar el tipo numérico para Latitud/Longitud
                if col_sis in ("Latitud", "Longitud"):
                    try:
                        cell.value = float(nuevo_val_str)
                    except ValueError:
                        cell.value = nuevo_val_str
                else:
                    cell.value = nuevo_val_str

                fila_modificada = True

        # ── Actualizar tags derivados de RUTA ───────────────────────────
        ruta_descompuesta = _descomponer_ruta(datos.get("RUTA", ""))
        for col_sis, nuevo_val_str in ruta_descompuesta.items():
            if col_sis not in mapa_sistema:
                continue
            cell = fila_cells[mapa_sistema[col_sis] - 1]
            actual_str = _normalizar(cell.value)
            if nuevo_val_str == actual_str:
                continue
            cell.value = nuevo_val_str
            fila_modificada = True

        # ── Actualizar Nombre Lugar (lógica especial) ────────────────────
        # El nombre canónico es: Cadena (del catálogo) + Nombre Tienda (del Maestro)
        # La Cadena se toma siempre del catálogo para no usar el valor incorrecto del Maestro.
        # El maestro puede traer el nombre en "NOMBRE DE LA TIENDA" o en "Nombre Lugar".
        nombre_tienda_nuevo = datos.get("NOMBRE DE LA TIENDA") or datos.get("Nombre Lugar", "")
        if nombre_tienda_nuevo and "Nombre Lugar" in mapa_sistema:
            cadena = ""
            if "Cadena" in mapa_sistema:
                cadena = _normalizar(fila_cells[mapa_sistema["Cadena"] - 1].value)
            # Quitar siglas de la cadena si el maestro las incrustó en el nombre
            # Ej: 'FA JOSEFA' con cadena 'FARMACIAS DEL AHORRO' → 'JOSEFA'
            nombre_tienda_limpio = _quitar_siglas_cadena(nombre_tienda_nuevo, cadena)
            partes = [p for p in [cadena, nombre_tienda_limpio] if p]
            nombre_nuevo = _eliminar_duplicados_consecutivos(" ".join(partes))
            nombre_nuevo = " ".join(nombre_nuevo.split())  # limpiar espacios dobles
            if len(nombre_nuevo) > 60:
                nombre_nuevo = nombre_nuevo[:60]

            cell_nombre = fila_cells[mapa_sistema["Nombre Lugar"] - 1]
            actual_nombre = (cell_nombre.value or "").strip()

            if nombre_nuevo != actual_nombre:
                cell_nombre.value = nombre_nuevo
                fila_modificada = True

        # ── Actualizar Activo/tags_ESTATUS ───────────────────────────────
        # El maestro puede tener la columna "STATUS OPERACIONES" o "Activo".
        # Valores aceptados: ACTIVO → 1, INACTIVO → 0, 1 → 1, 0 → 0.
        # tags_ESTATUS guarda la representación en texto: ACTIVO/INACTIVO.
        if "Activo" in mapa_sistema or "tags_ESTATUS" in mapa_sistema:
            estado_raw = datos.get("STATUS OPERACIONES") or datos.get("Activo", "")
            nuevo_activo = _normalizar_activo(estado_raw)
            if nuevo_activo is not None:
                if "Activo" in mapa_sistema:
                    cell_activo = fila_cells[mapa_sistema["Activo"] - 1]
                    if _normalizar(nuevo_activo) != _normalizar(cell_activo.value):
                        cell_activo.value = nuevo_activo
                        fila_modificada = True

                if "tags_ESTATUS" in mapa_sistema:
                    nuevo_estatus_txt = _activo_a_tags_estatus(nuevo_activo)
                    cell_estatus = fila_cells[mapa_sistema["tags_ESTATUS"] - 1]
                    if _normalizar(nuevo_estatus_txt) != _normalizar(cell_estatus.value):
                        cell_estatus.value = nuevo_estatus_txt
                        fila_modificada = True

        if fila_modificada:
            fila_cells[col_accion - 1].value = "UPDATE"
            actualizados += 1
            filas_update.append([cell.value for cell in fila_cells])
        else:
            sin_cambios += 1

    # ── 4. Conservar solo filas UPDATE en archivo final ──────────────
    filas_en_hoja = ws_sistema.max_row
    if filas_en_hoja > fila_enc_sistema:
        ws_sistema.delete_rows(fila_enc_sistema + 1, filas_en_hoja - fila_enc_sistema)
    for fila in filas_update:
        ws_sistema.append(fila)

    # ── 5. Guardar ────────────────────────────────────────────────────
    try:
        wb_sistema.save(ruta_salida)
    except PermissionError:
        wb_sistema.close()
        raise RuntimeError("El archivo de salida está abierto en Excel. Ciérralo e intenta de nuevo.")
    except Exception as exc:
        wb_sistema.close()
        raise RuntimeError(f"No se pudo guardar el archivo: {exc}")

    wb_sistema.close()

    # ── 6. Dividir en partes si supera el límite ──────────────────────
    total_filas_datos = len(filas_update)
    if total_filas_datos > _LIMITE_REGISTROS:
        print(f"  El catálogo tiene {total_filas_datos:,} registros → "
              f"dividiendo en partes de {_LIMITE_REGISTROS:,}…")

        filas_datos = filas_update

        ext = os.path.splitext(ruta_salida)[1]
        nombre_base = "layout_places_actualizado"
        num_partes = (total_filas_datos + _LIMITE_REGISTROS - 1) // _LIMITE_REGISTROS

        for i in range(num_partes):
            chunk = filas_datos[i * _LIMITE_REGISTROS:(i + 1) * _LIMITE_REGISTROS]
            ruta_p = os.path.join(carpeta_salida, f"{nombre_base}_parte_{i + 1}{ext}")
            # Copiar el archivo actualizado para preservar todo el formato y propiedades
            shutil.copy2(ruta_salida, ruta_p)
            wb_p = openpyxl.load_workbook(ruta_p, keep_links=False)
            ws_p = wb_p[_HOJA_SISTEMA]
            # Eliminar filas de datos anteriores; conservar encabezados
            filas_en_copia = ws_p.max_row
            if filas_en_copia > fila_enc_sistema:
                ws_p.delete_rows(fila_enc_sistema + 1, filas_en_copia - fila_enc_sistema)
            for fila in chunk:
                ws_p.append(fila)
            wb_p.save(ruta_p)
            wb_p.close()
            print(f"    Parte {i + 1}/{num_partes}: {len(chunk):,} registros "
                  f"→ {os.path.basename(ruta_p)}")

        print(f"  División completada: {num_partes} archivos generados.")
        print(f"  Archivo unificado conservado: {os.path.basename(ruta_salida)}")

    return True

