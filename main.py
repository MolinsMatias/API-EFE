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

templates = Jinja2Templates(directory="templates")
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

# --- LÓGICA DE PRECIOS ESTUDIANTE ---
def calcular_tarifa_estudiante(precio_str: str, origen: int, destino: int) -> str:
    """Calcula el descuento según el tramo del viaje"""
    try:
        # Limpiamos el precio (quitamos puntos y signos)
        precio_normal = int(precio_str.replace('.', '').replace('$', ''))
        
        # Lógica de tramos EFE:
        # Tramo 1: Estación Central (1) a Hospital (10) -> 48% dcto
        # Tramo 2: San Francisco (11) a Rancagua (13) -> 47% dcto
        
        descuento = 0.0
        
        # Si ambos puntos están en el tramo norte (ID <= 10)
        if origen <= 10 and destino <= 10:
            descuento = 0.48
        # Si ambos puntos están en el tramo sur (ID >= 11)
        elif origen >= 11 and destino >= 11:
            descuento = 0.47
        else:
            # Si cruza tramos (ej: Buin a Rancagua), aplicamos el promedio conservador o el del tramo mayor
            # Por seguridad usaremos 47% si es mixto
            descuento = 0.47
            
        precio_final = int(precio_normal * (1 - descuento))
        
        # Formateamos de vuelta a string con puntos (ej: "680")
        return f"{precio_final:,}".replace(',', '.')
    except:
        return precio_str

# --- SCRAPING ---
def scrape_itinerarios(html: str, tipo_tarifa: str) -> List[Dict]:
    soup = BeautifulSoup(html, 'html.parser')
    itinerarios = []
    tarifa_label = f"Salidas Tarifa {tipo_tarifa}"
    tabla = soup.find('p', string=tarifa_label)
    if not tabla: return []
    tabla = tabla.find_next('table')
    if not tabla or not tabla.tbody: return []
    rows = tabla.tbody.find_all('tr')

    for i, row in enumerate(rows, 1):
        cols = row.find_all('td')
        if not cols: continue
        itinerarios.append({
            'salida': cols[0].get_text(strip=True).replace('🕒', ''),
            'llegada': cols[1].get_text(strip=True).replace('🕒', ''),
            'duracion': cols[2].get_text(strip=True).replace('⌛', ''),
            'valor': cols[3].get_text(strip=True).replace('$', '').replace('.', '').strip(),
            'tarifa': tipo_tarifa
        })
    return itinerarios

def obtener_todos_los_viajes(origen: int, destino: int) -> Tuple[Optional[List[Dict]], Optional[str]]:
    ahora_chile = datetime.now(TZ_CHILE)
    fecha_hoy = ahora_chile.strftime("%Y-%m-%d")
    url = f"https://www.efe.cl/planificador/?empresa=1&hsalida=1&hregreso=&usuario=1&ida=1&origen={origen}&destino={destino}&salida={fecha_hoy}&hran=1"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200: return None, "Error EFE"
    except: return None, "Error Conexión"
    
    baja = scrape_itinerarios(response.text, "Baja")
    alta = scrape_itinerarios(response.text, "Alta")
    return sorted(baja + alta, key=lambda x: x['salida']), None

# --- ENDPOINTS ---

@app.get("/itinerarios/ahora/siri")
def itinerarios_siri(origen: int = Query(...), destino: int = Query(...)):
    todos, error = obtener_todos_los_viajes(origen, destino)
    if error: return JSONResponse(status_code=500, content={"error": error})
    
    # Filtramos próximos
    ahora = datetime.now(TZ_CHILE)
    proximos = []
    for t in todos:
        try:
            h, m = map(int, t['salida'].split(':'))
            if ahora.replace(hour=h, minute=m, second=0) >= ahora:
                # Calculamos precio estudiante para Siri
                t['valor_estudiante'] = calcular_tarifa_estudiante(t['valor'], origen, destino)
                proximos.append(t)
        except: continue
        
    if not proximos:
        mensaje = "No quedan trenes por hoy."
    else:
        tren = proximos[0]
        # Siri ahora te dirá el precio con descuento
        mensaje = f"Próximo tren a las {tren['salida']}. Tarifa estudiante: {tren['valor_estudiante']} pesos."
        
    return {"mensaje": mensaje}

@app.get("/itinerarios/visual", response_class=HTMLResponse)
def itinerarios_visual(request: Request, origen: int = Query(...), destino: int = Query(...)):
    todos, error = obtener_todos_los_viajes(origen, destino)
    
    contexto = {
        "request": request,
        "origen": DESTINOS.get(origen, "Estación"),
        "destino": DESTINOS.get(destino, "Estación"),
        "hora_actual": datetime.now(TZ_CHILE).strftime("%H:%M"),
        "viajes": []
    }
    
    if error:
        contexto["error"] = error
        return templates.TemplateResponse("visual.html", contexto)

    ahora = datetime.now(TZ_CHILE)
    primer_scroll = False

    for item in todos:
        try:
            h, m = map(int, item['salida'].split(':'))
            hora_tren = ahora.replace(hour=h, minute=m, second=0)
            
            tren = item.copy()
            # AQUI CALCULAMOS EL PRECIO ESTUDIANTE
            tren['valor_estudiante'] = calcular_tarifa_estudiante(tren['valor'], origen, destino)
            
            if hora_tren < ahora:
                tren['estado'] = 'pasado'
            else:
                tren['estado'] = 'proximo'
                if not primer_scroll:
                    tren['scroll_target'] = True
                    primer_scroll = True
            
            contexto["viajes"].append(tren)
        except: continue
            
    return templates.TemplateResponse("visual.html", contexto)