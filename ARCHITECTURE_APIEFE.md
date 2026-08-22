# Arquitectura del Proyecto: API-EFE

Este documento proporciona una visión profunda y técnica de las decisiones de arquitectura, diseño e implementación del proyecto API-EFE. Está estructurado para comprender el *porqué* detrás del código, sirviendo como guía para justificar el proyecto en contextos profesionales o entrevistas técnicas.

---

## 1. ¿Qué problema resuelve este proyecto?

El sitio web oficial de EFE (Empresa de los Ferrocarriles del Estado en Chile) no provee una API pública, documentada o de fácil acceso para que los desarrolladores integren los horarios y tarifas de los trenes en aplicaciones de terceros, widgets, o atajos móviles. Los usuarios finales están forzados a navegar por un sitio web tradicional, llenar un formulario y esperar que cargue la página para obtener un itinerario.

Este proyecto resuelve ese problema de accesibilidad e integración. Actúa como un middleware que encapsula la complejidad de interactuar con el sitio web oficial, extrayendo la información mediante **Web Scraping** y exponiéndola a través de una **API REST estandarizada (JSON)** y una **Interfaz visual optimizada (HTML)** de forma rápida y automatizada.

## 2. ¿Quién utilizaría este proyecto?

El proyecto tiene dos usuarios objetivos principales:

- **Desarrolladores (Consumidores de la API):** Ingenieros o hobbistas que necesitan integrar información en tiempo real de trenes chilenos en sus propias aplicaciones móviles, bots de Telegram/Discord, integraciones domóticas, o dashboards de análisis de transporte. Ellos consumen las respuestas estandarizadas en `JSON`.
- **Usuarios Finales:** Pasajeros de trenes, especialmente estudiantes o trabajadores de comunas periféricas (Buin, Paine, Rancagua) que buscan ver el estado de los trenes de forma instantánea mediante la vista HTML renderizada, ideal para usarse como un *Widget* o *Atajo (Shortcut) de iOS/Android*, a un solo toque y visualizando el precio con descuento.

## 3. Objetivo principal del proyecto

El objetivo técnico principal es construir una **capa de abstracción y adaptación** (Adapter) robusta, rápida e independiente de estado, capaz de convertir datos web no estructurados (documento HTML crudo de EFE) en datos estructurados y predecibles (JSON / Objetos de Python), inyectando lógica de valor agregado (como cálculos de tarifas y tiempos relativos).

## 4. Arquitectura elegida

El proyecto sigue una arquitectura de **API REST con una estructura de Capas Lógicas Simplificada** y utiliza los patrones estructurales **Adapter/Proxy**.

* **¿Por qué tiene sentido?**
Al ser un microservicio enfocado en una única tarea, la arquitectura en capas (Routers -> Lógica -> Scraper) permite separar responsabilidades. Si mañana EFE cambia el diseño de su página, solo se debe tocar la capa de *Scraper*, dejando los *Endpoints* y las reglas de negocio intactas. No requiere bases de datos (stateless), por lo que el enfoque monolítico simplificado de FastAPI es la solución de mayor rendimiento y menor fricción de mantenimiento.

## 5. Flujo completo de una petición

Este es el ciclo de vida, paso a paso, desde que el usuario consulta los trenes:

1. **Cliente:** Hace una petición HTTP `GET` a `/itinerarios` con parámetros de query (`origen=1`, `destino=13`).
2. **FastAPI Router:** Intercepta la petición. Utiliza validación nativa (Pydantic) para asegurar que los parámetros ingresados sean correctos.
3. **Endpoint (`itinerarios_json`):** Recibe la petición limpia y llama al orquestador principal de la lógica subyacente (`obtener_todos_los_viajes`).
4. **Lógica de negocio:** Normaliza el texto ingresado, valida que las estaciones existan (con `resolver_id_estacion`) y calcula el formato de fecha correcto usando la zona horaria chilena (`ZoneInfo`).
5. **Sitio Web de EFE (Petición Externa):** La librería `requests` construye la URL específica con los identificadores internos de EFE y descarga el documento HTML del sistema oficial.
6. **Web Scraper (BeautifulSoup):** Carga el HTML en memoria, busca las clases, párrafos y tablas (`<table>`) correspondientes a "Tarifa Alta" y "Tarifa Baja", iterando por las filas (`<tr>`) y celdas (`<td>`).
7. **Procesamiento y Transformación:** Se limpian los datos extraídos (removiendo emojis, espacios y separadores de miles). Se calculan los valores derivados, como la tarifa nacional de estudiante en base a los IDs de las comunas (`calcular_tarifa_estudiante`).
8. **Modelo de Respuesta:** Los datos procesados se agrupan en una lista de diccionarios (arrays/objetos).
9. **Serialización (JSON / HTML):** FastAPI toma estos diccionarios; si el endpoint era el base, lo convierte en una `JSONResponse`. Si era la ruta `/visual`, le inyecta las variables a Jinja2 para que renderice el `TemplateResponse`.
10. **Cliente:** Recibe instantáneamente un JSON limpio o una página web formateada con los próximos trenes.

