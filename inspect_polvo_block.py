from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

path = r'C:\Users\katoH\Downloads\Matriz_Aqualit_CF_20260610_044753.xlsx'
wb = load_workbook(path, data_only=False)
ws = wb['CONFIGURACIÓN DE ANAQUEL']

for col in range(86, 92):  # CH to CK
    print('COL', get_column_letter(col), col)
    for row in (1, 2, 3, 4, 5, 6):
        print(row, repr(ws.cell(row=row, column=col).value))
    print('---')
