"""
Script para actualizar la columna del producto general en la hoja CONFIGURACIÓN DE ANAQUEL.

Este script revisa fila por fila (lugar por lugar) y si hay al menos una celda con valor 1
en el rango de sabores de un grupo, coloca un 1 en la/las columna(s) del
producto general correspondiente.

Los grupos y sus columnas se detectan DINÁMICAMENTE usando marcadores en la fila 2:
- Cada grupo inicia en su marcador de fila 2
- El/los producto(s) general(es) se ubican al final del grupo: columna(s)
    inmediatamente anterior(es) al siguiente marcador
- Regla especial: para "Electrolife Zero Polvo" son 2 columnas generales antes de "Aqualit"
- "Aqualit" se usa como separador de bloque y no crea una columna general extra

No se necesitan rangos hardcodeados: el script se adapta automáticamente si cambian las columnas.
"""

import openpyxl
from openpyxl.utils import column_index_from_string, get_column_letter

NOMBRE_HOJA = "CONFIGURACIÓN DE ANAQUEL"
COL_INICIO_PRODUCTOS = 'K'   # Primera columna donde empiezan los grupos de productos
FILA_INICIO_DATOS = 5        # Fila donde empiezan los datos de lugares

MARCADORES_ORDEN = [
    "Electrolit 625ml",
    "Electrolit 355ml",
    "Electrolit 1000ml",
    "Electrolife zero 625ml",
    "Electrolit Ped 300ml",
    "Electrolit Ped 500ml",
    "Electrolit Six Pack",
    "Electrolit Fifteen pack",
    "Electrolife Zero Polvo",
    "Aqualit 625",
    "Competencia",
]


def _normalizar_texto(texto):
    return " ".join(str(texto).strip().lower().split())


GENERALES_POR_MARCADOR = {
    _normalizar_texto("Electrolit Fifteen pack"): 0,
    _normalizar_texto("Electrolife Zero Polvo"): 2,
    _normalizar_texto("Aqualit 625"): 0,
    _normalizar_texto("Competencia"): 0,
}


ALIAS_MARCADORES = {
    _normalizar_texto("Aqualit 625"): {
        _normalizar_texto("Aqualit 625"),
        _normalizar_texto("Aqualit 625ml"),
    },
}


def _coincide_marcador(nombre_norm, marcador_norm):
    alias = ALIAS_MARCADORES.get(marcador_norm)
    if alias is not None:
        return nombre_norm in alias
    return nombre_norm == marcador_norm


def _mapear_marcadores(ws):
    """Devuelve el mapa marcador normalizado -> columna detectada en la fila 2."""
    col_inicio = column_index_from_string(COL_INICIO_PRODUCTOS)
    max_col = ws.max_column
    marcadores_norm = [_normalizar_texto(m) for m in MARCADORES_ORDEN]
    col_por_marcador = {}

    for col in range(col_inicio, max_col + 1):
        val = ws.cell(row=2, column=col).value
        if val is None or str(val).strip() == "":
            continue
        nombre_norm = _normalizar_texto(val)
        for marcador_norm in marcadores_norm:
            if marcador_norm in col_por_marcador:
                continue
            if _coincide_marcador(nombre_norm, marcador_norm):
                col_por_marcador[marcador_norm] = col
                break

    return col_por_marcador


def _mapear_bloques_marcadores(ws):
    """Devuelve el mapa marcador normalizado -> (col_inicio, col_fin) del bloque continuo detectado."""
    col_inicio = column_index_from_string(COL_INICIO_PRODUCTOS)
    max_col = ws.max_column
    marcadores_norm = [_normalizar_texto(m) for m in MARCADORES_ORDEN]
    bloques = {}

    col = col_inicio
    while col <= max_col:
        val = ws.cell(row=2, column=col).value
        if val is None or str(val).strip() == "":
            col += 1
            continue

        nombre_norm = _normalizar_texto(val)
        marcador_detectado = None
        for marcador_norm in marcadores_norm:
            if _coincide_marcador(nombre_norm, marcador_norm):
                marcador_detectado = marcador_norm
                break

        if marcador_detectado is None:
            col += 1
            continue

        col_fin = col
        while col_fin + 1 <= max_col:
            siguiente = ws.cell(row=2, column=col_fin + 1).value
            if siguiente is None or str(siguiente).strip() == "":
                break
            siguiente_norm = _normalizar_texto(siguiente)
            if not _coincide_marcador(siguiente_norm, marcador_detectado):
                break
            col_fin += 1

        bloques.setdefault(marcador_detectado, []).append((col, col_fin))
        col = col_fin + 1

    return bloques


