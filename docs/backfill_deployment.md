# 历史数据回填部署文档

本文档介绍如何使用 OAP 爬虫的历史数据回填功能。

## 概述

回填功能用于渐进式抓取历史 OA 通知数据，主要特点：

- **断点续传**：通过状态文件记录进度，支持中断后继续
- **随机延迟**：模拟真人访问，避免触发反爬机制
- **批量处理**：每次只处理少量日期，分散访问压力
- **状态监控**：提供进度查询和状态报告功能

## 配置参数

在 `crawler/.env` 文件中添加以下配置：

> 注意：如果 `crawler/.env` 文件不存在，请复制 `crawler/.env.example` 创建配置文件：
> ```bash
> cp crawler/.env.example crawler/.env
> # 然后编辑 crawler/.env 填入实际配置
> ```

```bash
# 回填配置
BACKFILL_BATCH_SIZE=2              # 每次爬几天（推荐: 1-3）
BACKFILL_DELAY_MIN=2.0             # 详情页最小延迟(秒)
BACKFILL_DELAY_MAX=5.0             # 详情页最大延迟(秒)
BACKFILL_DAY_DELAY_MIN=60          # 天间最小延迟(秒)
BACKFILL_DAY_DELAY_MAX=180         # 天间最大延迟(秒)
BACKFILL_ENABLE_RANDOM_DELAY=true  # 是否启用随机延迟
```

### 参数说明

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| BACKFILL_BATCH_SIZE | 2 | 每次 cron 触发只爬少量日期 |
| BACKFILL_DELAY_MIN | 2.0 | 每篇文章之间最小延迟（秒） |
| BACKFILL_DELAY_MAX | 5.0 | 每篇文章之间最大延迟（秒） |
| BACKFILL_DAY_DELAY_MIN | 60 | 爬完一天后最小延迟（秒） |
| BACKFILL_DAY_DELAY_MAX | 180 | 爬完一天后最大延迟（秒） |
| BACKFILL_ENABLE_RANDOM_DELAY | true | 是否启用随机延迟 |

## 快速开始

### 1. 初始化回填任务

```bash
cd crawler/

# 使用辅助脚本初始化（推荐）
./backfill_runner.sh --init 2024-01-01 2024-12-31

# 或直接使用 Python
python -m crawler.backfill --init --start-date 2024-01-01 --end-date 2024-12-31
```

### 2. 手动执行一次测试

```bash
# 使用辅助脚本
./backfill_runner.sh

# 或直接使用 Python
python -m crawler.backfill --run
```

### 3. 查看进度状态

```bash
# 使用辅助脚本
./backfill_runner.sh --status

# 或直接使用 Python
python -m crawler.backfill --status
```

输出示例：
```
📊 回填进度状态:
   状态: 进行中
   日期范围: 2024-01-01 至 2024-12-31
   完成进度: 45/365 天 (12.33%)
   已爬取文章: 125 篇
   上次运行: 2025-12-28T03:30:00
```

## 定时任务部署

### 方式一：Cron 定时任务（推荐）

编辑 crontab：

```bash
crontab -e
```

添加以下配置之一：

#### 选项 A：每天凌晨随机时间执行

```bash
# 每天凌晨 2:00-5:00 之间的随机时间执行
0 2 * * * sleep $((RANDOM \% 10800)); cd /path/to/OAP/crawler && ./backfill_runner.sh >> backfill.log 2>&1
```

#### 选项 B：每周执行 5 次（工作日）

```bash
# 周一到周五，每天凌晨 2:00-5:00 之间的随机时间执行
0 2 * * 1-5 sleep $((RANDOM \% 10800)); cd /path/to/OAP/crawler && ./backfill_runner.sh >> backfill.log 2>&1
```

#### 选项 C：每天多次执行（加速回填）

```bash
# 凌晨 2 点和早上 6 点各执行一次
0 2,6 * * * sleep $((RANDOM \% 1800)); cd /path/to/OAP/crawler && ./backfill_runner.sh >> backfill.log 2>&1
```

### 方式二：Systemd Timer

创建服务文件 `/etc/systemd/system/oap-backfill.service`：

```ini
[Unit]
Description=OAP Backfill Crawler
After=network.target postgresql.service

[Service]
Type=oneshot
User=oap
WorkingDirectory=/path/to/OAP/crawler
ExecStart=/path/to/OAP/crawler/.venv/bin/python -m crawler.backfill --run

# 环境变量（如果 .env 文件不在默认位置）
EnvironmentFile=/path/to/OAP/crawler/.env

# 日志
StandardOutput=append:/path/to/OAP/crawler/backfill.log
StandardError=append:/path/to/OAP/crawler/backfill.log
```

创建定时器文件 `/etc/systemd/system/oap-backfill.timer`：

```ini
[Unit]
Description=OAP Backfill Timer
Requires=oap-backfill.service

[Timer]
# 每天凌晨 2 点执行
OnCalendar=*-*-* 02:00:00
# 随机延迟 0-3 小时
RandomizedDelaySec=10800
# 如果错过执行时间，立即执行
Persistent=true

[Install]
WantedBy=timers.target
```

