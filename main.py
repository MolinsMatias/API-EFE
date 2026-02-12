from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import requests
from bs4 import BeautifulSoup
from typing import List, Tuple, Optional, Dict, Union
from datetime import datetime, timedelta
import unicodedata

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

# --- UTILIDADES ---
def normalizar_texto(texto: str) -> str:
    if not texto: return ""
    texto = str(texto).lower()
    texto = texto.replace('%20', ' ').replace('+', ' ')
    texto = ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    return texto.strip()

def resolver_id_estacion(entrada: Union[int, str]) -> Optional[int]:
    if str(entrada).isdigit(): return int(entrada)
    busqueda = normalizar_texto(entrada)
    for id_est, nombre in DESTINOS.items():
        if busqueda == normalizar_texto(nombre): return id_est
    return None

def calcular_tarifa_estudiante(precio_str: str, origen: int, destino: int) -> str:
    try:
        precio_normal = int(precio_str.replace('.', '').replace('$', ''))
        descuento = 0.47
        if origen <= 10 and destino <= 10: descuento = 0.48
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
    for row in rows:
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

# Modificado para aceptar fecha personalizada
def obtener_todos_los_viajes(origen_input, destino_input, fecha_str: Optional[str] = None):
    id_origen = resolver_id_estacion(origen_input)
    id_destino = resolver_id_estacion(destino_input)

    if not id_origen: return None, f"Origen no encontrado: {origen_input}", 0, 0
    if not id_destino: return None, f"Destino no encontrado: {destino_input}", 0, 0

    # Si no hay fecha, usamos HOY
    ahora_chile = datetime.now(TZ_CHILE)
    if not fecha_str:
        fecha_consulta = ahora_chile.strftime("%Y-%m-%d")
    else:
        fecha_consulta = fecha_str # Formato esperado YYYY-MM-DD

    url = f"https://www.efe.cl/planificador/?empresa=1&hsalida=1&hregreso=&usuario=1&ida=1&origen={id_origen}&destino={id_destino}&salida={fecha_consulta}&hran=1"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200: return None, "Error EFE", id_origen, id_destino
    except: return None, "Error Conexión", id_origen, id_destino
    
    baja = scrape_itinerarios(response.text, "Baja")
    alta = scrape_itinerarios(response.text, "Alta")
    # Retornamos también la fecha usada para mostrarla en el HTML
    return sorted(baja + alta, key=lambda x: x['salida']), None, id_origen, id_destino, fecha_consulta

@app.get("/itinerarios/visual", response_class=HTMLResponse)
def itinerarios_visual(
    request: Request, 
    origen: str = Query(...), 
    destino: str = Query(...),
    fecha: Optional[str] = Query(None, description="Fecha formato YYYY-MM-DD")
):
    todos, error, id_org, id_dst, fecha_usada = obtener_todos_los_viajes(origen, destino, fecha)
    
    ahora = datetime.now(TZ_CHILE)
    es_hoy = fecha_usada == ahora.strftime("%Y-%m-%d")
    
    # Formatear la fecha para que se vea bonita en el título (ej: 12/02/2026)
    fecha_titulo = datetime.strptime(fecha_usada, "%Y-%m-%d").strftime("%d/%m/%Y")

    contexto = {
        "request": request,
        "origen": DESTINOS.get(id_org, origen),
        "destino": DESTINOS.get(id_dst, destino),
        "hora_actual": ahora.strftime("%H:%M"),
        "fecha_titulo": "Hoy" if es_hoy else fecha_titulo,
        "pasados": [],
        "proximos": []
    }
    
    if error:
        contexto["error"] = error
        return templates.TemplateResponse("visual.html", contexto)

    for item in todos:
        tren = item.copy()
        tren['valor_estudiante'] = calcular_tarifa_estudiante(tren['valor'], id_org, id_dst)
        
        # Lógica de Pasado/Futuro
        if es_hoy:
            # Si es hoy, comparamos con la hora actual
            try:
                h, m = map(int, item['salida'].split(':'))
                hora_tren = ahora.replace(hour=h, minute=m, second=0)
                if hora_tren < ahora:
                    contexto["pasados"].append(tren)
                else:
                    contexto["proximos"].append(tren)
            except: continue
        else:
            # Si NO es hoy (es futuro), TODOS son próximos
            contexto["proximos"].append(tren)
            
    return templates.TemplateResponse("visual.html", contexto)