def _compactar_huecos_despues_de_grupos_cero(ws):
    """Elimina un hueco de una sola columna entre un grupo de 0 generales y el siguiente marcador."""
    eliminadas = 0
    marcadores_norm = [_normalizar_texto(m) for m in MARCADORES_ORDEN]

    while True:
        bloques_por_marcador = _mapear_bloques_marcadores(ws)
        borrada = False

        for i in range(len(marcadores_norm) - 1):
            marcador_actual = marcadores_norm[i]
            marcador_siguiente = marcadores_norm[i + 1]

            if GENERALES_POR_MARCADOR.get(marcador_actual, 1) != 0:
                continue

            if marcador_actual not in bloques_por_marcador or marcador_siguiente not in bloques_por_marcador:
                continue

            col_actual = bloques_por_marcador[marcador_actual][-1][1]
            col_siguiente = bloques_por_marcador[marcador_siguiente][0][0]

            if col_siguiente != col_actual + 2:
                continue

            col_hueco = col_actual + 1
            if any(ws.cell(row=fila, column=col_hueco).value not in (None, "") for fila in range(2, 5)):
                continue

            ws.delete_cols(col_hueco, 1)
            eliminadas += 1
            borrada = True
            break

        if not borrada:
            break

    if eliminadas:
        print(f"  [OK] Eliminadas {eliminadas} columna(s) hueca(s) entre grupos de 0 generales")

    return eliminadas


def _eliminar_separador_vacio_solitario(ws):
    """Elimina columnas completamente vacías entre dos columnas con header.
    
    IMPORTANTE: Solo elimina columnas que están 100% vacías en TODO el worksheet,
    no aquellas que podrían ser "espacios para generales".
    
    Estrategia conservadora: Una columna solo se elimina si:
    1. NO tiene header en fila 2
    2. Está completamente vacía en TODAS las filas (no solo 2-4)
    """
    eliminadas = 0
    col_inicio = column_index_from_string(COL_INICIO_PRODUCTOS)

    while True:
        # Recolectar columnas que tienen header en fila 2
        columnas_activas = []
        for col in range(col_inicio, ws.max_column + 1):
            if ws.cell(row=2, column=col).value not in (None, ""):
                columnas_activas.append(col)

        borrada = False
        
        # Analizar pares consecutivos de headers
        for i in range(len(columnas_activas) - 1):
            izquierda = columnas_activas[i]
            derecha = columnas_activas[i + 1]
            
            # Si están pegadas, no hay columna entre ellas
            if derecha - izquierda <= 1:
                continue

            # Hay columnas entre izquierda y derecha
            # Revisar cada una: si está 100% VACÍA, eliminarla
            col_a_revisar = izquierda + 1
            while col_a_revisar < derecha:
                # Verificar si esta columna está COMPLETAMENTE VACÍA en TODAS las filas
                es_vacia_completa = True
                for fila in range(1, ws.max_row + 1):
                    if ws.cell(row=fila, column=col_a_revisar).value not in (None, ""):
                        es_vacia_completa = False
                        break
                
                if es_vacia_completa:
                    # Esta columna está 100% vacía, puede eliminarse
                    ws.delete_cols(col_a_revisar, 1)
                    eliminadas += 1
                    borrada = True
                    break  # Reiniciar búsqueda
                
                col_a_revisar += 1
            
            if borrada:
                break

        if not borrada:
            break

    if eliminadas:
        print(f"  [OK] Eliminadas {eliminadas} columna(s) sin header entre pares activos")

    return eliminadas



