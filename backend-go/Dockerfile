# ==============================================================================
# SIEWS+ 5.0 Go Backend Dockerfile
# Multi-stage build for optimized production image
# ==============================================================================

# Stage 1: Builder
FROM golang:1.23-alpine AS builder

# Install build dependencies including gocv requirements
RUN apk add --no-cache \
    gcc \
    musl-dev \
    linux-headers \
    ca-certificates \
    git \
    make \
    cmake \
    pkgconfig \
    libglib-dev \
    go

# Install OpenCV build dependencies for gocv
RUN apk add --no-cache \
    libopencv-dev \
    openblas-dev \
    lapack-dev \
    arpack-dev

WORKDIR /app

# Copy go mod files
COPY go.mod go.sum* ./

# Download dependencies
RUN go mod download

# Copy source code
COPY . .

# Build the application
RUN CGO_ENABLED=1 GOOS=linux go build \
    -ldflags="-w -s" \
    -tags 'containers' \
    -o /app/siews-backend \
    ./cmd/server

# ==============================================================================
# Stage 2: Production Runtime
# ==============================================================================

FROM alpine:3.19 AS production

# Install runtime dependencies
RUN apk add --no-cache \
    ca-certificates \
    libglib \
    libopencv \
    libstdc++ \
    libgcc \
    libc6-compat \
    openblas \
    lapack \
    arpack

# Create non-root user
RUN addgroup -S siews && adduser -S siews -G siews

WORKDIR /app

# Copy binary from builder
COPY --from=builder /app/siews-backend .

# Create directories for static files
RUN mkdir -p /app/static/snapshots /app/static/uploads && \
    chown -R siews:siews /app

USER siews

# Environment variables
ENV PORT=8000
ENV STATIC_DIR=/app/static
ENV MODELS_DIR=/app/models
ENV DATABASE_URL=sqlite:///app/siews.db
ENV GIN_MODE=release

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:8000/health || exit 1

# Run the application
CMD ["./siews-backend"]

# ==============================================================================
# Stage 3: Development
# ==============================================================================

FROM golang:1.23-alpine AS development

# Install dependencies
RUN apk add --no-cache \
    gcc \
    musl-dev \
    linux-headers \
    ca-certificates \
    git \
    make \
    cmake \
    libglib-dev \
    opencv-dev

WORKDIR /app

# Copy go mod files
COPY go.mod go.sum* ./

# Download dependencies
RUN go mod download

# Copy source code
COPY . .

# Run development server with hot reload (requires air)
# Install air for hot reload: go install github.com/cosmtrek/air@latest
CMD ["go", "run", "./cmd/server"]
