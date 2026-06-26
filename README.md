# API-EFE

API-EFE es una aplicación desarrollada con **FastAPI** que permite consultar los itinerarios, horarios y tarifas de los trenes de EFE (Empresa de los Ferrocarriles del Estado) en Chile. Utiliza técnicas de *web scraping* para obtener la información actualizada directamente desde el sitio web oficial de EFE.

## 🚀 Características

- **Consulta de Itinerarios:** Busca horarios de trenes entre distintas estaciones habilitadas (Estación Central, San Bernardo, Rancagua, Buin Zoo, etc.).
- **Búsqueda por Fecha:** Permite visualizar los horarios de trenes para el día actual o para una fecha futura.
- **Interfaz Visual:** Proporciona una interfaz web amigable renderizada con plantillas de Jinja2.
- **Cálculo de Tarifas de Estudiante:** Calcula automáticamente la tarifa con descuento para estudiantes dependiendo del tramo seleccionado.
- **Estado de Trenes (Pasados/Próximos):** Diferencia visualmente los trenes que ya pasaron de los que están próximos a salir según la hora local de Chile.

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
   docker run -d -p 8000:8000 api-efe
   ```

## 📍 Endpoints Principales

- `GET /itinerarios/visual`
  - **Descripción:** Retorna una página HTML con los horarios de los trenes consultados.
  - **Parámetros Query:**
    - `origen` (str, obligatorio): Nombre o ID de la estación de origen (ej. "Estación Central").
    - `destino` (str, obligatorio): Nombre o ID de la estación de destino (ej. "Rancagua").
    - `fecha` (str, opcional): Fecha de la consulta en formato `YYYY-MM-DD`. Si no se provee, asume la fecha de hoy en Chile.

## 🚉 Estaciones Soportadas

Actualmente, el sistema mapea internamente las siguientes estaciones (IDs comunes):
- Estación Central
- San Bernardo
- Buin Zoo
- Buin
- Linderos
- Paine
- Hospital
- San Francisco
- Graneros
- Rancagua

---

*Nota: Este proyecto realiza scraping sobre el sitio público de EFE para fines informativos.*
