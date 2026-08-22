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

USUARIOS = {
    1: "General",
    2: "Estudiante",
    3: "Adulto Mayor"
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

def resolver_tipo_usuario(entrada: Union[int, str, None]) -> int:
    if not entrada:
        return 1
    entrada_str = str(entrada).strip()
    if entrada_str.isdigit():
        return int(entrada_str)
    busqueda = normalizar_texto(entrada_str)
    if "estudiante" in busqueda or "tne" in busqueda:
        return 2
    if "adulto mayor" in busqueda or "mayor" in busqueda or "tercera edad" in busqueda or "senior" in busqueda:
        return 3
    return 1

# --- SCRAPING ---
def scrape_itinerarios(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, 'html.parser')
    itinerarios = []
    tabla = soup.find('table', class_='tabla-salidas') or soup.find('table', class_='tablaTren')
    if not tabla:
        for t in soup.find_all('table'):
            if t.find('td'):
                tabla = t
                break
    if not tabla:
        return []

    rows = tabla.find_all('tr')
    for row in rows:
        cols = row.find_all('td')
        if not cols or len(cols) < 4:
            continue

        salida_td = cols[0]
        classes = salida_td.get('class', [])

        if any('baj' in c.lower() for c in classes):
            tipo_tarifa = "Baja"
        elif any('alt' in c.lower() for c in classes):
            tipo_tarifa = "Alta"
        else:
            tipo_tarifa = "General"

        itinerarios.append({
            'salida': salida_td.get_text(strip=True).replace('🕒', '').strip(),
            'llegada': cols[1].get_text(strip=True).replace('🕒', '').strip(),
            'duracion': cols[2].get_text(strip=True).replace('⌛', '').strip(),
            'valor': cols[3].get_text(strip=True).replace('$', '').replace('.', '').strip(),
            'tarifa': tipo_tarifa
        })
    return itinerarios

# Modificado para aceptar fecha y tipo de usuario personalizados
def obtener_todos_los_viajes(
    origen_input: Union[int, str],
    destino_input: Union[int, str],
    fecha_str: Optional[str] = None,
    usuario_input: Union[int, str, None] = 1
):
    id_origen = resolver_id_estacion(origen_input)
    id_destino = resolver_id_estacion(destino_input)
    id_usuario = resolver_tipo_usuario(usuario_input)

    if not id_origen: return None, f"Origen no encontrado: {origen_input}", 0, 0, None, id_usuario
    if not id_destino: return None, f"Destino no encontrado: {destino_input}", 0, 0, None, id_usuario

    # Si no hay fecha, usamos HOY
    ahora_chile = datetime.now(TZ_CHILE)
    if not fecha_str:
        fecha_consulta = ahora_chile.strftime("%Y-%m-%d")
    else:
        fecha_consulta = fecha_str # Formato esperado YYYY-MM-DD

    url = f"https://www.efe.cl/planificador/?empresa=1&hsalida=1&hregreso=&usuario={id_usuario}&ida=1&origen={id_origen}&destino={id_destino}&salida={fecha_consulta}&hran=1"
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200: return None, "Error EFE", id_origen, id_destino, None, id_usuario
    except: return None, "Error Conexión", id_origen, id_destino, None, id_usuario
    
    viajes = scrape_itinerarios(response.text)
    return sorted(viajes, key=lambda x: x['salida']), None, id_origen, id_destino, fecha_consulta, id_usuario

# --- ENDPOINTS ---

@app.get("/estaciones", summary="Lista de estaciones disponibles",
         description="Devuelve todas las estaciones soportadas con su ID interno y nombre.")
def listar_estaciones():
    return {
        "estaciones": [{"id": id_est, "nombre": nombre} for id_est, nombre in DESTINOS.items()]
    }


@app.get("/itinerarios", summary="Itinerarios en JSON",
         description="Devuelve los viajes disponibles entre dos estaciones en formato JSON.")
def itinerarios_json(
    origen: str = Query(..., description="Nombre o ID de la estación de origen"),
    destino: str = Query(..., description="Nombre o ID de la estación de destino"),
    fecha: Optional[str] = Query(None, description="Fecha en formato YYYY-MM-DD (default: hoy en Chile)"),
    usuario: Optional[str] = Query("1", description="Tipo de usuario: 1 = General, 2 = Estudiante, 3 = Adulto Mayor")
):
    resultado = obtener_todos_los_viajes(origen, destino, fecha, usuario)

    todos, error, id_org, id_dst, fecha_usada, id_usr = resultado

    if error:
        status_code = 404 if "no encontrado" in error.lower() else 500
        return JSONResponse(status_code=status_code, content={"error": error})

    viajes = []
    for item in todos:
        precio = int(item['valor']) if item['valor'].isdigit() else 0
        viajes.append({
            "salida": item['salida'],
            "llegada": item['llegada'],
            "duracion": item['duracion'],
            "tarifa": item['tarifa'],
            "precio": precio
        })

    return {
        "origen": {"id": id_org, "nombre": DESTINOS.get(id_org, origen)},
        "destino": {"id": id_dst, "nombre": DESTINOS.get(id_dst, destino)},
        "fecha": fecha_usada,
        "usuario": {"id": id_usr, "tipo": USUARIOS.get(id_usr, "Otro")},
        "viajes": viajes
    }


@app.get("/itinerarios/visual", response_class=HTMLResponse,
         summary="Itinerarios visual (HTML)",
         description="Devuelve una página HTML con los horarios de trenes, optimizada para Atajos de iOS.")
def itinerarios_visual(
    request: Request, 
    origen: str = Query(..., description="Nombre o ID de la estación de origen"),
    destino: str = Query(..., description="Nombre o ID de la estación de destino"),
    fecha: Optional[str] = Query(None, description="Fecha en formato YYYY-MM-DD (default: hoy en Chile)"),
    usuario: Optional[str] = Query("1", description="Tipo de usuario: 1 = General, 2 = Estudiante, 3 = Adulto Mayor")
):
    resultado = obtener_todos_los_viajes(origen, destino, fecha, usuario)

    todos, error, id_org, id_dst, fecha_usada, id_usr = resultado

    if error:
        contexto = {
            "request": request, "origen": origen, "destino": destino,
            "origen_id": id_org or origen, "destino_id": id_dst or destino,
            "hora_actual": "", "fecha_titulo": "", "fecha_raw": "",
            "es_hoy": False, "error": error,
            "pasados": [], "proximos": [], "usuario": id_usr,
            "usuario_tipo": USUARIOS.get(id_usr, "General")
        }
        return templates.TemplateResponse("visual.html", contexto)

    ahora = datetime.now(TZ_CHILE)
    es_hoy = fecha_usada == ahora.strftime("%Y-%m-%d")
    
    fecha_titulo = datetime.strptime(fecha_usada, "%Y-%m-%d").strftime("%d/%m/%Y")

    contexto = {
        "request": request,
        "origen": DESTINOS.get(id_org, origen),
        "destino": DESTINOS.get(id_dst, destino),
        "origen_id": id_org,
        "destino_id": id_dst,
        "hora_actual": ahora.strftime("%H:%M"),
        "fecha_titulo": "Hoy" if es_hoy else fecha_titulo,
        "fecha_raw": fecha_usada,
        "es_hoy": es_hoy,
        "usuario": id_usr,
        "usuario_tipo": USUARIOS.get(id_usr, "General"),
        "pasados": [],
        "proximos": []
    }

    for item in todos:
        tren = item.copy()
        if tren['valor'].isdigit():
            tren['valor'] = f"{int(tren['valor']):,}".replace(',', '.')
        
        # Lógica de Pasado/Futuro
        if es_hoy:
            try:
                h, m = map(int, item['salida'].split(':'))
                hora_tren = ahora.replace(hour=h, minute=m, second=0)
                if hora_tren < ahora:
                    contexto["pasados"].append(tren)
                else:
                    contexto["proximos"].append(tren)
            except: continue
        else:
            contexto["proximos"].append(tren)
            
    return templates.TemplateResponse("visual.html", contexto)