FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

WORKDIR /app

# Install Python 3.11 + system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3.11-venv python3-pip python3.11-dev \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    curl cmake g++ make libopenblas-dev liblapack-dev \
    ffmpeg \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3 \
    && ln -sf /usr/bin/python3.11 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir dlib==19.24.6 && \
    pip install --no-cache-dir face_recognition==1.3.0 && \
    pip install --no-cache-dir -r requirements.txt

# Remove build tools
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
