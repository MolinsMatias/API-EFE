# API-EFE

API-EFE es una aplicación desarrollada con **FastAPI** que permite consultar los itinerarios, horarios y tarifas de los trenes de EFE (Empresa de los Ferrocarriles del Estado) en Chile. Utiliza técnicas de *web scraping* para obtener la información actualizada directamente desde el sitio web oficial de EFE.

## 🚀 Características

- **API JSON:** Endpoint REST que devuelve itinerarios en formato JSON, ideal para integrar en cualquier aplicación.
- **Interfaz Visual (HTML):** Página web optimizada para consultar horarios directamente desde el navegador o Atajos de iOS.
- **Consulta de Itinerarios:** Busca horarios de trenes entre distintas estaciones habilitadas (Estación Central, San Bernardo, Rancagua, Buin Zoo, etc.).
- **Búsqueda por Fecha:** Permite consultar los horarios para el día actual o para una fecha futura.
- **Tarifas Normal y Estudiante:** Muestra ambos precios. En la vista visual, el parámetro `tarifa` permite alternar entre vista de estudiante (con TNE) y normal.
- **Lista de Estaciones:** Endpoint dedicado para consultar todas las estaciones soportadas con sus IDs.
- **Estado de Trenes (Pasados/Próximos):** Diferencia visualmente los trenes que ya pasaron de los que están próximos a salir según la hora local de Chile.
- **Documentación Automática:** Swagger UI y ReDoc disponibles en `/docs` y `/redoc`.

## 🛠️ Tecnologías Utilizadas

- [Python 3](https://www.python.org/)
- [FastAPI](https://fastapi.tiangolo.com/) - Framework web para la API.
- [BeautifulSoup4](https://pypi.org/project/beautifulsoup4/) - Para el scraping de datos desde la web de EFE.
- [Jinja2](https://jinja.palletsprojects.com/) - Motor de plantillas HTML.
- [Uvicorn](https://www.uvicorn.org/) - Servidor ASGI.
- [Docker](https://www.docker.com/) - Para la contenerización de la aplicación.

## ⚙️ Requisitos Previos

Asegúrate de tener instalado Python en tu sistema (versión recomendada 3.8 o superior).

## 📦 Instalación y Ejecución Local

1. **Clonar el repositorio** (o descargar los archivos):
   ```bash
   git clone <url-del-repositorio>
   cd API-EFE
   ```

2. **Instalar las dependencias:**
   Se recomienda usar un entorno virtual, pero puedes instalar los requerimientos directamente con:
   ```bash
   pip install -r requirements.txt
   ```

3. **Ejecutar la aplicación:**
   Puedes levantar el servidor de desarrollo utilizando `uvicorn`:
   ```bash
   uvicorn main:app --reload
   ```
   *Alternativa en Windows:* Puedes ejecutar el archivo `run.bat` incluido en el proyecto.

4. **Acceder a la aplicación:**
   Abre tu navegador web e ingresa a:
   `http://localhost:8000/itinerarios/visual?origen=Estación Central&destino=Rancagua`

## 🐳 Ejecución con Docker

El proyecto incluye un `Dockerfile` listo para usar. Para levantar la aplicación usando Docker:

1. **Construir la imagen:**
   ```bash
   docker build -t api-efe .
   ```

2. **Ejecutar el contenedor:**
   ```bash
   docker run -d -p 8000:8080 api-efe
   ```

## 📍 Endpoints

### `GET /estaciones`

Devuelve la lista de estaciones soportadas con su ID interno.

**Ejemplo de respuesta:**
```json
{
  "estaciones": [
    { "id": 1, "nombre": "Estación Central" },
    { "id": 3, "nombre": "San Bernardo" },
    { "id": 6, "nombre": "Buin Zoo" }
  ]
}
```

---

### `GET /itinerarios`

Devuelve los viajes disponibles entre dos estaciones en **formato JSON**, incluyendo precios normal y estudiante.

| Parámetro | Tipo | Obligatorio | Descripción |
|-----------|------|:-----------:|-------------|
| `origen`  | str  | ✅ | Nombre o ID de la estación de origen |
| `destino` | str  | ✅ | Nombre o ID de la estación de destino |
| `fecha`   | str  | ❌ | Fecha en formato `YYYY-MM-DD` (default: hoy en Chile) |

**Ejemplo:**
```
GET /itinerarios?origen=1&destino=13
GET /itinerarios?origen=Estación Central&destino=Rancagua&fecha=2026-07-20
```

**Ejemplo de respuesta:**
```json
{
  "origen": { "id": 1, "nombre": "Estación Central" },
  "destino": { "id": 13, "nombre": "Rancagua" },
  "fecha": "2026-07-15",
  "viajes": [
    {
      "salida": "06:30",
      "llegada": "08:05",
      "duracion": "1h 35min",
      "tarifa": "Baja",
      "precio_normal": 2100,
      "precio_estudiante": 1113
    }
  ]
}
```

---

### `GET /itinerarios/visual`

Devuelve una **página HTML** con los horarios de trenes. Ideal para consumir desde Atajos de iOS o para visualización directa en el navegador.

| Parámetro | Tipo | Obligatorio | Descripción |
|-----------|------|:-----------:|-------------|
| `origen`  | str  | ✅ | Nombre o ID de la estación de origen |
| `destino` | str  | ✅ | Nombre o ID de la estación de destino |
| `fecha`   | str  | ❌ | Fecha en formato `YYYY-MM-DD` (default: hoy en Chile) |
| `tarifa`  | str  | ❌ | `estudiante` (default) o `normal` |

**Ejemplo:**
```
GET /itinerarios/visual?origen=Estación Central&destino=Rancagua
GET /itinerarios/visual?origen=1&destino=13&tarifa=normal
```

## 🚉 Estaciones Soportadas

Actualmente, el sistema mapea internamente las siguientes estaciones. Se puede utilizar el **nombre** o el **ID** como parámetro de origen/destino:

| ID | Estación |
|----|----------|
| 1  | Estación Central |
| 3  | San Bernardo |
| 6  | Buin Zoo |
| 7  | Buin |
| 8  | Linderos |
| 9  | Paine |
| 10 | Hospital |
| 11 | San Francisco |
| 12 | Graneros |
| 13 | Rancagua |

> **Nota:** Los IDs no son consecutivos porque corresponden a los identificadores internos utilizados por el planificador de EFE.

## 📖 Documentación Interactiva

FastAPI genera documentación automática. Una vez levantada la aplicación, podés acceder a:

- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

---

*Nota: Este proyecto realiza scraping sobre el sitio público de EFE para fines informativos.*

