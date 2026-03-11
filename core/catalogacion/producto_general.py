"""
Script para actualizar la columna del producto general en la hoja CONFIGURACIÓN DE ANAQUEL.

Este script revisa fila por fila (lugar por lugar) y si hay al menos una celda con valor
(no vacía) en el rango de sabores de un grupo, coloca un 1 en la/las columna(s) del
producto general correspondiente.

Los grupos y sus columnas se detectan DINÁMICAMENTE desde la hoja:
- Fila 2: nombre del grupo en la primera columna de cada grupo
- Fila 3: IDs de sabores; las columnas sin ID dentro del rango del grupo = columnas generales

No se necesitan rangos hardcodeados: el script se adapta automáticamente si cambian las columnas.
"""

import openpyxl
from openpyxl.utils import column_index_from_string, get_column_letter

NOMBRE_HOJA = "CONFIGURACIÓN DE ANAQUEL"
COL_INICIO_PRODUCTOS = 'K'   # Primera columna donde empiezan los grupos de productos
FILA_INICIO_DATOS = 5        # Fila donde empiezan los datos de lugares



def detectar_grupos(ws):
    """Detecta grupos de productos dinámicamente desde fila 2 y fila 3.

    Fila 2: nombre del grupo en la primera columna de ese grupo (resto vacío).
    Fila 3: IDs de sabores; columnas sin ID dentro del rango del grupo = generales.

    Retorna lista de (nombre_grupo, [cols_sabor], [cols_general]).
    """
    col_inicio = column_index_from_string(COL_INICIO_PRODUCTOS)
    max_col = ws.max_column

    # Recopilar inicios de grupo desde fila 2
    starts = []  # (col, nombre, es_especial)
    for col in range(col_inicio, max_col + 1):
        val = ws.cell(row=2, column=col).value
        if val is not None and str(val).strip() != "":
            nombre = str(val).strip()
            especial = any(k in nombre.lower() for k in ("competencia", "sams", "frentes"))
            starts.append((col, nombre, especial))

    grupos = []
    for i, (g_start, g_name, es_especial) in enumerate(starts):
        if es_especial:
            continue  # secciones especiales no tienen sabores
        g_next = starts[i + 1][0] if i + 1 < len(starts) else max_col + 1

        cols_sabor = []
        cols_general = []
        for col in range(g_start, g_next):
            id_val = ws.cell(row=3, column=col).value
            if id_val is not None and str(id_val).strip() != "":
                cols_sabor.append(col)
            else:
                cols_general.append(col)

        if cols_sabor:
            grupos.append((g_name, cols_sabor, cols_general))

    return grupos


def procesar_producto_general(wb):
    """Marca el producto general en CONFIGURACIÓN DE ANAQUEL detectando grupos dinámicamente."""
    print("\n--- Procesando producto general (detección dinámica) ---")

    if NOMBRE_HOJA not in wb.sheetnames:
        print(f"  ✗ ERROR: No se encontró la hoja '{NOMBRE_HOJA}'")
        return False

    ws = wb[NOMBRE_HOJA]
    col_F = column_index_from_string('F')

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

    for fila in range(FILA_INICIO_DATOS, ultima_fila + 1):
        if ws.cell(row=fila, column=col_F).value is None:
            continue

        for g_name, cols_sabor, cols_general in grupos:
            tiene_sabor = any(
                ws.cell(row=fila, column=c).value not in (None, "")
                for c in cols_sabor
            )
            if tiene_sabor:
                for gen_col in cols_general:
                    ws.cell(row=fila, column=gen_col).value = 1
                total_actualizaciones += 1

    print(f"  ✓ Total de celdas de general marcadas: {total_actualizaciones}")
    return True
