#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script de debug que ejecuta el pipeline y guarda la salida.
"""

import sys
import os

# Redirigir salida a UTF-8
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Agregar ruta del proyecto
proyecto_dir = r"c:\Users\katoH\OneDrive\Documentos\Proyectos personales\Automatizaciones storecheck L2"
if proyecto_dir not in sys.path:
    sys.path.insert(0, proyecto_dir)

# Archivo de salida
output_file = os.path.join(r"C:\Temp", "DEBUG_OUTPUT_PIPELINE.txt")
os.makedirs(r"C:\Temp", exist_ok=True)

def main():
    with open(output_file, 'w', encoding='utf-8', errors='replace') as f:
        # Redirigir stdout
        original_stdout = sys.stdout
        sys.stdout = f
        
        try:
            from core.catalogacion.completa import procesar_matriz
            
            ruta_archivo = r"C:\Users\katoH\Downloads\MATRIZ DE CATALOGACÓN actual 1 (4) (1).xlsx"
            ruta_products = r"C:\Users\katoH\Downloads\layout_products_188865 (5).xlsx"
            ruta_places = r"C:\Users\katoH\Downloads\layout_places_188865 (5).xlsx"
            
            print("=" * 100)
            print("INICIANDO PIPELINE DE DEBUG")
            print("=" * 100)
            print(f"\nArchivo: {ruta_archivo}")
            print(f"Productos: {ruta_products}")
            print(f"Lugares: {ruta_places}")
            print("\n" + "=" * 100)
            
            result = procesar_matriz(ruta_archivo, ruta_products, ruta_places, proyecto_dir)
            
            print("\n" + "=" * 100)
            print(f"RESULTADO: {'EXITO' if result else 'FALLO'}")
            print("=" * 100)
            
        except Exception as e:
            print(f"\nERROR: {e}")
            import traceback
            traceback.print_exc()
        finally:
            sys.stdout = original_stdout
    
    # Leer y mostrar el archivo
    print(f"Salida guardada en: {output_file}")
    print("\n" + "="*100)
    print("MOSTRANDO OUTPUT DEL DEBUG:")
    print("="*100 + "\n")
    
    with open(output_file, 'r', encoding='utf-8', errors='replace') as f:
        print(f.read())

if __name__ == "__main__":
    main()
