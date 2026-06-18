"""
Script que ejecuta el debug y guarda la salida en un archivo.
"""

import os
import sys
import io
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr

# Configurar encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.insert(0, str(Path(__file__).parent))

from core.catalogacion.completa import procesar_matriz

# Rutas
ruta_archivo_entrada = r"C:\Users\katoH\Downloads\MATRIZ DE CATALOGACÓN actual 1 (4) (1).xlsx"
ruta_layout_products = r"C:\Users\katoH\Downloads\layout_products_188865 (5).xlsx"
ruta_layout_places = r"C:\Users\katoH\Downloads\layout_places_188865 (5).xlsx"
ruta_base = r"C:\Users\katoH\OneDrive\Documentos\Proyectos personales\Automatizaciones storecheck L2"

output_file = r"C:\Users\katoH\OneDrive\Documentos\Proyectos personales\Automatizaciones storecheck L2\debug_output.log"

try:
    with open(output_file, 'w', encoding='utf-8') as f:
        # Redirigir stdout y stderr al archivo
        with redirect_stdout(f), redirect_stderr(f):
            print("="*80)
            print("INICIANDO DEBUG DEL PIPELINE DE CATALOGACION")
            print("="*80)
            print(f"\nArchivo de entrada: {ruta_archivo_entrada}")
            print(f"Layout products: {ruta_layout_products}")
            print(f"Layout places: {ruta_layout_places}")
            print(f"\nVerificando archivos...")
            
            for ruta in [ruta_archivo_entrada, ruta_layout_products, ruta_layout_places]:
                exists = os.path.exists(ruta)
                print(f"  {ruta}: {'ENCONTRADO' if exists else 'NO ENCONTRADO'}")
            
            print("\n" + "="*80)
            print("EJECUTANDO PIPELINE...")
            print("="*80)
            
            success = procesar_matriz(ruta_archivo_entrada, ruta_layout_products, ruta_layout_places, ruta_base)
            
            print("\n" + "="*80)
            if success:
                print("[OK] PIPELINE COMPLETADO")
            else:
                print("[ERROR] PIPELINE FALLO")
            print("="*80)
    
    # Leer y mostrar el archivo
    with open(output_file, 'r', encoding='utf-8') as f:
        print(f.read())
        
except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
