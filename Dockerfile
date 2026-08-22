# 1. Base ligera de Python
FROM python:3.10-slim

# 2. Configuraciones de entorno para la nube
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 3. Directorio de trabajo en el contenedor
WORKDIR /app

# 4. Instalación de dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copiar el código fuente y plantillas
COPY . .

# 6. Comando de ejecución con soporte dinámico para el puerto de Cloud Run ($PORT)
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]