## 6. Organización del proyecto

- `main.py`: Archivo de entrada centralizado. Aunque contiene múltiples capas lógicas, al ser un microservicio pequeño unifica la ejecución del router, la inicialización de FastAPI, el core scraper y las dependencias. (Punto obvio para refactor a múltiples módulos a futuro).
- `templates/`: Directorio dedicado a la Capa de Presentación (Vista). Contiene archivos HTML (ej. `visual.html`) que esperan ser hidratados con los datos del backend mediante sintaxis Jinja2.
- `requirements.txt`: Archivo de control de versiones y dependencias de Python (Pip).
- `Dockerfile` / `.dockerignore`: Empaquetamiento de la aplicación. Describe las dependencias del sistema operativo y asegura la portabilidad a entornos Cloud Serverless.
- `README.md`: Documentación del desarrollador sobre cómo levantar, consumir y desplegar el servicio.

## 7. Responsabilidad de cada capa

Dentro de `main.py`, la lógica está fragmentada lógicamente en:

- **Capa de Endpoints (Routers/Controladores):**
  - *Qué hace:* Exponer rutas REST (`@app.get`), recibir parámetros HTTP, manejar excepciones HTTP y retornar `JSONResponse` o plantillas renderizadas.
  - *Qué NO hace:* No toma decisiones de lógica de negocio, no calcula tarifas y nunca extrae información de HTML directamente.
- **Capa de Servicios Lógicos (Utils):**
  - *Qué hace:* Alojar algoritmos puros como `calcular_tarifa_estudiante`, el manejo de husos horarios (`ZoneInfo`) y validadores de strings (`normalizar_texto`).
  - *Cómo interactúa:* Es llamada por el Endpoint y el Scraper de manera transversal como utilería.
- **Capa de Scraper (Data Access Layer / DAO Web):**
  - *Qué hace:* Contiene `obtener_todos_los_viajes` y `scrape_itinerarios`. Construye URLs, maneja librerías de red HTTP externas (`requests`), parsea los nodos del DOM y abstrae los errores de conexión a diccionarios puros manejables.
  - *Qué NO hace:* No formatea respuestas al cliente y no le importa si FastAPI está siendo utilizado.
- **Capa de Configuración:**
  - *Qué hace:* Instancia la aplicación principal `app = FastAPI()`, monta los `Jinja2Templates`, define variables de entorno o constantes globales (`DESTINOS`).

## 8. Tecnologías utilizadas

- **Python (3.x):** Lenguaje de programación. Elegido por su inigualable y vasto ecosistema de librerías destinadas a la extracción y manipulación de datos (Scraping/Data Engineering).
- **FastAPI:** Framework web moderno de Python.
  - *Para qué sirve:* Construir las APIs REST.
  - *Por qué fue elegido:* Es asíncrono/ASGI (alto rendimiento), valida tipos de datos automáticamente mediante Pydantic y autogenera documentación técnica con cero esfuerzo extra. Es significativamente más veloz en microservicios que alternativas robustas como Django o Flask.
- **BeautifulSoup4:** Librería de Web Scraping.
  - *Para qué sirve:* Analizar el DOM del HTML descargado y proveer métodos para navegar y buscar etiquetas (`find`, `find_all`).
  - *Por qué fue elegido:* El sitio de EFE renderiza sus datos del lado del servidor (SSR - HTML estático puro). BeautifulSoup es veloz y extremadamente ligero, evitando usar monstruos informáticos como Puppeteer/Selenium (y evadiendo sus altísimos costos de memoria RAM en la nube).
