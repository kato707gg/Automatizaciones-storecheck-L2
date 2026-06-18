from openpyxl import load_workbook
from openpyxl.utils import get_column_letter, column_index_from_string

# Cargar el archivo procesado
wb = load_workbook(r"C:\Users\katoH\Downloads\MATRIZ DE CATALOGACÓN actual 1 (4) (1).xlsx")
ws = wb["CONFIGURACIÓN DE ANAQUEL"]

print("="*80)
print("VERIFICACIÓN FINAL - Columnas CH, CI, CJ, CK tras post-processing")
print("="*80)

# Mostrar fila 1 (ahora fila 2 en la hoja porque borramos la fila 1)
print("\nFila 1 (después de borrar primera fila original):\n")
for col in range(column_index_from_string('CH'), column_index_from_string('CL') + 1):
    col_letter = get_column_letter(col)
    val = ws.cell(row=1, column=col).value
    marker = " <-- HEADER" if val and isinstance(val, str) and len(str(val)) > 5 else ""
    print(f"  {col_letter}: {val}{marker}")

print("\nFila 2 (datos/SKU):\n")
for col in range(column_index_from_string('CH'), column_index_from_string('CL') + 1):
    col_letter = get_column_letter(col)
    val = ws.cell(row=2, column=col).value
    print(f"  {col_letter}: {val}")

print("\nFila 3 (nombres de productos):\n")
for col in range(column_index_from_string('CH'), column_index_from_string('CL') + 1):
    col_letter = get_column_letter(col)
    val = ws.cell(row=3, column=col).value
    print(f"  {col_letter}: {val}")

print("\n" + "="*80)
print("Verificar también datos de Polvo en filas 5-10:")
print("="*80)

for row in range(5, min(11, ws.max_row + 1)):
    print(f"\nFila {row}:")
    for col in range(column_index_from_string('CH'), column_index_from_string('CL') + 1):
        col_letter = get_column_letter(col)
        val = ws.cell(row=row, column=col).value
        print(f"  {col_letter}: {val}")
