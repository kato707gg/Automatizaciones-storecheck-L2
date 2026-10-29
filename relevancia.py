"""
Script para actualizar el campo "Relevancia" de productos en
https://webapp.storecheck.com/product/index a partir de un archivo Excel.

Requisitos previos (ejecutar una sola vez en una terminal):
    pip install playwright openpyxl
    playwright install chromium

Uso:
    python actualizar_relevancia.py

Qué hace:
    1. Lee "CATALOGO DE PRODUCTOS MATRIZ.xlsx" (debe estar en la misma carpeta
       que este script). Columna 1 = nombre del producto, columna 2 = número
       de relevancia.
    2. Abre un navegador Chrome visible y lo lleva a la página de login.
    3. Se detiene y espera a que tú inicies sesión manualmente. Cuando ya
       estés dentro de la página de productos, presiona ENTER en la terminal.
    4. Para cada producto de la lista:
         - Escribe el nombre en la barra de búsqueda (#textSearch).
         - Revisa los resultados de la tabla; si el producto no aparece en la
           página actual, hace clic en la flecha "siguiente" e intenta de
           nuevo, hasta agotar las páginas disponibles.
         - Al encontrar una coincidencia, hace clic en el producto para
           entrar a su detalle.
         - Actualiza el campo #relevance con el valor de la columna 2 del
           Excel.
         - Hace clic en "Guardar cambios" (#saveBtn).
         - Regresa a la página de productos y continúa con el siguiente.
    5. Al final imprime un resumen de qué productos se actualizaron y cuáles
       no se encontraron, y lo guarda en "resultado_actualizacion.xlsx".
"""

import re
import sys
import time
import unicodedata
from pathlib import Path

from openpyxl import load_workbook, Workbook
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError, Error as PWError

# ------------------------------------------------------------------------
# CONFIGURACIÓN — ajusta aquí si algo cambia
# ------------------------------------------------------------------------
EXCEL_FILENAME = "CATALOGO DE PRODUCTOS MATRIZ.xlsx"
PRODUCT_INDEX_URL = "https://webapp.storecheck.com/product/index"
MAX_PAGES_TO_SEARCH = 60          # tope de seguridad al recorrer páginas
WAIT_AFTER_SEARCH_MS = 1500       # espera a que la tabla se actualice tras buscar
WAIT_AFTER_PAGE_MS = 1000         # espera al cambiar de página en la tabla
WAIT_AFTER_SAVE_MS = 1500         # espera tras guardar cambios


def normalizar(texto: str) -> str:
    """Quita acentos, pasa a mayúsculas, colapsa espacios, une un número
    con la unidad que le sigue aunque vengan separados por espacio(s)
    (ej. "625 ML" y "625ML" quedan como "625ML"), y normaliza los guiones
    para que no importe si vienen pegados o con espacios alrededor
    (ej. "NARANJA-MANDARINA" y "NARANJA - MANDARINA" quedan igual).
    Esto hace que la comparación entre el nombre del Excel y el nombre en
    el sitio sea confiable."""
    if texto is None:
        return ""
    texto = texto.strip().upper()
    texto = "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
    # Los guiones (con o sin espacios alrededor) se tratan como un espacio:
    # "NARANJA-MANDARINA" / "NARANJA - MANDARINA" -> "NARANJA MANDARINA"
    texto = re.sub(r"\s*-\s*", " ", texto)
    texto = " ".join(texto.split())
    # Une número + unidad separados por espacio: "625 ML" -> "625ML"
    texto = re.sub(r"(\d+)\s+([A-Z]+)\b", r"\1\2", texto)
    # Normaliza guiones: quita espacios alrededor -> "NARANJA - MANDARINA"
    # y "NARANJA-MANDARINA" quedan ambos como "NARANJA-MANDARINA"
    texto = re.sub(r"\s*-\s*", "-", texto)
    return texto


def leer_excel(ruta: Path):
    """Lee el excel y regresa una lista de tuplas (nombre, relevancia)."""
    wb = load_workbook(ruta, data_only=True)
    ws = wb.active

    filas = []
    for i, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if row is None or len(row) < 2:
            continue
        nombre, relevancia = row[0], row[1]
        if nombre is None:
            continue
        nombre = str(nombre).strip()
        if not nombre:
            continue
        # Salta encabezado si la primera fila no trae un número válido
        if i == 1:
            try:
                float(relevancia)
            except (TypeError, ValueError):
                continue
        if relevancia is None:
            continue
        try:
            relevancia = int(float(relevancia))
        except (TypeError, ValueError):
            print(f"  Aviso: relevancia inválida para '{nombre}' -> se omite")
            continue
        filas.append((nombre, relevancia))
    return filas


