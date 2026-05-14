FROM python:3.11-slim

WORKDIR /app

# Install system deps for OpenCV and YOLO
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY inference-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY inference-service/ ./inference-service/
COPY model/ ./model/
COPY inference-service/yolo26n.pt ./yolo26n.pt
COPY yolov8n.pt ./yolov8n.pt

ENV MODEL_BASE=/app
ENV GO_BACKEND_URL=http://backend:8001
ENV PYTHONUNBUFFERED=1

EXPOSE 8001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--app-dir", "/app/inference-service"]
