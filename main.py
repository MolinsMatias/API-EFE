from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import requests
from bs4 import BeautifulSoup
from typing import List, Tuple, Optional, Dict
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

app = FastAPI()

# Configuración de plantillas
templates = Jinja2Templates(directory="templates")

# Configuración Zona Horaria Chile
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

# --- LÓGICA DE SCRAPING ---

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
    ahora_chile = datetime.now(TZ_CHILE)
    fecha_hoy = ahora_chile.strftime("%Y-%m-%d")
    
    url = (
        f"https://www.efe.cl/planificador/?empresa=1&hsalida=1&hregreso=&usuario=1"
        f"&ida=1&origen={origen}&destino={destino}&salida={fecha_hoy}&hran=1"
    )
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None, "Error al obtener datos"
    except Exception as e:
        return None, f"Error de conexión: {str(e)}"
    
    baja = scrape_itinerarios(response.text, "Baja")
    alta = scrape_itinerarios(response.text, "Alta")
    todos = sorted(baja + alta, key=lambda x: x['salida'])
    
    return todos, None

# --- UTILIDADES ---

def filtrar_proximos(lista_todos: List[Dict]) -> List[Dict]:
    ahora = datetime.now(TZ_CHILE)
    proximos = []
    for item in lista_todos:
        try:
            h, m = map(int, item['salida'].split(':'))
            # Creamos un objeto datetime con la hora del tren para hoy
            hora_salida = ahora.replace(hour=h, minute=m, second=0, microsecond=0)
            
            # Si la hora es mayor o igual a la actual, sirve
            if hora_salida >= ahora:
                proximos.append(item)
        except ValueError:
            continue
    return proximos

def hora_a_texto(hora_str: str) -> str:
    """Convierte HH:MM a texto natural para Siri"""
    try:
        horas, minutos = map(int, hora_str.split(':'))
    except:
        return hora_str

    periodo = "de la mañana"
    if horas == 0: periodo = "de la madrugada"; horas_12 = 12
    elif horas == 12: periodo = "del mediodía"; horas_12 = 12
    elif horas > 12: periodo = "de la tarde" if horas < 20 else "de la noche"; horas_12 = horas - 12
    else: horas_12 = horas

    numeros = ["doce", "una", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce"]
    texto_h = numeros[horas_12 % 12]
    if horas_12 == 12: texto_h = "doce"

    if minutos == 0: texto_m = "en punto"
    elif minutos < 10: texto_m = f"cero {minutos}"
    elif minutos <= 15:
        especiales = {10:"diez", 11:"once", 12:"doce", 13:"trece", 14:"catorce", 15:"quince"}
        texto_m = especiales.get(minutos, str(minutos))
    elif minutos < 20: texto_m = f"dieci{minutos-10}" # Simplificado
    elif minutos == 30: texto_m = "y media"
    else: texto_m = f"{minutos}"

    return f"{texto_h} {texto_m} {periodo}"

# --- ENDPOINTS ---

@app.get("/itinerarios/ahora/siri")
def itinerarios_siri(
    origen: int = Query(..., description="Código origen"),
    destino: int = Query(..., description="Código destino")
):
    """Endpoint optimizado para lectura de voz (Siri)"""
    todos, error = obtener_todos_los_viajes(origen, destino)
    if error:
        return JSONResponse(status_code=500, content={"error": error})
    
    proximos = filtrar_proximos(todos)
    ahora_str = datetime.now(TZ_CHILE).strftime("%H:%M")
    
    if not proximos:
        mensaje = f"No hay más trenes desde {DESTINOS.get(origen)} hacia {DESTINOS.get(destino)} por hoy."
    else:
        tren = proximos[0]
        mensaje = f"Son las {hora_a_texto(ahora_str)}. El próximo tren sale a las {hora_a_texto(tren['salida'])} y cuesta {tren['valor']} pesos."
        
        if len(proximos) > 1:
            siguiente = proximos[1]
            mensaje += f" Después, hay otro a las {siguiente['salida']}."

    return {
        "mensaje": mensaje,
        "data": proximos[:4]
    }

@app.get("/itinerarios/visual", response_class=HTMLResponse)
def itinerarios_visual(
    request: Request,
    origen: int = Query(..., description="Código origen"),
    destino: int = Query(..., description="Código destino")
):
    """Endpoint visual para 'Mostrar vista web' en Atajos iOS"""
    todos, error = obtener_todos_los_viajes(origen, destino)
    
    contexto = {
        "request": request,
        "origen": DESTINOS.get(origen, "Desconocido"),
        "destino": DESTINOS.get(destino, "Desconocido"),
        "hora_actual": datetime.now(TZ_CHILE).strftime("%H:%M"),
        "proximos": []
    }

    if error:
        contexto["error"] = error
        return templates.TemplateResponse("visual.html", contexto)

    proximos = filtrar_proximos(todos)
    contexto["proximos"] = proximos[:6] # Mostramos hasta 6 próximos
    
    return templates.TemplateResponse("visual.html", contexto)