def detectar_grupos(ws):
    """Detecta grupos usando marcadores de fila 2 y calcula generales al final de cada grupo.

    Regla general: 1 columna general al final del rango (antes del siguiente marcador).
    Regla especial: en "Electrolife Zero Polvo" son 2 columnas generales antes de "Competencia".

    Retorna lista de (nombre_grupo, [cols_sabor], [cols_general]).
    """
    col_inicio = column_index_from_string(COL_INICIO_PRODUCTOS)
    max_col = ws.max_column

    marcadores_norm = [_normalizar_texto(m) for m in MARCADORES_ORDEN]
    col_por_marcador = {}

    for col in range(col_inicio, max_col + 1):
        val = ws.cell(row=2, column=col).value
        if val is None or str(val).strip() == "":
            continue
        nombre = str(val).strip()
        nombre_norm = _normalizar_texto(nombre)
        for marcador_norm in marcadores_norm:
            if marcador_norm in col_por_marcador:
                continue
            if _coincide_marcador(nombre_norm, marcador_norm):
                col_por_marcador[marcador_norm] = col
                break

    grupos = []

    def _col_tiene_datos_en_tiendas(col_idx):
        """True si la columna tiene algun dato en filas de tiendas (fila 5+)."""
        for fila in range(FILA_INICIO_DATOS, ws.max_row + 1):
            if ws.cell(row=fila, column=col_idx).value not in (None, ""):
                return True
        return False

    def _col_parece_producto(col_idx):
        """True si la columna parece de producto por metadata o datos de tiendas."""
        for fila in (3, 4):
            if ws.cell(row=fila, column=col_idx).value not in (None, ""):
                return True
        return _col_tiene_datos_en_tiendas(col_idx)

    def _col_parece_polvo(col_idx):
        """True si la columna pertenece explícitamente a Electrolife Zero Polvo."""
        textos = []
        for fila in (3, 4, 5, 6):
            val = ws.cell(row=fila, column=col_idx).value
            if val is not None:
                textos.append(_normalizar_texto(val))
        return any("electrolife zero polvo" in t for t in textos)

    # Procesamos solo grupos de producto (hasta antes de Competencia).
    # Competencia es el marcador terminal del bloque de productos para este cálculo.
    idx_competencia = marcadores_norm.index(_normalizar_texto("Competencia"))

    for i in range(idx_competencia):
        marcador_actual = marcadores_norm[i]
        marcador_siguiente = marcadores_norm[i + 1]

        if marcador_actual not in col_por_marcador or marcador_siguiente not in col_por_marcador:
            continue

        col_header_grupo = col_por_marcador[marcador_actual]  # Columna con el header (marcador)
        col_siguiente = col_por_marcador[marcador_siguiente]

        cantidad_generales = GENERALES_POR_MARCADOR.get(marcador_actual, 1)

        if cantidad_generales <= 0:
            continue

        col_general_inicio = col_siguiente - cantidad_generales
        col_general_fin = col_siguiente - 1
        col_sabor_fin = col_general_inicio - 1

        # Si la columna del marcador también contiene el primer producto,
        # puede venir reflejado en fila 3 (ID), fila 4 (Nombre) o solo
        # en datos de tiendas (fila 5+). Si detectamos producto en cualquiera
        # de esos niveles, incluimos la columna del marcador como sabor.
        val_id = ws.cell(row=3, column=col_header_grupo).value
        val_nombre = ws.cell(row=4, column=col_header_grupo).value
        header_tiene_producto = (
            val_id not in (None, "")
            or val_nombre not in (None, "")
            or _col_tiene_datos_en_tiendas(col_header_grupo)
        )
        start_sabor = col_header_grupo if header_tiene_producto else col_header_grupo + 1

        # Caso especial de Polvo: a veces el primer sabor queda una o mas
        # columnas a la izquierda del marcador, sin texto en fila 2 pero con
        # datos reales del producto. Recuperamos esas columnas huérfanas para
        # que los dos generales usen el mismo rango completo.
        if marcador_actual == _normalizar_texto("Electrolife Zero Polvo"):
            col_scan = col_header_grupo - 1
            if (
                col_scan >= col_inicio
                and ws.cell(row=2, column=col_scan).value in (None, "")
                and _col_parece_polvo(col_scan)
            ):
                start_sabor = col_scan

        if col_sabor_fin < start_sabor:
            continue

        cols_sabor = list(range(start_sabor, col_sabor_fin + 1))
        cols_general = list(range(col_general_inicio, col_general_fin + 1))

        # Salvaguarda: una columna general no debe ser un marcador/columna
        # rotulada (ej. Aqualit). Conservamos solo slots sin texto en fila 2.
        cols_general = [c for c in cols_general if ws.cell(row=2, column=c).value in (None, "")]
        if not cols_general:
            continue

        nombre_grupo = MARCADORES_ORDEN[i]
        grupos.append((nombre_grupo, cols_sabor, cols_general))

    return grupos