def guardar_resultado(resultados, ruta_salida: Path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Resultado"
    ws.append(["Nombre", "Relevancia", "Estatus", "Detalle"])
    for nombre, relevancia, estatus, detalle in resultados:
        ws.append([nombre, relevancia, estatus, detalle])
    wb.save(ruta_salida)


def ir_a_indice(page, intentos: int = 4):
    """Navega a la página de productos, reintentando si la navegación es
    interrumpida por una redirección propia del sitio (p. ej. justo después
    del login)."""
    for intento in range(1, intentos + 1):
        try:
            page.goto(PRODUCT_INDEX_URL, wait_until="load")
            page.wait_for_selector("#textSearch", timeout=15000)
            return
        except (PWError, PWTimeoutError) as e:
            if intento == intentos:
                raise
            print(f"   (reintentando navegación al índice, intento {intento}: {e.__class__.__name__})")
            page.wait_for_timeout(1000)


def buscar_producto(page, nombre_buscado: str):
    """Escribe el nombre en el buscador y recorre páginas de resultados
    hasta encontrar una coincidencia EXACTA (ignorando espacios dobles y
    espacios al inicio/final, y mayúsculas/acentos como red de seguridad).
    Regresa el locator de la fila (elemento p.p-description) encontrada,
    o None si no se encontró."""

    objetivo = normalizar(nombre_buscado)

    # Limpiar y escribir en el buscador
    caja = page.locator("#textSearch")
    caja.click()
    caja.fill("")
    caja.type(nombre_buscado, delay=30)
    caja.press("Enter")
    page.wait_for_timeout(WAIT_AFTER_SEARCH_MS)

    for pagina in range(1, MAX_PAGES_TO_SEARCH + 1):
        filas = page.locator("#productTable tbody tr")
        total_filas = filas.count()

        for i in range(total_filas):
            celda = filas.nth(i).locator("p.p-description[data-prod-dsc]").first
            try:
                texto = celda.get_attribute("title") or celda.inner_text()
            except Exception:
                continue
            if not texto:
                continue

            texto_norm = normalizar(texto)
            if objetivo == texto_norm or objetivo in texto_norm or texto_norm in objetivo:
                return celda

        # No se encontró en esta página: intentar avanzar a la siguiente
        boton_siguiente = page.locator("#productTable_next")
        clase = boton_siguiente.get_attribute("class") or ""
        if "disabled" in clase:
            break  # ya no hay más páginas

        boton_siguiente.click()
        page.wait_for_timeout(WAIT_AFTER_PAGE_MS)

    return None


def actualizar_relevancia(page, relevancia: int):
    """En la página de detalle del producto, llena #relevance y guarda."""
    campo = page.locator("#relevance")
    campo.wait_for(state="visible", timeout=15000)
    campo.click()
    # Selecciona todo el contenido actual y lo reemplaza
    campo.fill("")
    campo.type(str(relevancia), delay=20)

    guardar = page.locator("#saveBtn")
    guardar.wait_for(state="visible", timeout=15000)
    guardar.click()
    page.wait_for_timeout(WAIT_AFTER_SAVE_MS)


def main():
    carpeta = Path(__file__).resolve().parent
    ruta_excel = carpeta / EXCEL_FILENAME

    if not ruta_excel.exists():
        print(f"ERROR: no encontré el archivo '{EXCEL_FILENAME}' en {carpeta}")
        sys.exit(1)

    print(f"Leyendo '{EXCEL_FILENAME}' ...")
    productos = leer_excel(ruta_excel)
    print(f"Se encontraron {len(productos)} productos en el Excel.\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        print(f"Abriendo {PRODUCT_INDEX_URL} ...")
        page.goto(PRODUCT_INDEX_URL)

        input(
            "\n>>> Inicia sesión manualmente en la ventana del navegador.\n"
            ">>> Cuando ya estés dentro de la página de productos "
            "(la barra de búsqueda visible), regresa aquí y presiona ENTER "
            "para comenzar...\n"
        )

        # Le damos un momento a la página por si todavía está redirigiendo
        # sola tras el login (evita choques de navegación).
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except PWTimeoutError:
            pass

        # Por si el login te dejó en otra URL, aseguramos estar en el índice
        if PRODUCT_INDEX_URL not in page.url:
            ir_a_indice(page)
        else:
            page.wait_for_selector("#textSearch", timeout=30000)

        resultados = []
        total = len(productos)

        for idx, (nombre, relevancia) in enumerate(productos, start=1):
            print(f"[{idx}/{total}] Buscando: {nombre} (relevancia={relevancia})")

            # Aseguramos estar en la página de índice antes de cada búsqueda
            if PRODUCT_INDEX_URL not in page.url:
                ir_a_indice(page)

            try:
                celda = buscar_producto(page, nombre)
            except PWTimeoutError:
                print("   -> Error de tiempo de espera durante la búsqueda.")
                resultados.append((nombre, relevancia, "ERROR", "Timeout en búsqueda"))
                continue

            if celda is None:
                print("   -> No se encontró ninguna coincidencia.")
                resultados.append((nombre, relevancia, "NO ENCONTRADO", ""))
                continue

            texto_encontrado = celda.get_attribute("title") or celda.inner_text()
            print(f"   -> Coincidencia: {texto_encontrado}")

            try:
                celda.click()
                actualizar_relevancia(page, relevancia)
                print("   -> Relevancia actualizada y guardada.")
                resultados.append((nombre, relevancia, "ACTUALIZADO", texto_encontrado))
            except PWTimeoutError:
                print("   -> Error: no cargó el campo de relevancia o el botón guardar.")
                resultados.append((nombre, relevancia, "ERROR", "No cargó el formulario de detalle"))
            except Exception as e:
                print(f"   -> Error inesperado: {e}")
                resultados.append((nombre, relevancia, "ERROR", str(e)))

        browser.close()

        # Resumen final
        ruta_salida = carpeta / "resultado_actualizacion.xlsx"
        guardar_resultado(resultados, ruta_salida)

        ok = sum(1 for r in resultados if r[2] == "ACTUALIZADO")
        no_enc = sum(1 for r in resultados if r[2] == "NO ENCONTRADO")
        err = sum(1 for r in resultados if r[2] == "ERROR")

        print("\n=== RESUMEN ===")
        print(f"Actualizados:   {ok}")
        print(f"No encontrados: {no_enc}")
        print(f"Con error:      {err}")
        print(f"Detalle guardado en: {ruta_salida}")


if __name__ == "__main__":
    main()
