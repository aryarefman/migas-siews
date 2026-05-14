FROM python:3.11-slim

WORKDIR /app

# Install system deps for OpenCV and YOLO
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY model/ ./model/
COPY backend/yolo26n.pt ./yolo26n.pt
COPY backend/yolov8n.pt ./yolov8n.pt

ENV MODEL_BASE=/app
ENV PYTHONPATH=/app/backend:/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8001

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8001"]
