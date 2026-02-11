from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import requests
from bs4 import BeautifulSoup
from typing import List, Tuple, Optional, Dict, Union
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

app = FastAPI()

templates = Jinja2Templates(directory="templates")
TZ_CHILE = ZoneInfo("America/Santiago")

# Diccionario maestro de estaciones
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

# --- FUNCIÓN MÁGICA: TEXTO -> ID ---
def resolver_id_estacion(entrada: Union[int, str]) -> Optional[int]:
    """
    Convierte 'San Francisco' o '11' en el ID 11.
    Es insensible a mayúsculas/minúsculas.
    """
    if str(entrada).isdigit():
        return int(entrada)
    
    entrada_limpia = str(entrada).lower().strip()
    
    # Buscamos en el diccionario por nombre
    for id_est, nombre in DESTINOS.items():
        if nombre.lower() == entrada_limpia:
            return id_est
    return None

# --- LÓGICA DE PRECIOS ESTUDIANTE ---
def calcular_tarifa_estudiante(precio_str: str, origen: int, destino: int) -> str:
    try:
        precio_normal = int(precio_str.replace('.', '').replace('$', ''))
        descuento = 0.0
        # Tramo Norte (Estación Central - Hospital) -> 48%
        if origen <= 10 and destino <= 10: descuento = 0.48
        # Tramo Sur (San Francisco - Rancagua) -> 47%
        elif origen >= 11 and destino >= 11: descuento = 0.47
        # Mixto (Por defecto usamos el del sur) -> 47%
        else: descuento = 0.47
        
        precio_final = int(precio_normal * (1 - descuento))
        return f"{precio_final:,}".replace(',', '.')
    except: return precio_str

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

def obtener_todos_los_viajes(origen_input: Union[str, int], destino_input: Union[str, int]) -> Tuple[Optional[List[Dict]], Optional[str], int, int]:
    # Convertimos nombres a IDs
    id_origen = resolver_id_estacion(origen_input)
    id_destino = resolver_id_estacion(destino_input)

    if not id_origen: return None, f"Estación origen '{origen_input}' no encontrada", 0, 0
    if not id_destino: return None, f"Estación destino '{destino_input}' no encontrada", 0, 0

    ahora_chile = datetime.now(TZ_CHILE)
    fecha_hoy = ahora_chile.strftime("%Y-%m-%d")
    
    url = f"https://www.efe.cl/planificador/?empresa=1&hsalida=1&hregreso=&usuario=1&ida=1&origen={id_origen}&destino={id_destino}&salida={fecha_hoy}&hran=1"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200: return None, "Error EFE", id_origen, id_destino
    except: return None, "Error Conexión", id_origen, id_destino
    
    baja = scrape_itinerarios(response.text, "Baja")
    alta = scrape_itinerarios(response.text, "Alta")
    return sorted(baja + alta, key=lambda x: x['salida']), None, id_origen, id_destino

# --- ENDPOINTS ---

@app.get("/itinerarios/ahora/siri")
def itinerarios_siri(
    origen: str = Query(..., description="Nombre o ID origen"), 
    destino: str = Query(..., description="Nombre o ID destino")
):
    todos, error, id_org, id_dst = obtener_todos_los_viajes(origen, destino)
    
    if error: return JSONResponse(status_code=500, content={"error": error})
    
    ahora = datetime.now(TZ_CHILE)
    proximos = []
    for t in todos:
        try:
            h, m = map(int, t['salida'].split(':'))
            if ahora.replace(hour=h, minute=m, second=0) >= ahora:
                t['valor_estudiante'] = calcular_tarifa_estudiante(t['valor'], id_org, id_dst)
                proximos.append(t)
        except: continue
        
    if not proximos: mensaje = "No quedan trenes por hoy."
    else:
        tren = proximos[0]
        mensaje = f"Próximo tren a las {tren['salida']}. Tarifa estudiante: {tren['valor_estudiante']} pesos."
    return {"mensaje": mensaje}

@app.get("/itinerarios/visual", response_class=HTMLResponse)
def itinerarios_visual(
    request: Request, 
    origen: str = Query(..., description="Nombre o ID origen"), 
    destino: str = Query(..., description="Nombre o ID destino")
):
    todos, error, id_org, id_dst = obtener_todos_los_viajes(origen, destino)
    
    contexto = {
        "request": request,
        "origen": DESTINOS.get(id_org, origen),
        "destino": DESTINOS.get(id_dst, destino),
        "hora_actual": datetime.now(TZ_CHILE).strftime("%H:%M"),
        "pasados": [],
        "proximos": []
    }
    
    if error:
        contexto["error"] = error
        return templates.TemplateResponse("visual.html", contexto)

    ahora = datetime.now(TZ_CHILE)

    for item in todos:
        try:
            h, m = map(int, item['salida'].split(':'))
            hora_tren = ahora.replace(hour=h, minute=m, second=0)
            
            tren = item.copy()
            # Calculamos tarifa usando los IDs numéricos resueltos
            tren['valor_estudiante'] = calcular_tarifa_estudiante(tren['valor'], id_org, id_dst)
            
            if hora_tren < ahora:
                contexto["pasados"].append(tren)
            else:
                contexto["proximos"].append(tren)
        except: continue
            
    return templates.TemplateResponse("visual.html", contexto)