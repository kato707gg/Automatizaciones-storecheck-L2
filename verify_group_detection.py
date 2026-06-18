import datetime
import shutil
import sys

sys.path.insert(0, r"c:\Users\katoH\OneDrive\Documentos\Proyectos personales\Automatizaciones storecheck L2")

from core.catalogacion.completa import procesar_matriz

source = r"C:\Users\katoH\Downloads\MATRIZ DE CATALOGACÓN actual 1 (4) (1) - copia.xlsx"
products = r"C:\Users\katoH\Downloads\layout_products_188865 (5).xlsx"
places = r"C:\Users\katoH\Downloads\layout_places_188865 (5).xlsx"
base = r"c:\Users\katoH\OneDrive\Documentos\Proyectos personales\Automatizaciones storecheck L2"

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
target = rf"C:\Users\katoH\Downloads\Matriz_VERIFY_{ts}.xlsx"
shutil.copy(source, target)
print("FILE", target)
procesar_matriz(target, products, places, base)
