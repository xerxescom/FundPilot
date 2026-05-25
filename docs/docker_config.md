# Docker 配置说明

FundPilot 维护两套互不影响的配置：

- 本地开发：使用 `.env`，适合 `uv run uvicorn` 和 `npm run dev` 直接在宿主机启动。
- Docker 部署：使用 `.env.docker`，只包含 `DOCKER_*` 变量，适合 `docker-compose` 启动容器。

`.env` 和 `.env.docker` 不共用变量名，避免本地的 `localhost`、端口或 Ollama 地址影响容器部署。

## 配置文件

| 文件 | 是否提交 | 用途 |
| --- | --- | --- |
| `.env.example` | 是 | 本地开发配置模板 |
| `.env` | 否 | 本地开发实际配置 |
| `.env.docker.example` | 是 | Docker 部署配置模板 |
| `.env.docker` | 否 | Docker 部署实际配置 |
| `docker-compose.yml` | 是 | Docker 服务编排 |

## 服务组成

| 服务 | 镜像/构建 | 容器内端口 | 默认宿主机端口 | 说明 |
| --- | --- | --- | --- | --- |
| `postgres` | `postgres:16` | `5432` | `5432` | PostgreSQL 数据库，数据写入 `postgres_data` volume |
| `backend` | 根目录 `Dockerfile` 构建 | `8000` | `8000` | FastAPI 后端，连接 compose 内部的 `postgres` 服务 |
| `frontend` | `node:20-alpine` | `5173` | `5173` | Vite Vue 开发服务，代理 `/api` 和 `/health` 到 backend |

宿主机端口通过 `.env.docker` 的 `DOCKER_POSTGRES_PORT`、`DOCKER_BACKEND_PORT`、`DOCKER_FRONTEND_PORT` 调整；容器内部端口固定，便于服务互相发现。

## Docker 专用变量

`.env.docker` 示例：

```env
DOCKER_POSTGRES_PORT=5432
DOCKER_POSTGRES_DB=fund_watcher
DOCKER_POSTGRES_USER=postgres
DOCKER_POSTGRES_PASSWORD=postgres

DOCKER_BACKEND_PORT=8000
DOCKER_FRONTEND_PORT=5173
DOCKER_SYNC_NAV_CRON=18:00
DOCKER_ENABLE_SCHEDULER=false
DOCKER_AUTO_CREATE_TABLES=true

DOCKER_AI_PROVIDER=ollama
DOCKER_OLLAMA_BASE_URL=http://host.docker.internal:11434
DOCKER_OLLAMA_MODEL=qwen3:14b
DOCKER_OLLAMA_TIMEOUT=180
DOCKER_ONLINE_LLM_API_KEY=
```

关键点：

- 后端容器内 `DATABASE_URL` 固定使用 `postgres:5432`，不会读取本地 `.env` 里的 `localhost`。
- 前端容器内 `VITE_API_PROXY_TARGET` 固定为 `http://backend:8000`。
- Docker 访问宿主机 Ollama 时使用 `DOCKER_OLLAMA_BASE_URL=http://host.docker.internal:11434`。
- 本地非 Docker 启动时仍使用 `.env` 里的 `OLLAMA_BASE_URL=http://localhost:11434`。

## 本地部署步骤

1. 准备 Docker 配置：

```bash
copy .env.docker.example .env.docker
```

2. 启动完整服务：

```bash
docker-compose --env-file .env.docker up --build
```

如果你的 Docker 支持新版 compose，也可以使用：

```bash
docker compose --env-file .env.docker up --build
```

3. 访问地址：

- Vue 前端：http://127.0.0.1:5173
- FastAPI 健康检查：http://127.0.0.1:8000/health
- API 文档：http://127.0.0.1:8000/docs
- PostgreSQL：`localhost:5432`

## 常用命令

后台启动：

```bash
docker-compose --env-file .env.docker up -d --build
```

查看日志：

```bash
docker-compose --env-file .env.docker logs -f backend
docker-compose --env-file .env.docker logs -f frontend
```

执行 Alembic 迁移：

```bash
docker-compose --env-file .env.docker exec backend alembic upgrade head
```

停止并保留数据库数据：

```bash
docker-compose --env-file .env.docker down
```

停止并删除数据库 volume：

```bash
docker-compose --env-file .env.docker down -v
```

## 验证清单

- `docker-compose --env-file .env.docker ps` 中三个服务都处于 running/healthy。
- 打开 `/health` 返回 `{"status":"ok", ...}`。
- 打开 Vue 首页，今日驾驶舱能正常加载。
- 在自选基金中添加基金后，可以进入详情并执行“一键同步并分析”。
- 如果 AI 简报需要 Ollama，确认宿主机 Ollama 已启动，并且模型已拉取。
