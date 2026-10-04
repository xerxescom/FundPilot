# Docker 配置说明

FundPilot 维护两套互不影响的配置：

- 本地开发：使用 `.env`，适合 `uv run uvicorn`、`python -m app.worker` 和 `npm run dev` 直接在宿主机启动。
- Docker 部署：使用 `.env.docker`，`DOCKER_*` 变量供 compose 插值（端口/库名），其余变量通过 `env_file` 注入容器。

## 配置文件

| 文件 | 是否提交 | 用途 |
| --- | --- | --- |
| `.env.example` | 是 | 本地开发配置模板 |
| `.env` | 否 | 本地开发实际配置 |
| `.env.docker.example` | 是 | Docker 部署配置模板 |
| `.env.docker` | 否 | Docker 部署实际配置 |
| `docker-compose.yml` | 是 | Docker 服务编排 |
| `frontend/nginx.conf` | 是 | 前端静态托管与 `/api` 反代 |

## 服务组成

| 服务 | 镜像/构建 | 容器内端口 | 默认宿主机端口 | 说明 |
| --- | --- | --- | --- | --- |
| `postgres` | `postgres:16` | `5432` | `5432`（仅 127.0.0.1） | 数据写入 `postgres_data` volume |
| `migrate` | 根目录 `Dockerfile` | — | — | 一次性服务：`alembic upgrade head`，成功后才启动后端与 worker |
| `backend` | 根目录 `Dockerfile` | `8000` | `8000`（仅 127.0.0.1） | FastAPI 后端；`AUTO_CREATE_TABLES=false`，迁移由 `migrate` 负责；健康检查走 `/readyz`（数据库连通 + 迁移到 head） |
| `worker` | 根目录 `Dockerfile` | `9101`（指标，可选） | — | 批次 worker（`python -m app.worker`），`restart: unless-stopped`；探针 `--healthcheck` 只查数据库连通 |
| `frontend` | `frontend/Dockerfile` | `80` | `5173`（仅 127.0.0.1） | nginx 托管前端构建产物，反代 `/api`、`/health`、`/livez`、`/readyz` |

依赖顺序：`postgres`（healthy）→ `migrate`（completed）→ `backend` / `worker` → `frontend`（backend healthy）。所有对外端口默认只绑定回环地址。

**指标**：后端在 `/metrics` 暴露 Prometheus 指标（HTTP 请求、任务、批次、数据源），仅 127.0.0.1:8000 本机可达——`frontend/nginx.conf` 刻意不反代该路径。worker 的进程内计数器通过 `WORKER_METRICS_PORT=9101` 在 compose 内网暴露，不映射到宿主机；批次状态另有查库 Gauge，从后端 `/metrics` 也能看到。

## 变量说明

`.env.docker` 示例（完整列表见 `.env.docker.example`）：

```env
# compose 插值
DOCKER_POSTGRES_PORT=5432
DOCKER_POSTGRES_DB=fund_watcher
DOCKER_POSTGRES_USER=postgres
DOCKER_POSTGRES_PASSWORD=postgres
DOCKER_BACKEND_PORT=8000
DOCKER_FRONTEND_PORT=5173
DOCKER_SYNC_NAV_CRON=18:00
DOCKER_ENABLE_SCHEDULER=false
DOCKER_OLLAMA_BASE_URL=http://host.docker.internal:11434

# 通过 env_file 注入容器（不带前缀）
AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=
QWEN_API_KEY=
WORKER_POLL_SECONDS=2
LEASE_TTL_SECONDS=120
# 可观测性（可选）
LOG_LEVEL=INFO
LOG_JSON=false
# 账户基准对比（默认沪深300）
BENCHMARK_INDEX_CODE=sh000300
```

关键点：

- 后端/worker 容器内 `DATABASE_URL` 由 compose 拼成 `postgres:5432`，不会读取本地 `.env` 里的 `localhost`。
- Docker 访问宿主机 Ollama 使用 `DOCKER_OLLAMA_BASE_URL=http://host.docker.internal:11434`。
- 在线模型密钥只在后端环境变量中（`.env.docker`），前端与 git 都不包含。
- 新表由迁移创建；开发环境（`APP_ENV=dev` + `AUTO_CREATE_TABLES=true`）才有附加列自动兼容补丁，Docker 路径不走该补丁。

## 启动与常用命令

```bash
copy .env.docker.example .env.docker
docker compose --env-file .env.docker up -d --build

docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs -f backend
docker compose --env-file .env.docker logs --tail 20 worker

# 手动补跑迁移（正常情况下 migrate 服务已执行）
docker compose --env-file .env.docker run --rm migrate

docker compose --env-file .env.docker down        # 停止，保留数据卷
docker compose --env-file .env.docker down -v     # 停止并删除数据卷（危险）
```

## 定时备份（宿主侧）

后端镜像不含 `pg_dump`，备份脚本默认经 `docker exec` 调用 postgres 容器，因此定时任务放在宿主机：

```bash
# Linux cron（每天 03:15，保留最近 14 份）
15 3 * * * cd /opt/FundPilot && .venv/bin/python scripts/backup_database.py --keep 14 >> backups/backup.log 2>&1

# Windows 任务计划
schtasks /Create /SC DAILY /TN FundPilotBackup /ST 03:15 ^
  /TR "E:\codeX-worksapce\FundPilot\.venv\Scripts\python.exe E:\codeX-worksapce\FundPilot\scripts\backup_database.py --keep 14"
```

`--keep` 决定保留份数，也就是最坏情况下的数据丢失窗口；定期用 `restore_database.py` 做恢复演练。

## 验证清单

- `docker compose ... ps`：postgres 为 healthy，migrate 退出码 0，backend healthy（`/readyz`），worker healthy，frontend healthy。
- `http://127.0.0.1:8000/livez` 返回 ok；`http://127.0.0.1:8000/readyz` 返回 `status: ready` 且 revision 为 head；`http://127.0.0.1:8000/metrics` 能看到 `fundpilot_` 前缀指标。
- 打开 `http://127.0.0.1:5173`，驾驶舱可加载；点击"更新今日数据"后批次出现在任务中心。
- `docker compose ... logs worker` 能看到 worker 启动与领取日志。
- Ollama/DeepSeek 等模型服务按需在宿主机准备；密钥无效时日报自动走规则兜底，不影响核心流程。
