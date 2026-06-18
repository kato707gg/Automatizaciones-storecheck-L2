"""
Script de prueba para capturar debug output del pipeline.
Ejecutar con: python test_debug.py
"""

import os
import sys
from pathlib import Path

# Configurar encoding para Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Agregar el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent))

from core.catalogacion.completa import procesar_matriz

# Ruta del archivo a procesar
# EDITA ESTA LÍNEA CON LA RUTA DE TU ARCHIVO
ruta_archivo_entrada = r"C:\Users\katoH\Downloads\MATRIZ DE CATALOGACÓN actual 1 (4) (1).xlsx"

# Rutas de archivos auxiliares (layout files)
ruta_layout_products = r"C:\Users\katoH\Downloads\layout_products_188865 (5).xlsx"
ruta_layout_places = r"C:\Users\katoH\Downloads\layout_places_188865 (5).xlsx"
ruta_base = r"C:\Users\katoH\OneDrive\Documentos\Proyectos personales\Automatizaciones storecheck L2"

if __name__ == "__main__":
    print("="*60)
    print("INICIANDO DEBUG DEL PIPELINE DE CATALOGACION")
    print("="*60)
    
    # Verificar que exista el archivo de entrada
    if not os.path.exists(ruta_archivo_entrada):
        print(f"\n[ERROR] Archivo de entrada no encontrado:")
        print(f"  {ruta_archivo_entrada}")
        print(f"\nPor favor, edita la variable 'ruta_archivo_entrada' en este script")
        print(f"y proporciona la ruta correcta a tu archivo MATRIZ DE CATALOGACION.")
        sys.exit(1)
    
    print(f"\n[OK] Archivo de entrada: {os.path.basename(ruta_archivo_entrada)}")
    
    # Ejecutar el pipeline
    try:
        success = procesar_matriz(ruta_archivo_entrada, ruta_layout_products, ruta_layout_places, ruta_base)
        
        if success:
            print("\n" + "="*60)
            print("[OK] PIPELINE COMPLETADO EXITOSAMENTE")
            print("="*60)
            print(f"\nArchivo procesado: {os.path.basename(ruta_archivo_entrada)}")
            print("\nREVISA LA SALIDA ANTERIOR PARA IDENTIFICAR DONDE APARECE LA COLUMNA VACIA")
        else:
            print("\n" + "="*60)
            print("[ERROR] PIPELINE FALLO")
            print("="*60)
            
    except Exception as e:
        print("\n" + "="*60)
        print("[ERROR] DURANTE EL PROCESAMIENTO")
        print("="*60)
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
