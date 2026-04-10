# 部署指南

本文档详细说明OAP项目的部署流程。

## 目录

- [后端部署](#后端部署)
- [爬虫部署](#爬虫部署)
- [客户端构建](#客户端构建)
- [生产环境配置](#生产环境配置)
- [监控与维护](#监控与维护)

## 后端部署

### Docker部署（推荐）

项目包含Docker配置，支持一键部署。

#### 前置要求

- Docker 20.10+
- Docker Compose 2.0+

#### 部署步骤

1. **准备环境变量文件**

```bash
cd backend
cp env.example .env
# 编辑.env文件，配置生产环境参数
vim .env
```

2. **构建并启动服务**

```bash
# 构建镜像
docker-compose build

# 启动服务（后台运行）
docker-compose up -d

# 查看日志
docker-compose logs -f
```

3. **初始化数据库**

```bash
# 进入容器
docker-compose exec backend bash

# 运行数据库迁移
python -c "from backend.db import init_db; init_db()"

# 创建管理员用户
python scripts/create_admin_user.py
```

4. **验证部署**

```bash
# 健康检查
curl http://localhost:4420/api/health

# 应返回：
# {"status":"ok","service":"oa-api","version":"0.1.0"}
```

#### Docker Compose配置说明

`backend/docker-compose.yml`包含以下服务：

- **backend**: Flask API服务
- **postgres**: PostgreSQL数据库
- **redis**: Redis缓存服务

#### 常用命令

```bash
# 停止服务
docker-compose down

# 停止并删除数据卷
docker-compose down -v

# 重启服务
docker-compose restart

# 查看服务状态
docker-compose ps

# 查看资源使用
docker stats
```

### 传统部署

#### 前置要求

- Python 3.10+
- PostgreSQL 15+
- Redis 7+
- Nginx（可选，用于反向代理）

#### 部署步骤

1. **安装系统依赖**

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3.10 python3-pip postgresql redis-server nginx

# CentOS/RHEL
sudo yum install python3.10 python3-pip postgresql-server redis nginx
```

2. **配置PostgreSQL**

```bash
# 创建数据库
sudo -u postgres psql
CREATE DATABASE oap;
CREATE USER oap_user WITH PASSWORD 'strong_password';
GRANT ALL PRIVILEGES ON DATABASE oap TO oap_user;
\q

# 安装pgvector扩展
sudo -u postgres psql -d oap
CREATE EXTENSION IF NOT EXISTS vector;
\q
```

3. **配置Redis**

```bash
# 编辑Redis配置
sudo vim /etc/redis/redis.conf

# 设置密码（可选）
requirepass your_redis_password

# 重启Redis
sudo systemctl restart redis
sudo systemctl enable redis
```

4. **部署后端代码**

```bash
# 克隆代码
git clone <repository-url>
cd OAP/backend

# 创建虚拟环境
python3.10 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp env.example .env
vim .env
```

5. **配置Systemd服务**

创建服务文件 `/etc/systemd/system/oap-backend.service`：

```ini
[Unit]
Description=OAP Backend API
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/OAP/backend
Environment="PATH=/path/to/OAP/backend/venv/bin"
ExecStart=/path/to/OAP/backend/venv/bin/python app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable oap-backend
sudo systemctl start oap-backend
sudo systemctl status oap-backend
```

6. **配置Nginx反向代理**

创建配置文件 `/etc/nginx/sites-available/oap`：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location /api/ {
        proxy_pass http://127.0.0.1:4420/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

启用配置：

```bash
sudo ln -s /etc/nginx/sites-available/oap /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

7. **配置SSL（推荐）**

使用Let's Encrypt免费SSL证书：

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

## 爬虫部署

### 使用Cron定时任务

1. **创建定时任务脚本**

创建 `/usr/local/bin/oap-crawler.sh`：

```bash
#!/bin/bash
cd /path/to/OAP/crawler
source venv/bin/activate
python main.py >> /var/log/oap-crawler.log 2>&1
```

设置执行权限：

```bash
chmod +x /usr/local/bin/oap-crawler.sh
```

2. **配置Cron**

编辑crontab：

```bash
crontab -e
```

添加定时任务（每天8:00和14:00运行）：

```cron
0 8,14 * * * /usr/local/bin/oap-crawler.sh
```

3. **查看日志**

```bash
tail -f /var/log/oap-crawler.log
```

### 使用Systemd定时器

1. **创建服务文件**

创建 `/etc/systemd/system/oap-crawler.service`：

```ini
[Unit]
Description=OAP Crawler Service

[Service]
Type=oneshot
User=www-data
WorkingDirectory=/path/to/OAP/crawler
Environment="PATH=/path/to/OAP/crawler/venv/bin"
ExecStart=/path/to/OAP/crawler/venv/bin/python main.py
```

2. **创建定时器文件**

创建 `/etc/systemd/system/oap-crawler.timer`：

```ini
[Unit]
Description=Run OAP Crawler daily

[Timer]
OnCalendar=*-*-* 08:00,14:00
Persistent=true

[Install]
WantedBy=timers.target
```

3. **启用定时器**

```bash
sudo systemctl daemon-reload
sudo systemctl enable oap-crawler.timer
sudo systemctl start oap-crawler.timer
sudo systemctl status oap-crawler.timer
```

## 客户端构建

### 使用EAS Build（推荐）

Expo Application Services (EAS) 提供云端构建服务。

#### 前置要求

- Expo账号
- EAS CLI

```bash
npm install -g eas-cli
eas login
```

#### 配置EAS

1. **初始化EAS配置**

```bash
cd OAP-app
eas build:configure
```

2. **配置环境变量**

在EAS Dashboard或使用命令行配置：

```bash
eas secret:create EXPO_PUBLIC_API_BASE_URL
# 输入生产环境API地址
```

3. **构建iOS应用**

```bash
# 开发构建
eas build --profile development --platform ios

# 预览构建
eas build --profile preview --platform ios

# 生产构建
eas build --profile production --platform ios
```

4. **构建Android应用**

```bash
# 开发构建
eas build --profile development --platform android

# 预览构建
eas build --profile preview --platform android

# 生产构建
eas build --profile production --platform android
```

#### 提交到应用商店

**iOS App Store:**

1. 在EAS Dashboard下载IPA文件
2. 使用Xcode或Application Loader上传到App Store Connect
3. 填写应用信息和截图
4. 提交审核

**Google Play Store:**

1. 在EAS Dashboard下载AAB或APK文件
2. 上传到Google Play Console
3. 填写应用信息和截图
4. 提交审核

### 本地构建

#### iOS构建

```bash
cd OAP-app

# 安装依赖
npm install

# 启动开发服务器
npm start

# 按i键在模拟器中运行
# 或按Shift+i在真机上运行
```

#### Android构建

```bash
cd OAP-app

# 安装依赖
npm install

# 启动开发服务器
npm start

# 按a键在模拟器中运行
# 或按Shift+a在真机上运行
```

#### Web构建

```bash
cd OAP-app

# 安装依赖
npm install

# 构建生产版本
npm run web

# 构建静态文件
npx expo export:web
```

## 生产环境配置

### 数据库优化

1. **连接池配置**

在`backend/.env`中添加：

```bash
# 数据库连接池大小
DB_POOL_SIZE=20

# 最大溢出连接数
DB_MAX_OVERFLOW=10

# 连接超时时间（秒）
DB_POOL_TIMEOUT=30
```

2. **索引优化**

```sql
-- 为常用查询添加索引
CREATE INDEX idx_articles_published_on ON articles(published_on);
CREATE INDEX idx_articles_created_at ON articles(created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_vectors_article ON vectors(article_id);
CREATE INDEX IF NOT EXISTS idx_vectors_embedding_hnsw ON vectors USING hnsw (embedding vector_cosine_ops);
```

3. **定期维护**

```bash
# 定期清理过期数据
psql -d oap -c "DELETE FROM articles WHERE published_on < NOW() - INTERVAL '2 years';"

# 重建索引
psql -d oap -c "REINDEX DATABASE oap;"
```

### Redis优化

1. **内存配置**

编辑`/etc/redis/redis.conf`：

```conf
# 最大内存限制
maxmemory 2gb

# 内存淘汰策略
maxmemory-policy allkeys-lru
```

2. **持久化配置**

```conf
# RDB快照
save 900 1
save 300 10
save 60 10000

# AOF持久化
appendonly yes
appendfsync everysec
```

### 安全加固

1. **防火墙配置**

```bash
# 只允许必要端口
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

2. **定期更新**

```bash
# 系统更新
sudo apt update && sudo apt upgrade -y

# 依赖更新
cd /path/to/OAP/backend
pip install --upgrade -r requirements.txt
```

3. **备份策略**

```bash
# 数据库备份脚本
#!/bin/bash
BACKUP_DIR="/backups/postgres"
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump -U oap_user oap > $BACKUP_DIR/oap_$DATE.sql
gzip $BACKUP_DIR/oap_$DATE.sql

# 保留最近30天的备份
find $BACKUP_DIR -name "oap_*.sql.gz" -mtime +30 -delete
```

## 监控与维护

### 日志管理

1. **配置日志轮转**

创建 `/etc/logrotate.d/oap`：

```
/var/log/oap/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0640 www-data www-data
}
```

2. **集中式日志**

考虑使用ELK Stack或Loki进行日志收集和分析。

### 性能监控

1. **应用监控**

使用Prometheus + Grafana监控应用性能：

```python
# 在backend/app.py中添加Prometheus端点
from prometheus_flask_exporter import PrometheusMetrics

prometheus_metrics = PrometheusMetrics(app)
```

2. **数据库监控**

监控PostgreSQL性能指标：

```sql
-- 查看慢查询
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
```

3. **Redis监控**

使用Redis命令监控：

```bash
# 查看内存使用
redis-cli INFO memory

# 查看连接数
redis-cli INFO clients

# 查看命中率
redis-cli INFO stats | grep keyspace
```

### 告警配置

配置告警规则，在出现问题时及时通知：

- API响应时间超过阈值
- 数据库连接失败
- Redis连接失败
- 磁盘空间不足
- 错误日志激增

## 故障排查

### 常见问题

1. **服务无法启动**

```bash
# 查看服务状态
sudo systemctl status oap-backend

# 查看详细日志
sudo journalctl -u oap-backend -n 100
```

2. **数据库连接失败**

```bash
# 测试数据库连接
psql -h localhost -U oap_user -d oap

# 检查PostgreSQL状态
sudo systemctl status postgresql
```

3. **Redis连接失败**

```bash
# 测试Redis连接
redis-cli ping

# 检查Redis状态
sudo systemctl status redis
```

### 回滚策略

1. **代码回滚**

```bash
# 回滚到上一个版本
git revert HEAD
git push
```

2. **数据库回滚**

```bash
# 从备份恢复
gunzip < /backups/postgres/oap_20240101_120000.sql.gz | psql -U oap_user -d oap
```

3. **快速回滚**

使用Docker快速回滚：

```bash
# 停止当前服务
docker-compose down

# 切换到上一个镜像标签
docker-compose pull backend:v1.0.1

# 启动服务
docker-compose up -d
```

## 扩展阅读

- [EAS Build文档](https://docs.expo.dev/build/introduction/)
- [Docker最佳实践](https://docs.docker.com/develop/dev-best-practices/)
- [PostgreSQL性能优化](https://wiki.postgresql.org/wiki/Performance_Optimization)
- [Redis最佳实践](https://redis.io/topics/admin)