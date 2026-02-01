FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir .

COPY static/ static/
COPY tests/ tests/

ENV AIRLOCK_DATA_DIR=/data
VOLUME /data

EXPOSE 9090

CMD ["python", "-m", "airlock"]
