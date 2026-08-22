from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from bs4 import BeautifulSoup
import requests
from typing import Optional, Union, Dict, Any, Tuple
import unicodedata
from datetime import datetime
import time
import math

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

app = FastAPI(
    title="API EFE Trenes de Chile",
    description="API para consultar itinerarios de trenes EFE (Servicio Nos/Rancagua). Incluye endpoints JSON, cálculo por GPS y vista web visual optimizada para Atajos de iOS.",
    version="2.2.0"
)

# Configuración de zona horaria oficial de Chile
TZ_CHILE = ZoneInfo("America/Santiago")

# Configuración de plantillas Jinja2
templates = Jinja2Templates(directory="templates")

# Diccionario de estaciones y sus IDs oficiales en la web de EFE
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

# Coordenadas GPS oficiales de cada estación para geolocalización inteligente
ESTACIONES_COORDENADAS = {
    1: {"nombre": "Estación Central", "lat": -33.4517, "lon": -70.6791},
    3: {"nombre": "San Bernardo", "lat": -33.5936, "lon": -70.7028},
    6: {"nombre": "Buin Zoo", "lat": -33.7132, "lon": -70.7335},
    7: {"nombre": "Buin", "lat": -33.7314, "lon": -70.7381},
    8: {"nombre": "Linderos", "lat": -33.7667, "lon": -70.7369},
    9: {"nombre": "Paine", "lat": -33.8115, "lon": -70.7412},
    10: {"nombre": "Hospital", "lat": -33.8732, "lon": -70.7588},
    11: {"nombre": "San Francisco", "lat": -33.9877, "lon": -70.7058},
    12: {"nombre": "Graneros", "lat": -34.0628, "lon": -70.7242},
    13: {"nombre": "Rancagua", "lat": -34.1678, "lon": -70.7331}
}

# Diccionario oficial de tipos de usuario soportados por el planificador de EFE
USUARIOS = {
    1: "General",
    2: "Estudiante",
    3: "Adulto Mayor"
}

# --- CACHÉ EN MEMORIA (TTL: 60 SEGUNDOS) ---
CACHE_ITINERARIOS: Dict[Tuple[int, int, str, int], Tuple[float, Any]] = {}
CACHE_TTL_SEGUNDOS = 60


