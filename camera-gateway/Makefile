.PHONY: proto build clean run-gateway run-rtsp run-rtmp test

# Generate Go code from protobuf
proto:
	@echo "Generating protobuf code..."
	protoc --go_out=. --go-grpc_out=. proto/camera.proto
	@echo "Protobuf code generated"

# Build all services
build:
	@echo "Building services..."
	go build -o bin/gateway cmd/gateway/main.go
	go build -o bin/rtsp-ingest cmd/rtsp-ingest/main.go
	go build -o bin/rtmp-ingest cmd/rtmp-ingest/main.go
	@echo "Build complete"

# Clean build artifacts
clean:
	@echo "Cleaning..."
	rm -rf bin/
	@echo "Clean complete"

# Run gateway service
run-gateway:
	@echo "Starting gateway service..."
	go run cmd/gateway/main.go

# Run RTSP ingest service
run-rtsp:
	@echo "Starting RTSP ingest service..."
	go run cmd/rtsp-ingest/main.go

# Run RTMP ingest service
run-rtmp:
	@echo "Starting RTMP ingest service..."
	go run cmd/rtmp-ingest/main.go

# Run tests
test:
	@echo "Running tests..."
	go test ./...

# Install dependencies
deps:
	@echo "Installing dependencies..."
	go mod download
	go mod tidy
	@echo "Dependencies installed"

# Format code
fmt:
	@echo "Formatting code..."
	go fmt ./...

# Run linter
lint:
	@echo "Running linter..."
	golangci-lint run

# Build Docker images
docker-build:
	@echo "Building Docker images..."
	docker build -t camera-gateway:latest .

# Run with Docker Compose
docker-up:
	@echo "Starting services with Docker Compose..."
	docker-compose up -d

# Stop Docker Compose
docker-down:
	@echo "Stopping Docker Compose..."
	docker-compose down
