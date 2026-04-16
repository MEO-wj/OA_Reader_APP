# Build stage
ARG BUILDER_IMAGE=docker.1ms.run/golang:1.21-alpine
ARG RUNTIME_IMAGE=docker.1ms.run/alpine:3.19
FROM ${BUILDER_IMAGE} AS builder

WORKDIR /app

# 安装依赖 - 使用国内镜像源
RUN set -eux; \
    printf '%s\n' \
        'https://mirrors.ustc.edu.cn/alpine/v3.19/main' \
        'https://mirrors.ustc.edu.cn/alpine/v3.19/community' \
        > /etc/apk/repositories; \
    if ! apk add --no-cache git; then \
        printf '%s\n' \
            'https://dl-cdn.alpinelinux.org/alpine/v3.19/main' \
            'https://dl-cdn.alpinelinux.org/alpine/v3.19/community' \
            > /etc/apk/repositories; \
        apk add --no-cache git; \
    fi

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
ARG RUNTIME_IMAGE
FROM ${RUNTIME_IMAGE}

WORKDIR /app

# 安装 CA 证书 - 使用国内镜像源
RUN set -eux; \
    printf '%s\n' \
        'https://mirrors.ustc.edu.cn/alpine/v3.19/main' \
        'https://mirrors.ustc.edu.cn/alpine/v3.19/community' \
        > /etc/apk/repositories; \
    if ! apk add --no-cache ca-certificates tzdata; then \
        printf '%s\n' \
            'https://dl-cdn.alpinelinux.org/alpine/v3.19/main' \
            'https://dl-cdn.alpinelinux.org/alpine/v3.19/community' \
            > /etc/apk/repositories; \
        apk add --no-cache ca-certificates tzdata; \
    fi

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
