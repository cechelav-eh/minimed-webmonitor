FROM python:3.9-slim

WORKDIR /app

# Instalar dependencias necesarias
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir pip==23.3.1

# Copiar requirements.txt primero para aprovechar la caché de Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Exponer el puerto que usa la aplicación
EXPOSE 5001
EXPOSE 8081

# El comando se especificará en docker-compose.yml
CMD ["python", "minimed-mon-web.py"]