def normalizar_texto(texto: str) -> str:
    """Elimina tildes, espacios extra y pasa a minúsculas para comparaciones."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', texto.lower().strip())
        if unicodedata.category(c) != 'Mn'
    )


def resolver_id_estacion(valor: Union[int, str]) -> Optional[int]:
    """Resuelve un ID de estación a partir de un entero o del nombre textual."""
    if isinstance(valor, int) or (isinstance(valor, str) and valor.isdigit()):
        v_int = int(valor)
        if v_int in DESTINOS:
            return v_int

    busqueda = normalizar_texto(str(valor))
    for id_est, nombre in DESTINOS.items():
        if busqueda == normalizar_texto(nombre):
            return id_est

    # Búsqueda por coincidencia parcial
    for id_est, nombre in DESTINOS.items():
        if busqueda in normalizar_texto(nombre):
            return id_est

    return None


def resolver_tipo_usuario(valor: Union[int, str, None]) -> int:
    """
    Normaliza el parámetro de usuario:
      - 1: General (Normal / Adulto)
      - 2: Estudiante (TNE)
      - 3: Adulto Mayor
    """
    if valor is None:
        return 1

    v_str = str(valor).strip().lower()

    if v_str in ("1", "general", "normal", "adulto"):
        return 1
    elif v_str in ("2", "estudiante", "tne", "alumno"):
        return 2
    elif v_str in ("3", "adulto mayor", "adulto_mayor", "mayor", "tercera edad"):
        return 3

    return 1


def encontrar_estacion_mas_cercana(lat: float, lon: float) -> Tuple[int, str, float]:
    """Calcula la distancia haversine y devuelve (id_estacion, nombre_estacion, distancia_km)."""
    R = 6371.0 # Radio de la Tierra en km
    mejor_id = 1
    mejor_dist = float('inf')
    
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    
    for est_id, info in ESTACIONES_COORDENADAS.items():
        dlat = math.radians(info["lat"]) - lat_rad
        dlon = math.radians(info["lon"]) - lon_rad
        a = math.sin(dlat / 2)**2 + math.cos(lat_rad) * math.cos(math.radians(info["lat"])) * math.sin(dlon / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distancia = R * c
        if distancia < mejor_dist:
            mejor_dist = distancia
            mejor_id = est_id
            
    return mejor_id, ESTACIONES_COORDENADAS[mejor_id]["nombre"], round(mejor_dist, 2)


def resolver_origen_destino_geolocalizados(
    origen: Optional[str],
    destino: Optional[str],
    lat: Optional[float],
    lon: Optional[float]
) -> Tuple[Optional[str], Optional[str], Optional[Dict[str, Any]]]:
    """
    Si se pasa lat y lon pero no origen, calcula la estación más cercana automáticamente.
    Si tampoco se pasa destino, determina la dirección lógica:
      - Si estás en Estación Central (1), destino por defecto es Rancagua (13).
      - Si estás en cualquier otra estación del sur, destino por defecto es Estación Central (1).
    """
    geo_info = None
    if lat is not None and lon is not None:
        cercana_id, cercana_nom, dist_km = encontrar_estacion_mas_cercana(lat, lon)
        geo_info = {
            "estacion_detectada": cercana_nom,
            "distancia_km": dist_km,
            "lat": lat,
            "lon": lon
        }
        if not origen:
            origen = str(cercana_id)
        if not destino:
            # Infiere dirección natural
            destino = "13" if cercana_id == 1 else "1"
            
    return origen, destino, geo_info


# --- SCRAPER EFE ---

def scrape_itinerarios(html: str):
    """
    Scraper adaptado al nuevo formato HTML de EFE (2026).
    Extrae salidas desde la tabla unificada e identifica la tarifa por clases CSS (hor_Alta / hor_Bajo).
    """
    soup = BeautifulSoup(html, 'html.parser')
    itinerarios = []

    tabla = soup.find('table', class_='tabla-salidas') or soup.find('table', class_='tablaTren')
    if not tabla:
        return itinerarios

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


def obtener_todos_los_viajes(
    origen_input: Union[int, str],
    destino_input: Union[int, str],
    fecha_str: Optional[str] = None,
    usuario_input: Union[int, str, None] = 1
):
    id_origen = resolver_id_estacion(origen_input)
    id_destino = resolver_id_estacion(destino_input)
    id_usuario = resolver_tipo_usuario(usuario_input)

    if not id_origen:
        return None, f"Origen no encontrado: {origen_input}", 0, 0, None, id_usuario
    if not id_destino:
        return None, f"Destino no encontrado: {destino_input}", 0, 0, None, id_usuario

    # Si no hay fecha, usamos HOY en Chile
    ahora_chile = datetime.now(TZ_CHILE)
    fecha_consulta = fecha_str if fecha_str else ahora_chile.strftime("%Y-%m-%d")

    url = f"https://www.efe.cl/planificador/?empresa=1&hsalida=1&hregreso=&usuario={id_usuario}&ida=1&origen={id_origen}&destino={id_destino}&salida={fecha_consulta}&hran=1"
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None, "Error EFE", id_origen, id_destino, None, id_usuario
    except:
        return None, "Error Conexión", id_origen, id_destino, None, id_usuario
    
    viajes = scrape_itinerarios(response.text)
    return sorted(viajes, key=lambda x: x['salida']), None, id_origen, id_destino, fecha_consulta, id_usuario


def obtener_todos_los_viajes_con_cache(
    origen_input: Union[int, str],
    destino_input: Union[int, str],
    fecha_str: Optional[str] = None,
    usuario_input: Union[int, str, None] = 1
):
    """
    Caché en memoria de 60 segundos por combinación (origen, destino, fecha, usuario).
    Reduce la latencia de ~800ms a ~2ms en consultas repetidas.
    """
    id_org = resolver_id_estacion(origen_input)
    id_dst = resolver_id_estacion(destino_input)
    id_usr = resolver_tipo_usuario(usuario_input)
    ahora_chile = datetime.now(TZ_CHILE)
    fecha_consulta = fecha_str if fecha_str else ahora_chile.strftime("%Y-%m-%d")

    if id_org and id_dst:
        cache_key = (id_org, id_dst, fecha_consulta, id_usr)
        now = time.time()
        if cache_key in CACHE_ITINERARIOS:
            cached_time, cached_result = CACHE_ITINERARIOS[cache_key]
            if now - cached_time < CACHE_TTL_SEGUNDOS:
                return cached_result

    # Si no está en caché o expiró, hacemos la consulta real
    resultado = obtener_todos_los_viajes(origen_input, destino_input, fecha_str, usuario_input)

    # Solo guardamos en caché si la consulta fue exitosa (no None)
    if id_org and id_dst and resultado[0] is not None:
        cache_key = (id_org, id_dst, fecha_consulta, id_usr)
        CACHE_ITINERARIOS[cache_key] = (time.time(), resultado)

    return resultado


# --- ENDPOINTS ---

@app.get(
    "/estaciones",
    summary="Lista de estaciones disponibles",
    description="Devuelve todas las estaciones soportadas con su ID interno, nombre oficial y coordenadas GPS."
)
def listar_estaciones():
    return {
        "estaciones": [
            {
                "id": id_est,
                "nombre": info["nombre"],
                "lat": info["lat"],
                "lon": info["lon"]
            }
            for id_est, info in ESTACIONES_COORDENADAS.items()
        ]
    }


@app.get(
    "/itinerarios",
    summary="Itinerarios en JSON",
    description="Devuelve la lista completa de viajes programados entre dos estaciones en formato JSON (con soporte de coordenadas GPS y caché de 1 minuto)."
)
def itinerarios_json(
    origen: Optional[str] = Query(None, description="Nombre o ID de la estación de origen"),
    destino: Optional[str] = Query(None, description="Nombre o ID de la estación de destino"),
    lat: Optional[float] = Query(None, description="Latitud GPS actual para detectar estación más cercana"),
    lon: Optional[float] = Query(None, description="Longitud GPS actual para detectar estación más cercana"),
    fecha: Optional[str] = Query(None, description="Fecha en formato YYYY-MM-DD (default: hoy en Chile)"),
    usuario: Optional[str] = Query("1", description="Tipo de usuario: 1 = General, 2 = Estudiante, 3 = Adulto Mayor")
):
    origen, destino, geo_info = resolver_origen_destino_geolocalizados(origen, destino, lat, lon)

    if not origen or not destino:
        return JSONResponse(
            status_code=400,
            content={"error": "Debes proporcionar 'origen' y 'destino', o enviar 'lat' y 'lon' para autodetección."}
        )

    resultado = obtener_todos_los_viajes_con_cache(origen, destino, fecha, usuario)
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
        "geolocalizacion": geo_info,
        "fecha": fecha_usada,
        "usuario": {"id": id_usr, "tipo": USUARIOS.get(id_usr, "General")},
        "viajes": viajes
    }


@app.get(
    "/proximo",
    summary="Próximo tren disponible (Optimizado para Siri, Apple Watch y Widgets)",
    description="Devuelve el próximo tren a partir de la hora actual con minutos restantes y una frase preformateada lista para que Siri la lea por voz. Soporta coordenadas GPS (lat/lon) para calcular automáticamente la estación más cercana."
)
def proximo_tren_endpoint(
    origen: Optional[str] = Query(None, description="Nombre o ID de la estación de origen (opcional si envías lat/lon)"),
    destino: Optional[str] = Query(None, description="Nombre o ID de la estación de destino (opcional si envías lat/lon)"),
    lat: Optional[float] = Query(None, description="Latitud GPS actual del usuario para autodetectar la estación más cercana"),
    lon: Optional[float] = Query(None, description="Longitud GPS actual del usuario para autodetectar la estación más cercana"),
    fecha: Optional[str] = Query(None, description="Fecha en formato YYYY-MM-DD (default: hoy en Chile)"),
    usuario: Optional[str] = Query("1", description="Tipo de usuario: 1 = General, 2 = Estudiante, 3 = Adulto Mayor")
):
    origen, destino, geo_info = resolver_origen_destino_geolocalizados(origen, destino, lat, lon)

    if not origen or not destino:
        return JSONResponse(
            status_code=400,
            content={"error": "Debes proporcionar 'origen' y 'destino', o enviar 'lat' y 'lon' para autodetección por GPS."}
        )

    resultado = obtener_todos_los_viajes_con_cache(origen, destino, fecha, usuario)
    todos, error, id_org, id_dst, fecha_usada, id_usr = resultado

    if error or todos is None:
        status_code = 404 if "no encontrado" in (error or "").lower() else 502
        return JSONResponse(
            status_code=status_code,
            content={"error": error or "No fue posible obtener los itinerarios de EFE"}
        )

    ahora = datetime.now(TZ_CHILE)
    es_hoy = fecha_usada == ahora.strftime("%Y-%m-%d")
    nombre_org = DESTINOS.get(id_org, str(origen))
    nombre_dst = DESTINOS.get(id_dst, str(destino))
    tipo_usr = USUARIOS.get(id_usr, "General")

    proximos = []
    for item in todos:
        tren = item.copy()
        valor_num = int(tren["valor"]) if tren["valor"].isdigit() else 0
        tren["valor_num"] = valor_num

        if es_hoy:
            try:
                h, m = map(int, item["salida"].split(":"))
                hora_tren = ahora.replace(hour=h, minute=m, second=0)
                diff = int((hora_tren - ahora).total_seconds() / 60)
                if hora_tren >= ahora:
                    tren["minutos_restantes"] = diff
                    if diff > 60:
                        hrs = diff // 60
                        mins = diff % 60
                        tren["relativo"] = f"Sale en {hrs}h {mins}m"
                    elif diff > 0:
                        tren["relativo"] = f"Sale en {diff} min"
                    else:
                        tren["relativo"] = "Saliendo ahora"
                    proximos.append(tren)
            except:
                continue
        else:
            tren["minutos_restantes"] = None
            tren["relativo"] = "Programado"
            proximos.append(tren)

    # Si no quedan más trenes para hoy
    if not proximos:
        return {
            "origen": {"id": id_org, "nombre": nombre_org},
            "destino": {"id": id_dst, "nombre": nombre_dst},
            "geolocalizacion": geo_info,
            "fecha": fecha_usada,
            "usuario": {"id": id_usr, "tipo": tipo_usr},
            "hay_salidas": False,
            "proximo_tren": None,
            "siguiente_tren": None,
            "texto_siri": f"Ya no quedan más salidas de trenes hoy desde {nombre_org} hacia {nombre_dst}.",
            "total_restantes_hoy": 0
        }

    siguiente = proximos[0]
    segundo = proximos[1] if len(proximos) > 1 else None

    # Generación de frase optimizada para Siri
    if es_hoy:
        mins = siguiente["minutos_restantes"]
        if mins == 0:
            texto_siri = f"El próximo tren desde {nombre_org} hacia {nombre_dst} está saliendo ahora, a las {siguiente['salida']}."
        elif mins == 1:
            texto_siri = f"El próximo tren desde {nombre_org} hacia {nombre_dst} sale en 1 minuto, a las {siguiente['salida']}."
        elif mins < 60:
            texto_siri = f"El próximo tren desde {nombre_org} hacia {nombre_dst} sale en {mins} minutos, a las {siguiente['salida']}."
        else:
            hrs = mins // 60
            rest = mins % 60
            texto_siri = f"El próximo tren desde {nombre_org} hacia {nombre_dst} sale en {hrs} horas y {rest} minutos, a las {siguiente['salida']}."
    else:
        texto_siri = f"La primera salida programada desde {nombre_org} hacia {nombre_dst} es a las {siguiente['salida']}."

    return {
        "origen": {"id": id_org, "nombre": nombre_org},
        "destino": {"id": id_dst, "nombre": nombre_dst},
        "geolocalizacion": geo_info,
        "fecha": fecha_usada,
        "usuario": {"id": id_usr, "tipo": tipo_usr},
        "hay_salidas": True,
        "proximo_tren": {
            "salida": siguiente["salida"],
            "llegada": siguiente["llegada"],
            "duracion": siguiente["duracion"],
            "tarifa": siguiente["tarifa"],
            "precio": siguiente["valor_num"],
            "minutos_restantes": siguiente["minutos_restantes"],
            "relativo": siguiente["relativo"]
        },
        "siguiente_tren": {
            "salida": segundo["salida"],
            "llegada": segundo["llegada"],
            "duracion": segundo["duracion"],
            "tarifa": segundo["tarifa"],
            "precio": segundo["valor_num"],
            "minutos_restantes": segundo["minutos_restantes"],
            "relativo": segundo["relativo"]
        } if segundo else None,
        "texto_siri": texto_siri,
        "total_restantes_hoy": len(proximos)
    }


@app.get(
    "/itinerarios/visual",
    response_class=HTMLResponse,
    summary="Itinerarios visual (HTML)",
    description="Devuelve una página HTML estilo Apple iOS 26 Liquid Glass con contadores en vivo, optimizada para Atajos de iOS. Soporta autodetección de estación por GPS (lat/lon)."
)
def itinerarios_visual(
    request: Request, 
    origen: Optional[str] = Query(None, description="Nombre o ID de la estación de origen"),
    destino: Optional[str] = Query(None, description="Nombre o ID de la estación de destino"),
    lat: Optional[float] = Query(None, description="Latitud GPS para autodetección"),
    lon: Optional[float] = Query(None, description="Longitud GPS para autodetección"),
    fecha: Optional[str] = Query(None, description="Fecha en formato YYYY-MM-DD (default: hoy en Chile)"),
    usuario: Optional[str] = Query("1", description="Tipo de usuario: 1 = General, 2 = Estudiante, 3 = Adulto Mayor")
):
    origen, destino, _ = resolver_origen_destino_geolocalizados(origen, destino, lat, lon)

    if not origen or not destino:
        contexto = {
            "request": request, "origen": "Desconocido", "destino": "Desconocido",
            "origen_id": 0, "destino_id": 0,
            "hora_actual": "", "fecha_titulo": "", "fecha_raw": "",
            "es_hoy": False, "error": "Debes especificar origen y destino o enviar coordenadas GPS (lat y lon).",
            "pasados": [], "proximos": [], "usuario": 1,
            "usuario_tipo": "General"
        }
        return templates.TemplateResponse(request=request, name="visual.html", context=contexto)

    resultado = obtener_todos_los_viajes_con_cache(origen, destino, fecha, usuario)
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
        return templates.TemplateResponse(request=request, name="visual.html", context=contexto)

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
        
        # Lógica de Pasado/Futuro y tiempo relativo calculado en el servidor
        if es_hoy:
            try:
                h, m = map(int, item['salida'].split(':'))
                hora_tren = ahora.replace(hour=h, minute=m, second=0)
                diff_minutos = int((hora_tren - ahora).total_seconds() / 60)
                tren['minutos_restantes'] = diff_minutos
                
                if diff_minutos > 60:
                    hrs = diff_minutos // 60
                    mins = diff_minutos % 60
                    tren['relativo'] = f"Sale en {hrs}h {mins}m"
                    tren['relativo_corto'] = f"En {hrs}h {mins}m"
                    tren['es_urgente'] = False
                elif diff_minutos > 5:
                    tren['relativo'] = f"Sale en {diff_minutos} min"
                    tren['relativo_corto'] = f"En {diff_minutos} min"
                    tren['es_urgente'] = False
                elif diff_minutos > 0:
                    tren['relativo'] = f"Sale en {diff_minutos} min"
                    tren['relativo_corto'] = f"En {diff_minutos} min"
                    tren['es_urgente'] = True
                elif diff_minutos == 0:
                    tren['relativo'] = "Saliendo ahora"
                    tren['relativo_corto'] = "Saliendo ahora"
                    tren['es_urgente'] = True
                else:
                    tren['relativo'] = f"Partió hace {abs(diff_minutos)} min"
                    tren['relativo_corto'] = ""
                    tren['es_urgente'] = True

                if hora_tren < ahora:
                    contexto["pasados"].append(tren)
                else:
                    contexto["proximos"].append(tren)
            except: continue
        else:
            tren['relativo'] = ""
            tren['relativo_corto'] = ""
            tren['es_urgente'] = False
            contexto["proximos"].append(tren)
            
    return templates.TemplateResponse(request=request, name="visual.html", context=contexto)