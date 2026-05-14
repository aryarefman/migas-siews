FROM python:3.11-slim

WORKDIR /app

# Install system deps for OpenCV, YOLO, and dlib (face_recognition)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    curl \
    cmake g++ make libopenblas-dev liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir dlib==19.24.6 && \
    pip install --no-cache-dir face_recognition==1.3.0 && \
    pip install --no-cache-dir -r requirements.txt

# Remove build tools after pip install to keep image smaller
RUN apt-get purge -y cmake g++ make && apt-get autoremove -y || true

COPY backend/ ./backend/
COPY model/ ./model/
COPY backend/yolo26n.pt ./yolo26n.pt
COPY backend/yolov8n.pt ./yolov8n.pt

ENV MODEL_BASE=/app
ENV PYTHONPATH=/app/backend:/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8001

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8001"]
