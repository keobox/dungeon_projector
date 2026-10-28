FROM docker.io/library/python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    IMAGE_STORAGE_PATH=/data/images \
    IMAGE_BASE_URI=/images/ \
    CAMPAIGN_PATH=/data/campaign.json

# Exported from uv.lock; no development packages or frontend build at runtime.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY static ./static
RUN mkdir -p /data/images

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
