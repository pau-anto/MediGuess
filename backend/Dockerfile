# Image de l'API MediGuess pour Azure Container Apps.
# Image Python officielle via le miroir AWS (Docker Hub coupait les téléchargements).
# À construire depuis la RACINE du repo (le code importe backend.src.*) :
#   docker build --platform linux/amd64 -f backend/Dockerfile -t mediguess-api .
FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/__init__.py backend/__init__.py
COPY backend/src backend/src
COPY backend/data backend/data

# Utilisateur non-root
RUN useradd --create-home app
USER app

EXPOSE 8080
CMD ["uvicorn", "backend.src.api:app", "--host", "0.0.0.0", "--port", "8080"]