- **Jinja2:** Motor de plantillas (Template Engine) nativo de Python.
  - *Para qué sirve:* Inyectar variables desde Python dentro del código HTML estático.
  - *Por qué fue elegido:* Solución nativa sin complejidad. Evita tener que desplegar un frontend desacoplado (como React/NextJS), abaratando infraestructura al hacer SSR directamente en el API.
- **Docker:** Plataforma de Contenerización.
  - *Para qué sirve:* Aísla la aplicación en una imagen inmutable con su propio mini Sistema Operativo y dependencias.
  - *Por qué fue elegido:* Evita el famoso "En mi máquina sí funciona". Garantiza un despliegue trivial a cualquier orquestador Cloud.
- **Uvicorn:** Servidor ASGI.
  - *Para qué sirve:* Ejecutar código Python asíncrono y enrutar las peticiones TCP/IP a la instancia de FastAPI.
- **Cloud Run (Deployment Target implícito):** Plataforma CaaS Serverless de Google Cloud. Al ser una API "stateless" en contenedor, es el entorno ideal, ya que permite escalar a 0 cuando no hay uso, cobrando literalmente céntimos al mes.
- **Swagger / OpenAPI:** Estandarización de documentación, incluida "gratis" por FastAPI en los endpoints `/docs`, facilitando la lectura técnica de terceros.

## 9. Flujo del Web Scraping

1. **Request de Datos (Red):** Generación dinámica de la URL con parámetros limpios hacia EFE. Ejecución de petición HTTP bloqueante temporalmente con `requests.get()` manejando *Timeouts* por seguridad operativa.
2. **Construcción del DOM (Parseo):** El string crudo HTML es inyectado a la clase base de `BeautifulSoup` utilizando el parser estándar de Python.
3. **Navegación Relativa (Traversal):** Ya que las tablas en sitios gubernamentales/corporativos suelen carecer de `id` claros, el script busca texto hardcodeado en la interfaz (como "Tarifa Baja") y navega al "siguiente hermano en el DOM" que sea de tipo `<table>`.
4. **Limpieza de Nodos y Extracción (ETL):** Se itera sobre las filas (trenes) y columnas (campos de tiempo/precio). Se emplea Python base para hacer limpiezas severas (`replace('🕒', '').strip()`) dejando únicamente el dato primitivo.
5. **Agregación Lógica:** Los datos limpios se insertan en diccionarios. A cada tren se le inserta una clave adicional ("tarifa") para no perder la semántica visual del DOM que parseamos, devolviendo una estructura lista para consumirse.

## 10. Patrones utilizados

- **Adapter (Proxy Pobre):** Este proyecto en su totalidad conforma un Adapter de Sistemas. Convierte una interfaz cerrada diseñada para humanos (GUI HTML del Gobierno), en una interfaz abierta y estandarizada (API REST) para máquinas y desarrolladores.
- **Template View (MVC Views):** Utilizado en el renderizado con Jinja2 para separar la capa de presentación, manteniendo el paradigma Controlador/Endpoint.
- **Factory/Builder Lógico:** Los diccionarios JSON resultantes no se exponen crudos, se ensamblan y unifican utilizando funciones de limpieza para entregar una firma consistente independientemente de si la página cambió formatos internos.

## 11. Decisiones técnicas importantes

- **¿Por qué FastAPI en vez de Flask/Django?**
  - *Problema resuelto:* Velocidad de desarrollo, tipado estricto y documentación de microservicios.
  - *Alternativas:* Flask (menos estricto, requiere dependencias extras para swagger), Django (demasiado pesado (ORM, Admin Panel) para algo sin BD).
  - *Ventaja:* Su velocidad base en ASGI lo empareja en latencia con Node/Go. Pydantic asegura que no fallen parámetros.
  - *Defensa en entrevista:* "Para un componente stateless de microservicio enfocado en Scraping de red, FastAPI brinda modernidad y alto rendimiento I/O (gracias a async), reduciendo el código repetitivo de validaciones manuales que requeriría Flask."

