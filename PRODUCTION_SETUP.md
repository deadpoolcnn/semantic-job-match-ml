# 生产环境部署配置清单

本文档详细说明在生产服务器上部署 Prometheus + Grafana 监控系统所需的配置。

## ✅ 部署前检查清单

### 1. GitHub Secrets 配置

在 GitHub 仓库中添加以下 secrets：

```
仓库 → Settings → Secrets and variables → Actions → New repository secret
```

必需的 secrets：
- ✅ `SERVER_HOST` - 服务器地址
- ✅ `SERVER_USER` - SSH 用户名
- ✅ `SSH_PRIVATE_KEY` - SSH 私钥
- ✅ `MOONSHOT_API_KEY` - Moonshot API Key
- ✅ `MOONSHOT_MODEL` - 模型名称（如 kimi-k2-turbo-preview）
- 🆕 `GRAFANA_ADMIN_PASSWORD` - Grafana 管理员密码（**必须设置！**）

### 2. 服务器端口开放

确保以下端口可访问（根据需要配置防火墙/安全组）：

| 服务 | 端口 | 访问范围 | 说明 |
|------|------|---------|------|
| API | 8000 | 内网 | 通过 Nginx 反向代理 |
| Grafana | 3000 | 内网 | 通过 Nginx 反向代理 |
| Prometheus | 9090 | 内网 | 通过 Nginx 反向代理（可选） |
| Redis | 6379 | 内网 | 仅容器间通信 |

**安全建议：** 不要直接暴露这些端口到公网，全部通过 Nginx 反向代理 + HTTPS 访问。

### 3. Nginx 反向代理配置

#### 方案 A：独立子域名（推荐）

创建 `/etc/nginx/sites-available/monitoring.fuppuccino.vip`:

```nginx
server {
    listen 80;
    server_name monitoring.fuppuccino.vip;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name monitoring.fuppuccino.vip;

    ssl_certificate /path/to/your/fullchain.pem;
    ssl_certificate_key /path/to/your/privkey.pem;

    # SSL 配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Grafana
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket 支持（Grafana 实时更新需要）
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

启用配置：
```bash
sudo ln -s /etc/nginx/sites-available/monitoring.fuppuccino.vip /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

#### 方案 B：主域名子路径

在现有的 `analysis.fuppuccino.vip` 配置中添加：

```nginx
server {
    listen 443 ssl http2;
    server_name analysis.fuppuccino.vip;

    # ... 现有的 SSL 和 API 配置 ...

    # Grafana 监控面板
    location /monitoring/ {
        rewrite ^/monitoring/(.*) /$1 break;
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Prometheus（可选，建议加密码保护）
    location /prometheus/ {
        auth_basic "Prometheus Access";
        auth_basic_user_file /etc/nginx/.htpasswd;
        
        rewrite ^/prometheus/(.*) /$1 break;
        proxy_pass http://127.0.0.1:9090;
        proxy_set_header Host $host;
    }
}
```

如果使用子路径，需要更新 `.env` 中的 `GRAFANA_ROOT_URL`：
```bash
GRAFANA_ROOT_URL=https://analysis.fuppuccino.vip/monitoring
```

创建 Prometheus 访问密码（可选）：
```bash
sudo apt install apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd admin
# 输入密码
```

### 4. DNS 配置（如果使用独立域名）

添加 A 记录：
```
monitoring.fuppuccino.vip → 你的服务器IP
```

### 5. SSL 证书（如果使用独立域名）

使用 Let's Encrypt：
```bash
sudo certbot --nginx -d monitoring.fuppuccino.vip
```

## 🚀 部署步骤

### 步骤 1：在 GitHub 添加 Secrets

1. 打开 https://github.com/deadpoolcnn/semantic-job-match-ml/settings/secrets/actions
2. 点击 "New repository secret"
3. 添加 `GRAFANA_ADMIN_PASSWORD`（值：你的安全密码）

### 步骤 2：提交代码并触发部署

