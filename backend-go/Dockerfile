# Build stage
FROM docker.1ms.run/golang:1.21-alpine AS builder

WORKDIR /app

# Install dependencies - 使用国内镜像源
RUN apk add --no-cache git && \
    echo 'https://mirrors.ustc.edu.cn' > /etc/apk/repositories

# Copy go mod files
COPY go.mod go.sum ./

# 使用国内 Go 代理
RUN go env -w GOPROXY=https://goproxy.cn,direct && \
    go env -w GOSUMDB=off && \
    go mod download

# Copy .env file
COPY .env .

# Copy source code
COPY . .

# Build
RUN CGO_ENABLED=0 GOOS=linux go build -o /server ./cmd/server

# Runtime stage
FROM docker.1ms.run/alpine:3.19

WORKDIR /app

# Install CA certificates for HTTPS calls - 使用国内镜像源
RUN apk add --no-cache ca-certificates tzdata && \
    echo 'https://mirrors.ustc.edu.cn' > /etc/apk/repositories

# Create non-root user
RUN adduser -D -g '' appuser

# Copy binary from builder
COPY --from=builder /server .

# Copy .env file
COPY --from=builder /app/.env .

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 4420

# Run
CMD ["./server"]
