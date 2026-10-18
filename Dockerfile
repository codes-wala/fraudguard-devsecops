# FraudGuard - production image
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# install dependencies first so Docker can cache this layer
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# copy only what the app needs (see .dockerignore)
COPY fraud_detector ./fraud_detector
COPY templates ./templates
COPY static ./static

# run as a non-root user
RUN useradd --system --uid 10001 --no-create-home appuser \
    && chown -R appuser /app
USER 10001

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/api/health', timeout=3).status == 200 else 1)"]

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "2", "--timeout", "30", "--access-logfile", "-", "fraud_detector.api:create_app()"]
