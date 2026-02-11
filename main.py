from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import requests
from bs4 import BeautifulSoup
from typing import List, Tuple, Optional, Dict
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo # Para versiones antiguas de python si fuera necesario

app = FastAPI()

# Configuración de plantillas (carpeta 'templates')
templates = Jinja2Templates(directory="templates")

# Configuración de Zona Horaria Chile
TZ_CHILE = ZoneInfo("America/Santiago")

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
    if not tabla or not tabla.tbody:
        return []

    rows = tabla.tbody.find_all('tr')

    for i, row in enumerate(rows, 1):
        cols = row.find_all('td')
        if not cols: continue
        
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
    # Usamos la hora de Chile para la consulta a EFE
    ahora_chile = datetime.now(TZ_CHILE)
    fecha_consulta = ahora_chile.strftime("%Y-%m-%d")
    
    url = (
        f"https://www.efe.cl/planificador/?empresa=1&hsalida=1&hregreso=&usuario=1"
        f"&ida=1&origen={origen}&destino={destino}&salida={fecha_consulta}&hran=1"
    )
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None, "Error al obtener datos de EFE"
    except requests.RequestException:
        return None, "Error de conexión con EFE"
    
    baja = scrape_itinerarios(response.text, "Baja")
    alta = scrape_itinerarios(response.text, "Alta")
    
    # Ordenar por hora de salida
    todos = sorted(baja + alta, key=lambda x: x['salida'])
    return todos, None

# --- UTILIDADES DE TEXTO ---

def hora_a_texto(hora_str: str) -> str:
    horas_24 = int(hora_str[:2])
    minutos = int(hora_str[3:])

    if horas_24 == 0:
        periodo = "de la madrugada"
        horas_12 = 12
    elif 1 <= horas_24 < 12:
        periodo = "de la mañana"
        horas_12 = horas_24
    elif horas_24 == 12:
        periodo = "del mediodía"
        horas_12 = 12
    elif 13 <= horas_24 < 20:
        periodo = "de la tarde"
        horas_12 = horas_24 - 12
    else:
        periodo = "de la noche"
        horas_12 = horas_24 - 12

    numeros_horas = [
        "doce", "una", "dos", "tres", "cuatro", "cinco", "seis",
        "siete", "ocho", "nueve", "diez", "once", "doce"
    ]
    # Ajuste índice: 1->una (índice 1), 12->doce (índice 0 o 12)
    texto_hora = numeros_horas[horas_12 % 12] 
    if horas_12 == 12: texto_hora = "doce" # Corrección rápida para array

    if minutes == 0:
        texto_minutos = "en punto"
    elif minutes < 10:
        texto_minutos = f"cero {minutos}"
    elif minutes <= 15:
        especiales = {10:"diez", 11:"once", 12:"doce", 13:"trece", 14:"catorce", 15:"quince"}
        texto_minutos = especiales.get(minutos, str(minutos))
    elif minutes < 20:
        texto_minutos = f"dieci{['seis','siete','ocho','nueve'][minutos-16]}"
    elif minutes == 30:
        texto_minutos = "y media"
    else:
        decenas = ["", "", "veinte", "treinta", "cuarenta", "cincuenta"]
        d = minutes // 10
        u = minutes % 10
        if u == 0:
            texto_minutos = decenas[d]
        else:
            # Ajuste simple: "veintiuno" vs "veinte y uno" (coloquial)
            texto_minutos = f"{decenas[d]} y {u}"

    return f"{texto_hora} {texto_minutos} {periodo}"

def minutos_a_texto(min_str):
    num = min_str.replace("min", "").strip()
    return f"{num} minutos"

# --- ENDPOINTS ---

@app.get("/itinerarios")
def itinerarios_completos(
    origen: int = Query(6),
    destino: int = Query(3)
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
    origen: int = Query(6),
    destino: int = Query(3)
):
    ahora = datetime.now(TZ_CHILE)
    todos, error = obtener_todos_los_viajes(origen, destino)
    
    if error:
        return JSONResponse(status_code=500, content={"error": error})

    proximos = []
    for item in todos:
        try:
            h_str, m_str = item['salida'].split(':')
            hora_salida = ahora.replace(hour=int(h_str), minute=int(m_str), second=0, microsecond=0)
            
            # Si la hora ya pasó hoy, ignorar
            if hora_salida >= ahora:
                proximos.append(item)
        except ValueError:
            continue

    # Filtramos para devolver (máximo 4)
    proximos_baja = [p for p in proximos if p['tarifa'] == 'Baja'][:4]
    proximos_alta = [p for p in proximos if p['tarifa'] == 'Alta'][:4]

    return {
        "hora_actual": ahora.strftime("%H:%M"),
        "fecha": ahora.strftime("%Y-%m-%d"),
        "origen": DESTINOS.get(origen, "Desconocido"),
        "destino": DESTINOS.get(destino, "Desconocido"),
        "proximos": {
            "Baja": proximos_baja,
            "Alta": proximos_alta,
            "Todos": proximos[:5] # Lista combinada para la vista visual
        }
    }

@app.get("/itinerarios/ahora/siri")
def itinerarios_siri(origen: int = Query(6), destino: int = Query(3)):
    data = itinerarios_proximos(origen, destino)
    if isinstance(data, JSONResponse): return data
    
    lista = data['proximos']['Todos']
    ahora_str = data['hora_actual']
    
    if not lista:
        mensaje = f"No hay trenes próximos desde {data['origen']} a {data['destino']} por hoy."
    else:
        # Lógica simplificada de texto
        mensaje = f"Son las {ahora_str}. El próximo tren sale a las {lista[0]['salida']}."
        if len(lista) > 1:
            mensaje += f" Luego hay otro a las {lista[1]['salida']}."
        mensaje += f" El viaje dura {lista[0]['duracion']}."

    return {
        "mensaje": mensaje,
        "data_raw": data
    }

@app.get("/itinerarios/ahora/visual", response_class=HTMLResponse)
def itinerarios_visual(
    request: Request,
    origen: int = Query(6),
    destino: int = Query(3)
):
    data = itinerarios_proximos(origen, destino)
    
    # Manejo de errores si la función devuelve JSONResponse
    if isinstance(data, JSONResponse):
        return templates.TemplateResponse("visual.html", {
            "request": request,
            "error": "Hubo un error al conectar con EFE.",
            "proximos": {"Todos": []}
        })

    return templates.TemplateResponse("visual.html", {
        "request": request,
        "origen": data["origen"],
        "destino": data["destino"],
        "fecha": data["fecha"],
        "hora_actual": data["hora_actual"],
        "proximos": data["proximos"]["Todos"] # Pasamos la lista combinada ordenada
    })