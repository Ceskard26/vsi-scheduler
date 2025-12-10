FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias
RUN pip install --default-timeout=300 --no-cache-dir \
    ibm-vpc>=0.20.0 \
    ibm-cloud-sdk-core>=3.16.0

# Copiar script
COPY instance_scheduler.py .

# Hacer ejecutable
RUN chmod +x instance_scheduler.py

ENTRYPOINT ["python", "instance_scheduler.py"]
