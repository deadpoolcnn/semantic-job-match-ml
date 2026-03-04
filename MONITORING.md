# Monitoring with Prometheus + Grafana

本项目已集成 Prometheus + Grafana 监控系统，用于实时追踪 API 性能指标。

## 🚀 快速开始

### 启动完整监控栈

```bash
docker compose up -d
```

这将启动以下服务：
- **Redis** (6379) - 任务队列
- **API** (8000) - FastAPI 应用
- **Worker** - Celery 后台任务
- **Prometheus** (9090) - 指标采集
- **Grafana** (3000) - 可视化仪表盘

### 访问界面

#### Grafana 仪表盘
```
http://localhost:3000
```

默认登录凭证：
- 用户名: `admin`
- 密码: `admin` (首次登录会要求修改)

#### Prometheus 查询界面
```
http://localhost:9090
```

#### API Metrics 端点
```
http://localhost:8000/metrics
```

## 📊 可用指标

### HTTP 请求指标

- `http_requests_total` - 请求总数（按状态码、方法、路径分组）
- `http_request_duration_seconds` - 请求耗时分布（histogram）
- `http_requests_inprogress` - 当前正在处理的请求数

### 系统指标

- `process_cpu_seconds_total` - CPU 使用时间
- `process_resident_memory_bytes` - 内存占用
- `process_open_fds` - 打开的文件描述符数量

## 🎯 常用 Prometheus 查询

### 请求速率（每秒）
```promql
rate(http_requests_total{job="semantic-job-match-api"}[1m])
```

### P95 响应时间
```promql
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{job="semantic-job-match-api"}[5m]))
```

### 错误率（5xx）
```promql
sum(rate(http_requests_total{status=~"5.."}[1m])) / sum(rate(http_requests_total[1m]))
```

### 最活跃的端点
```promql
topk(10, sum by (handler) (rate(http_requests_total[5m])))
```

## 📈 Grafana 仪表盘

系统自动配置了以下仪表盘：

### API Metrics Dashboard
包含：
- 请求速率 (RPS)
- 响应时间分位数 (P50, P95, P99)
- HTTP 状态码分布
- 活跃请求数
- Top 10 端点统计

## 🔧 配置

### 自定义 Grafana 用户名密码

在 `.env` 文件中设置：
```bash
GRAFANA_ADMIN_USER=your_username
GRAFANA_ADMIN_PASSWORD=your_secure_password
GRAFANA_ROOT_URL=https://grafana.yourdomain.com
```

### 修改 Prometheus 采集间隔

编辑 `config/prometheus.yml`:
```yaml
global:
  scrape_interval: 15s  # 改为你想要的间隔
```

### 数据保留时间

默认保留 30 天。修改 `docker-compose.yml`:
```yaml
prometheus:
  command:
    - '--storage.tsdb.retention.time=90d'  # 改为 90 天
```

## 📝 添加自定义指标

在你的 FastAPI 代码中使用 `prometheus_client`:

```python
from prometheus_client import Counter, Histogram

# 计数器
api_calls = Counter('my_api_calls', 'Description', ['endpoint'])
api_calls.labels(endpoint='/match').inc()

# 直方图
response_time = Histogram('my_response_time', 'Description')
with response_time.time():
    # 你的代码
    pass
```

## 🔍 故障排查

### Grafana 显示 "No Data"

1. 检查 Prometheus 是否正常运行：
   ```bash
   curl http://localhost:9090/-/healthy
   ```

2. 检查 Prometheus 是否能采集到 API 指标：
   ```bash
   curl http://localhost:9090/api/v1/targets
   ```

3. 确认 API 的 `/metrics` 端点正常：
   ```bash
   curl http://localhost:8000/metrics
   ```

### Prometheus target 显示 "down"

检查 API 容器是否启动：
```bash
docker compose ps
docker compose logs api
```

## 🌐 生产环境部署

### 反向代理配置（Nginx 示例）

```nginx
# Grafana
location /grafana/ {
    proxy_pass http://localhost:3000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}

# Prometheus（建议加密码保护）
location /prometheus/ {
    auth_basic "Restricted";
    auth_basic_user_file /etc/nginx/.htpasswd;
    proxy_pass http://localhost:9090/;
}
```

### 安全建议

1. **修改默认密码** - 首次登录 Grafana 后立即修改
2. **限制访问** - 使用 Nginx 密码认证或 IP 白名单
3. **HTTPS** - 生产环境必须使用 HTTPS
4. **防火墙** - 不要直接暴露 9090 和 3000 端口

## 📚 进一步阅读

- [Prometheus 官方文档](https://prometheus.io/docs/)
- [Grafana 官方文档](https://grafana.com/docs/)
- [PromQL 查询语言](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Grafana Dashboard 最佳实践](https://grafana.com/docs/grafana/latest/best-practices/best-practices-for-creating-dashboards/)
