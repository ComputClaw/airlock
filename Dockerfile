# Stage 1: Build Svelte frontend
FROM node:22-slim AS frontend

WORKDIR /app/ui
COPY ui/package.json ui/package-lock.json* ./
RUN npm ci
COPY ui/ .
RUN npm run build

# Stage 2: Python backend
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir .

# Copy built frontend from Stage 1
COPY --from=frontend /app/ui/dist/ ui/dist/

COPY tests/ tests/

ENV AIRLOCK_DATA_DIR=/data
VOLUME /data

EXPOSE 9090

CMD ["python", "-m", "airlock"]
