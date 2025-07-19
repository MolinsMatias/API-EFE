from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
import requests
from bs4 import BeautifulSoup
from typing import List, Tuple, Optional, Dict
from datetime import datetime, timedelta



app = FastAPI()

DESTINOS = {
    1: "Estación Central",
    3: "San Bernardo",
    6: "Buin Zoo",
    7: "Buin",
    8: "Linderos",
    9: "Paine",
    10: "Hospital",
    11: "San Francisco",
    12: "Graneros",
    13: "Rancagua"
}

def scrape_itinerarios(html: str, tipo_tarifa: str) -> List[Dict]:
    soup = BeautifulSoup(html, 'html.parser')
    itinerarios = []
    tarifa_label = f"Salidas Tarifa {tipo_tarifa}"
    tabla = soup.find('p', string=tarifa_label)
    if not tabla:
        return []
    tabla = tabla.find_next('table')
    rows = tabla.tbody.find_all('tr')

    for i, row in enumerate(rows, 1):
        cols = row.find_all('td')
        salida = cols[0].get_text(strip=True).replace('🕒', '')
        llegada = cols[1].get_text(strip=True).replace('🕒', '')
        duracion = cols[2].get_text(strip=True).replace('⌛', '')
        valor = cols[3].get_text(strip=True).replace('$', '').replace('.', '').strip()
        itinerarios.append({
            'viaje': i,
            'salida': salida,
            'llegada': llegada,
            'duracion': duracion,
            'valor': valor,
            'tarifa': tipo_tarifa
        })
    return itinerarios

def obtener_todos_los_viajes(origen: int, destino: int) -> Tuple[Optional[List[Dict]], Optional[str]]:
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    url = (
        f"https://www.efe.cl/planificador/?empresa=1&hsalida=1&hregreso=&usuario=1"
        f"&ida=1&origen={origen}&destino={destino}&salida={fecha_hoy}&hran=1"
    )
    response = requests.get(url)
    if response.status_code != 200:
        return None, "Error al obtener datos"
    
    baja = scrape_itinerarios(response.text, "Baja")
    alta = scrape_itinerarios(response.text, "Alta")
    return baja + alta, None

@app.get("/itinerarios")
def itinerarios_completos(
    origen: int = Query(6, description="Código de la estación de origen"),
    destino: int = Query(3, description="Código de la estación de destino")
):
    todos, error = obtener_todos_los_viajes(origen, destino)
    if error:
        return JSONResponse(status_code=500, content={"error": error})
    return {
        "origen": DESTINOS.get(origen, "Desconocido"),
        "destino": DESTINOS.get(destino, "Desconocido"),
        "itinerarios": todos
    }

@app.get("/itinerarios/ahora")
def itinerarios_proximos(
    origen: int = Query(6, description="Código de la estación de origen"),
    destino: int = Query(3, description="Código de la estación de destino")
):
    ahora = (datetime.utcnow() - timedelta(hours=4)).time()
    fecha_hoy = ahora.strftime("%Y-%m-%d")
    url = (
        f"https://www.efe.cl/planificador/?empresa=1&hsalida=1&hregreso=&usuario=1"
        f"&ida=1&origen={origen}&destino={destino}&salida={fecha_hoy}&hran=1"
    )

    response = requests.get(url)
    if response.status_code != 200:
        return JSONResponse(status_code=500, content={"error": "No se pudo obtener la página"})

    baja = scrape_itinerarios(response.text, "Baja")
    alta = scrape_itinerarios(response.text, "Alta")

    def filtrar_proximos(lista: List[Dict]) -> List[Dict]:
        proximos = []
        for item in lista:
            try:
                hora_salida = datetime.strptime(item['salida'], "%H:%M").replace(
                    year=ahora.year, month=ahora.month, day=ahora.day
                )
                if hora_salida >= ahora:
                    proximos.append(item)
            except ValueError:
                continue
        return sorted(proximos, key=lambda x: x['salida'])[:4]

    return {
        "hora_actual": ahora.strftime("%H:%M"),
        "fecha": fecha_hoy,
        "origen": DESTINOS.get(origen, "Desconocido"),
        "destino": DESTINOS.get(destino, "Desconocido"),
        "proximos": {
            "Baja": filtrar_proximos(baja),
            "Alta": filtrar_proximos(alta)
        }
    }
