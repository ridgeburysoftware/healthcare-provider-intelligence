FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
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
CMD ["python","-m","uvicorn","drift_communities.api:app","--host","0.0.0.0","--port","8510"]
