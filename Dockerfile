FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
ARG PUBLIC_BASE_PATH=/
ENV PUBLIC_BASE_PATH=${PUBLIC_BASE_PATH}
RUN npm run build

FROM python:3.11-slim-bookworm
RUN groupadd --gid 10001 provider && useradd --uid 10001 --gid 10001 --create-home provider
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && pip check
COPY src ./src
COPY --from=frontend /frontend/dist ./frontend/dist
ENV PYTHONPATH=/app/src PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 BEDROCK_MODEL_ID=""
USER provider
EXPOSE 8510
# Probe the web process without depending on a populated graph or making AI requests.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8510/', timeout=3).close()"]
CMD ["python","-m","uvicorn","drift_communities.api:app","--host","0.0.0.0","--port","8510"]