启用定时器：

```bash
# 重新加载 systemd 配置
sudo systemctl daemon-reload

# 启用并启动定时器
sudo systemctl enable --now oap-backfill.timer

# 查看定时器状态
sudo systemctl list-timers
sudo systemctl status oap-backfill.timer

# 手动触发一次执行
sudo systemctl start oap-backfill.service
```

## 时间估算

假设：
- 每天平均 3-5 篇文章
- 每篇文章延迟平均 3.5 秒
- 单日处理时间：约 15-20 秒
- 天间延迟：1-3 分钟

| 回填范围 | 总天数 | 单批2天 | 所需周数（每周5次） | 所需周数（每天1次） |
|----------|--------|---------|---------------------|---------------------|
| 3 个月   | ~90    | 45 批   | ~9 周               | ~45 天              |
| 6 个月   | ~180   | 90 批   | ~18 周              | ~90 天              |
| 1 年     | ~365   | 183 批  | ~37 周              | ~183 天             |

### 加速方案

如果需要加快回填速度，可以调整以下参数：

1. **增加批处理大小**（风险：更容易触发反爬）
   ```bash
   BACKFILL_BATCH_SIZE=5  # 从 2 增加到 5
   ```

2. **减少天间延迟**（风险：更容易触发反爬）
   ```bash
   BACKFILL_DAY_DELAY_MIN=30
   BACKFILL_DAY_DELAY_MAX=60
   ```

3. **增加执行频率**
   - 从每周 5 次改为每天 1 次
   - 或每天执行 2-3 次

## 高级操作

### 强制执行（忽略今日执行检查）

```bash
./backfill_runner.sh --force
# 或
python -m crawler.backfill --run --force
```

### 重置回填状态

```bash
python -m crawler.backfill --reset
```

**警告**：此操作会删除所有进度记录，需要重新初始化。

### 查看状态文件

状态文件位于 `crawler/backfill_state.json`：

```json
{
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "completed_dates": ["2024-12-30", "2024-12-29", ...],
  "failed_dates": ["2024-06-15"],
  "last_run": "2025-12-28T03:30:00",
  "total_articles": 125
}
```

## 监控和日志

### 日志位置

- Cron 日志：`/path/to/OAP/crawler/backfill.log`
- Systemd 日志：`journalctl -u oap-backfill.service`

### 日志示例

```
[2025-12-28 02:15:32] INFO: 开始执行回填任务...
[2025-12-28 02:15:32] INFO: 激活虚拟环境: .venv
[2025-12-28 02:15:33] INFO: 执行回填: python -m crawler.backfill --run
📋 本批待处理日期: 2024-12-29, 2024-12-28
   进度: 8.5%

[1/2] 处理日期: 2024-12-29
开始增量抓取 2024-12-29 的OA通知
✅ 数据库连接成功
...
✅ 向量生成和存储完成
⏳ 随机延迟 125.3 秒...

[2/2] 处理日期: 2024-12-28
...
✅ 本批处理完成
   当前进度: 9.04%
   已完成: 33/365 天
[2025-12-28 02:25:45] INFO: 回填任务执行完成
```

## 故障排除

### 问题：状态文件损坏

```bash
# 重置状态并重新初始化
python -m crawler.backfill --reset
python -m crawler.backfill --init --start-date 2024-01-01 --end-date 2024-12-31
```

### 问题：某些日期失败

检查失败的日期列表：

```bash
python -m crawler.backfill --status
```

失败的日期会优先在下一次执行时处理。如果持续失败，可能需要：
1. 检查网络连接
2. 检查 OA 系统是否正常
3. 手动检查该日期的数据是否存在

### 问题：触发反爬

如果出现 403、404 或连接超时：
1. 增加延迟时间
2. 减少批处理大小
3. 减少执行频率
4. 暂停几天后再继续

## 配置示例文件

将以下内容添加到 `crawler/.env.example`：

```bash
# ========================================
# 回填配置 (Backfill Configuration)
# ========================================

# 每次爬几天 (推荐: 1-3)
BACKFILL_BATCH_SIZE=2

# 详情页最小延迟(秒) (推荐: 2-5)
BACKFILL_DELAY_MIN=2.0

# 详情页最大延迟(秒) (推荐: 5-10)
BACKFILL_DELAY_MAX=5.0

# 天间最小延迟(秒) (推荐: 60-180)
BACKFILL_DAY_DELAY_MIN=60

# 天间最大延迟(秒) (推荐: 180-300)
BACKFILL_DAY_DELAY_MAX=180

# 是否启用随机延迟 (推荐: true)
BACKFILL_ENABLE_RANDOM_DELAY=true
```

## 安全建议

1. **不要在高峰期执行**：建议在凌晨 2:00-6:00 执行
2. **使用随机延迟**：避免固定时间间隔
3. **监控失败率**：如果失败率过高，暂停任务
4. **备份数据库**：在开始回填前备份数据库