- **¿Por qué BeautifulSoup y no herramientas como Selenium, Puppeteer o Playwright?**
  - *Problema resuelto:* Extraer la tabla de horarios de una página estática del servidor web de EFE.
  - *Alternativas:* Selenium (arranca Chrome completo), Scrapy (framework sobredimensionado).
  - *Ventajas/Defensa en entrevista:* "Las herramientas Headless de navegador requieren muchísima RAM y tiempo de booteo (overhead) por petición, encareciendo enormemente la infraestructura en la Nube. Ya que la tabla de EFE está escrita estáticamente en el HTML y no depende de JavaScript (CSR), BeautifulSoup cumple el objetivo costando 1/100 del tiempo y recursos. Es Ingeniería enfocada a la eficiencia".

- **¿Por qué tener un Endpoint Visual (`HTMLResponse`) en una API Backend?**
  - *Problema resuelto:* Facilitar la vida al usuario para integraciones móviles (Atajos de iOS).
  - *Defensa en entrevista:* "Aunque el paradigma moderno separa Frontend y Backend (React + API), este proyecto necesitaba una vista simple sin costos adicionales de hosting frontend. El uso de SSR con Jinja2 resolvió un dolor de usuario entregando un panel visual elegante inmediatamente desde el backend monolítico."

- **¿Por qué separar Scraping de los Endpoints?**
  - *Ventajas:* Cumplimiento del principio *Separation of Concerns* y alta testabilidad (Test Driven Development).
  - *Defensa en entrevista:* "El scraper no debe saber nada sobre FastAPI o HTTP Responses. Mantener las funciones aisladas permite en el futuro testearlas con librerías como `pytest` de manera unitaria, o portar la lógica core del scraper a un script Lambda de AWS (Serverless functions) puras sin arrastrar el peso del framework web".

- **¿Por qué la lógica de tarifa estudiante se calcula manual vs ser extraída de la web?**
  - *Ventaja:* Demuestra la inyección de la "Lógica de Negocio". Una API no solo debe ser un pasillo de datos crudos, debe curar, calcular métricas y agregar inteligencia de negocio (descuentos específicos en zonas) sobre la Data Original para ofrecer más valor a sus clientes.

- **Falta de Base de Datos / Cache (Limitación y Justificación)**
  - *Desventajas:* Cada petición del cliente lanza una petición a EFE, sumando latencias (petición a petición) y corriendo riesgo de ser baneado por IP.
  - *Defensa en entrevista (Futuro):* "Al ser una versión inicial/MVP, prioricé el Time To Market. La siguiente evolución arquitectónica clara es introducir un patrón de caché asíncrono con **Redis** o bases Documentales (MongoDB/Firestore), implementando un Cron Job o Celery worker que haga web scraping de forma proactiva (ej. cada hora), guarde los horarios en Redis, y el endpoint simplemente devuelva la copia en caché en 20 milisegundos sin latencia ni riesgo de IP Ban".

---

## 12. Preguntas de Entrevista