def _es_uno(valor):
    """True cuando el valor representa un 1 (int/float/str)."""
    if valor is None:
        return False
    if isinstance(valor, (int, float)):
        return valor == 1
    texto = str(valor).strip()
    if texto == "1":
        return True
    # Aceptar variantes numéricas frecuentes como texto: "1.0" o "1,0".
    texto = texto.replace(",", ".")
    try:
        return float(texto) == 1.0
    except (TypeError, ValueError):
        return False


def procesar_producto_general(wb):
    """Marca el producto general en CONFIGURACIÓN DE ANAQUEL detectando grupos dinámicamente."""
    print("\n--- Procesando producto general (detección dinámica) ---")

    if NOMBRE_HOJA not in wb.sheetnames:
        print(f"  [ERROR] ERROR: No se encontró la hoja '{NOMBRE_HOJA}'")
        return False

    ws = wb[NOMBRE_HOJA]

    grupos = detectar_grupos(ws)
    if not grupos:
        print("  ! No se detectaron grupos de productos.")
        return True

    print(f"  Grupos detectados ({len(grupos)}):")
    for g_name, cols_sabor, cols_general in grupos:
        print(f"  Grupo '{g_name}': {len(cols_sabor)} sabores "
              f"({get_column_letter(cols_sabor[0])}-{get_column_letter(cols_sabor[-1])}), "
              f"{len(cols_general)} general(es) "
              f"({', '.join(get_column_letter(c) for c in cols_general)})")

    ultima_fila = ws.max_row
    total_actualizaciones = 0

    # Limpiar primero las columnas de generales para evitar arrastrar 1s
    # históricos que no correspondan al rango actual de sabores.
    for fila in range(FILA_INICIO_DATOS, ultima_fila + 1):
        for _, _, cols_general in grupos:
            for gen_col in cols_general:
                ws.cell(row=fila, column=gen_col).value = None

    for fila in range(FILA_INICIO_DATOS, ultima_fila + 1):
        for g_name, cols_sabor, cols_general in grupos:
            tiene_uno_en_sabores = any(
                _es_uno(ws.cell(row=fila, column=c).value)
                for c in cols_sabor
            )
            if tiene_uno_en_sabores:
                for gen_col in cols_general:
                    ws.cell(row=fila, column=gen_col).value = 1
                    total_actualizaciones += 1

    print(f"  [OK] Total de celdas de general marcadas: {total_actualizaciones}")
    
    # No borrar filas aquí: catalogación por formato/tienda depende de que
    # IDs estén en fila 3 y nombres en fila 4.
    
    return True


def _borrar_primera_fila(ws):
    """Borra la primera fila de la hoja (para limpiar datos confusos)."""
    print(f"  Borrando primera fila...")
    ws.delete_rows(1, 1)
    print(f"    [OK] Primera fila eliminada")