```bash
# 在本地
git add -A
git commit -m "feat: add Prometheus + Grafana monitoring"
git push origin master
```

GitHub Actions 会自动：
1. 构建包含监控系统的 Docker 镜像
2. 推送到 ghcr.io
3. SSH 到服务器
4. 创建包含 `GRAFANA_ADMIN_PASSWORD` 的 `.env` 文件
5. 拉取最新镜像
6. 启动所有服务（redis + api + worker + prometheus + grafana）

### 步骤 3：配置 Nginx（服务器端）

SSH 到服务器：
```bash
ssh root@你的服务器IP
```

根据上面的方案 A 或方案 B 配置 Nginx，然后：
```bash
sudo nginx -t
sudo systemctl reload nginx
```

### 步骤 4：验证部署

```bash
# 检查所有容器是否运行
cd /www/wwwroot/semantic-job-match-ml
docker compose ps

# 应该看到：
# - redis
# - api
# - worker
# - prometheus
# - grafana

# 测试服务健康
curl http://localhost:8000/health          # API
curl http://localhost:8000/metrics         # Prometheus metrics
curl http://localhost:9090/-/healthy       # Prometheus
curl http://localhost:3000/api/health      # Grafana
```

### 步骤 5：首次登录 Grafana

访问 `https://monitoring.fuppuccino.vip`（或 `https://analysis.fuppuccino.vip/monitoring`）

使用凭证：
- 用户名: `admin`
- 密码: 你在 GitHub Secrets 中设置的 `GRAFANA_ADMIN_PASSWORD`

首次登录后会自动加载：
- ✅ Prometheus 数据源
- ✅ API Metrics 仪表盘

## 🔍 故障排查

### Grafana 显示 "Bad Gateway"

```bash
# 检查 Grafana 容器状态
docker compose logs grafana

# 重启 Grafana
docker compose restart grafana
```

### Prometheus 采集不到数据

```bash
# 检查 API 的 /metrics 端点
curl http://localhost:8000/metrics

# 检查 Prometheus targets
curl http://localhost:9090/api/v1/targets | jq
```

### 无法访问 Grafana

1. 检查防火墙/安全组是否允许 443 端口
2. 检查 Nginx 配置是否正确
3. 查看 Nginx 日志：`sudo tail -f /var/log/nginx/error.log`

## 📊 访问监控

部署成功后，可通过以下方式访问：

### Grafana 仪表盘
```
https://monitoring.fuppuccino.vip
或
https://analysis.fuppuccino.vip/monitoring
```

### Prometheus 查询界面（如果配置了）
```
https://analysis.fuppuccino.vip/prometheus
```

### API Metrics 端点（仅内网）
```
http://localhost:8000/metrics
```

## 🔒 安全最佳实践

1. ✅ **使用强密码** - `GRAFANA_ADMIN_PASSWORD` 至少 16 位随机字符
2. ✅ **启用 HTTPS** - 生产环境必须使用 SSL
3. ✅ **限制访问** - 考虑使用 IP 白名单或 VPN
4. ✅ **定期更新** - 保持 Grafana/Prometheus 版本最新
5. ✅ **备份配置** - 定期导出 Grafana 仪表盘配置

## 📝 维护命令

```bash
# 查看所有容器状态
docker compose ps

# 查看监控系统日志
docker compose logs -f prometheus grafana

# 重启监控系统
docker compose restart prometheus grafana

# 备份 Grafana 数据
docker compose exec grafana grafana-cli admin export-dashboard > backup.json

# 清理旧的 Prometheus 数据（释放空间）
docker compose exec prometheus promtool tsdb clean
```

## 🎯 下一步

监控系统部署完成后，建议：

1. 在 Grafana 中创建自定义仪表盘
2. 配置告警规则（Grafana Alerts）
3. 集成 Alertmanager（邮件/Slack 通知）
4. 添加更多自定义业务指标

详细使用说明见 [MONITORING.md](MONITORING.md)