1. Explicame a nivel de arquitectura, ¿qué propósito cumple exactamente este microservicio en el ciclo de vida del dato?
2. ¿Por qué elegiste la combinación de Python + FastAPI en lugar de Node.js + Express, considerando que Node es altamente asíncrono por defecto?
3. ¿Cuáles fueron las ventajas de utilizar BeautifulSoup frente a alternativas como Selenium o LXML?
4. Si el día de mañana la empresa EFE rediseña su sitio web utilizando React (Client-Side Rendering) y la información de la tabla ya no llega en el HTML fuente, ¿cómo adaptarías este proyecto para resolver el problema?
5. Háblame de la separación de responsabilidades (Separation of Concerns). ¿Dónde pones los límites técnicos entre tu Router, la Lógica de Negocio y el Scraper?
6. ¿Cómo se encarga tu aplicación de evitar fallas (crashes 500) cuando la página de EFE está temporalmente caída o lenta?
7. Explica cómo FastAPI maneja las validaciones de entrada (`Query params`) y cómo eso te ahorra escribir validaciones de seguridad customizadas.
8. En el código usas un diccionario local hardcodeado llamado `DESTINOS`. ¿Cuáles son los riesgos a nivel de arquitectura de acoplar configuraciones estáticas al código base vs en una Base de Datos?
9. ¿Cuál es la diferencia entre devolver JSON vs retornar un `HTMLResponse` renderizado por Jinja2 a nivel de procesamiento en el servidor?
10. Has mencionado el uso de un patrón "Adapter" o "Proxy", ¿en qué partes específicas del código lo ves implementado lógicamente?
11. ¿Qué es Uvicorn y por qué FastAPI no puede ser ejecutado por sí solo en el puerto 80?
12. Hablemos de concurrencia vs paralelismo en Python. Para tareas I/O Bound como el Web Scraping (esperando la respuesta de red de EFE), ¿es preferible usar `asyncio` o multithreading? ¿Por qué?
13. ¿Cuál es el riesgo de que la función `obtener_todos_los_viajes` haga la petición síncrona `requests.get` si varios usuarios consultan tu API en el mismo milisegundo? ¿Cómo lo resolverías en Python asíncrono (`aiohttp`/`httpx`)?
14. Explicame cómo implementaste el cálculo de la tarifa de estudiante. ¿Por qué consideras eso como "Lógica de negocio"?
15. ¿Por qué es crucial el bloque `timeout=10` en tu capa de acceso HTTP (`requests`), y cómo impacta en la resistencia del servidor a ataques DDoS o caídas en cadena (cascading failures)?
16. Estás haciendo scraping en caliente (al momento del HTTP Request del cliente). ¿Cómo mitigarías la alta latencia provocada por esta decisión arquitectónica?
17. ¿Cómo diseñarías una capa de Caché en este sistema? ¿Qué tecnología usarías (ej. Redis o Memcached) y qué política de invalidación de caché emplearías?
18. Hablemos del archivo Dockerfile. ¿Qué beneficios específicos te da contenerizar este proyecto para llevarlo a un pipeline CI/CD en tu empresa?
19. ¿Por qué es importante incluir el archivo `.dockerignore` cuando generas la imagen del proyecto?
20. Imagina que el sistema escala a miles de peticiones. Has decidido desplegarlo en Cloud Run (Google Cloud) u otra plataforma Serverless. ¿Qué consideraciones tendrías sobre el "Cold Start" al tener dependencias en Python?
21. Si quisieras agregar pruebas unitarias (Unit Testing) y mockear (simular) la página web de EFE para testear si tus extracciones con BeautifulSoup funcionan sin pegarle a la red, ¿qué estrategia y librerías usarías (`pytest`, `unittest.mock`)?
22. Según tu entendimiento, ¿qué aspectos legales y éticos (como respetar `robots.txt` o frecuencia de request) hay que tener en cuenta al integrar un scraper continuo sobre un sistema público gubernamental?
23. ¿Cómo usarías herramientas de APM (Application Performance Monitoring) como Datadog o Sentry para monitorizar las posibles "roturas silenciosas" si cambian una clase CSS de la tabla EFE en producción?
24. ¿Qué significa el concepto de Swagger UI y por qué fue conveniente para tu proyecto?
25. Explicame qué rol juega `ZoneInfo` y el manejo de husos horarios (Timezones) en este backend. ¿Por qué no usar simplemente `datetime.now()` localmente?
26. Si agregas a 5 personas al equipo, ¿cómo reestructurarías la estructura de carpetas (actualmente centrada en `main.py`) para evitar conflictos en los merges de Git? (Ej. `app/api`, `app/core`, `app/services`, etc.).
27. Actualmente tu API es 100% pública. ¿Cómo implementarías autenticación mediante API Keys y Rate Limiting para evitar abusos de terceros sobre tu infraestructura?
28. Si los datos cambian, tu endpoint `/itinerarios/visual` muestra el error visualmente. ¿Debería responder con status code 200 o debería arrojar un HTTP error format? Discutamos la experiencia de usuario versus los estándares REST.
29. ¿Qué pasaría si la librería BeautifulSoup arroja un error no previsto (ej. `AttributeError` al llamar a `.text` en un `None`)? ¿Cómo afecta el manejo de excepciones (`try/except`) actual del proyecto al ciclo de vida del router y el response del cliente?
30. Mirando hacia el futuro, si el uso es masivo, ¿cuál sería tu diagrama de arquitectura propuesto con Cloud, Bases de Datos Documentales y Cron Jobs? Defiéndelo.
