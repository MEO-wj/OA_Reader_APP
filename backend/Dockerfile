# Build stage
FROM docker.1ms.run/golang:1.21-alpine AS builder

WORKDIR /app

# 安装依赖 - 使用国内镜像源
RUN apk add --no-cache git && \
    echo 'https://mirrors.ustc.edu.cn' > /etc/apk/repositories

# 复制 go mod 文件
COPY go.mod go.sum ./

# 使用国内 Go 代理
RUN go env -w GOPROXY=https://goproxy.cn,direct && \
    go env -w GOSUMDB=off && \
    go mod download

# 复制源代码
COPY . .

# 构建
RUN CGO_ENABLED=0 GOOS=linux go build -o /server ./cmd/server

# Runtime stage
FROM docker.1ms.run/alpine:3.19

WORKDIR /app

# 安装 CA 证书 - 使用国内镜像源
RUN apk add --no-cache ca-certificates tzdata && \
    echo 'https://mirrors.ustc.edu.cn' > /etc/apk/repositories

# 创建非 root 用户
RUN adduser -D -g '' appuser

# 预创建上传目录并授予运行用户写权限
RUN mkdir -p /app/uploads && chown -R appuser:appuser /app/uploads

# 从 builder 复制二进制文件
COPY --from=builder /server .

# 切换到非 root 用户
USER appuser

# 暴露端口
EXPOSE 4420

# 运行
CMD ["./server"]
