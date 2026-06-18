from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

wb = load_workbook(r"C:\Users\katoH\Downloads\MATRIZ DE CATALOGACÓN actual 1 (4) (1).xlsx")
ws = wb["CONFIGURACIÓN DE ANAQUEL"]

print("="*70)
print("BÚSQUEDA DE 'ELECTROLIFE ZERO POLVO' EN FILA 2")
print("="*70)

encontrado = False
for col in range(11, 200):  # K = 11
    val = ws.cell(row=2, column=col).value
    if val and isinstance(val, str):
        val_lower = val.lower()
        if 'polvo' in val_lower or 'zero' in val_lower:
            col_letter = get_column_letter(col)
            print(f"\n✓ ENCONTRADO EN {col_letter} ({col:3d}): {val}")
            encontrado = True
            
            # Mostrar datos de las filas 3 y 4 para este header
            r3 = ws.cell(row=3, column=col).value
            r4 = ws.cell(row=4, column=col).value
            print(f"  Fila 3: {r3}")
            print(f"  Fila 4: {r4}")
            
            # Mostrar columnas adyacentes
            print(f"\n  Contexto (fila 2):")
            for c in range(max(11, col-2), min(ws.max_column+1, col+4)):
                col_letter_ctx = get_column_letter(c)
                val_ctx = ws.cell(row=2, column=c).value
                marker = " <--" if c == col else ""
                print(f"    {col_letter_ctx:>3}: {val_ctx}{marker}")

if not encontrado:
    print("\n✗ NO ENCONTRADO")
    print("\nMostrando últimos headers (columnas CE en adelante):")
    for col in range(109, min(140, ws.max_column+1)):  # CE = 109
        val = ws.cell(row=2, column=col).value
        col_letter = get_column_letter(col)
        if val:
            print(f"  {col_letter:>3} ({col:3d}): {val}")
