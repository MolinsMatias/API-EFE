# 1. Usamos Python ligero como base
FROM python:3.9-slim

# 2. Configuraciones básicas para que Python corra bien en la nube
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 3. Creamos una carpeta vacía llamada 'app' dentro del servidor
WORKDIR /app

# 4. Copiamos TU archivo requirements.txt al servidor e instalamos las librerías
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. EL PASO IMPORTANTE:
# Este punto significa "Copia TODO lo que hay en mi carpeta actual al servidor"
# Esto copiará automáticamente tu carpeta 'templates', tu 'main.py' y todo lo demás.
COPY . .

# 6. Comando para encender la app usando la variable de puerto de Google
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}