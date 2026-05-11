# 抖音主页视频链接同步（多用户 / 高并发骨架）

按博主 **抖音号**（如 `y096031`）分页同步主页视频链接：每批最多 **100 条新增**；同一登录用户下以 **`(user_id, aweme_id)`** 去重；断点通过任务上的 **`cursor`** 持久化。

## 架构

- **前端**：Vue 3 + TypeScript + Vite（登录 / 注册 / 发起同步 / 任务与链接列表）
- **API**：FastAPI + JWT + PostgreSQL（SQLAlchemy 异步）
- **队列**：Redis + [arq](https://github.com/python-arq/arq) Worker 执行同步任务
- **抖音适配器**：默认 **Mock**；可选 **HTTP** 对接桥接服务。内置 **[bridge/](bridge/)** 薄层，将高星上游 [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) 的 `/api/douyin/web/...` 映射为本项目契约（详见 [bridge/README.md](bridge/README.md)）

## 高并发与限流（已实现）

| 机制 | 作用 |
| --- | --- |
| **Uvicorn 多进程** | `UVICORN_WORKERS`：水平扩展 API 进程（每台机器多 worker，前加负载均衡即可多机） |
| **SQLAlchemy 连接池** | `DB_POOL_SIZE` / `DB_MAX_OVERFLOW`：单进程内数据库连接上限，避免打满 Postgres |
| **部分唯一索引** | 同一用户、同一抖音号在 `pending` / `running` 时只能有 **一条** 活跃任务；并发请求下第二条会 **409**（数据库兜底 `IntegrityError`） |
| **按用户 Redis 限流** | `RATE_LIMIT_SYNC_PER_USER_PER_MINUTE`：创建同步任务的频率上限，多 API 实例共享 Redis |
| **抖音抓取许可池** | `DOUYIN_FETCH_MAX_CONCURRENT`：全集群（所有 Worker）同时调用 `resolve` / `fetch` 的并发上限，用 Redis 列表 + `BLPOP` 实现 |
| **arq 并行 Job** | `WORKER_MAX_JOBS`：单 Worker **进程**内并行执行的任务数；`WORKER_JOB_TIMEOUT`：单任务超时秒数 |
| **水平扩 Worker** | `docker compose up -d --scale worker=4`：多容器消费同一 Redis 队列（与许可池、DB 池配合调参） |

就绪探针：`GET /ready`（会 `PING` Redis）。

**调参提示**：总 DB 连接约等于 `UVICORN_WORKERS × (DB_POOL_SIZE + DB_MAX_OVERFLOW) + worker副本数 × (...)`，不要超过 Postgres `max_connections`。许可池大小变更后若需重建，可在维护窗口对 Redis 执行 `DEL douyin:fetch_permits`（若配置了 `REDIS_KEY_PREFIX`，则为 `{前缀}:douyin:fetch_permits`，例如统一基建默认 `tl:` 时为 `tl:douyin:fetch_permits`）后重启服务（见 `app/douyin_pool.py`）。

## 快速启动（Docker）

在项目根目录：

```bash
docker compose up --build
```

**启用真实数据时的前提（当前 compose 默认已接 `http` + `bridge`）**：请先在宿主机 **19001** 启动 [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) 并配置 Cookie；否则同步任务会在解析抖音号时失败。若需改上游端口，请同步修改 `bridge` 服务的 `UPSTREAM_BASE_URL`。

- API：<http://localhost:18080>（文档：<http://localhost:18080/docs>，就绪：<http://localhost:18080/ready>）
- **bridge**（可选）：宿主机端口见 `docker-compose.yml` 中映射（默认 **19190**，对应健康检查 <http://localhost:19190/health>），容器内端口 9000；默认请求本机 **`UPSTREAM_BASE_URL=http://host.docker.internal:19001`** 上的 Evil0ctal 上游。**若本机 19001 已被占用（例如 MinIO），请把 Evil0ctal 改到其他端口并同步修改 compose 里 bridge 的 `UPSTREAM_BASE_URL`。**
- Postgres：`localhost:5432`（用户/库：`douyin` / `douyin_app`）
- Redis：`localhost:6379`

前端在本地开发（默认连本机 API）：

```bash
cd frontend
npm install
npm run dev
```

浏览器打开前端：<http://localhost:5174>。`frontend/.env.development` 中 `VITE_API_BASE=http://localhost:18080` 需与 Docker 映射的 API 宿主机端口一致。

## 真实数据从零跑通（详细步骤）

链路顺序：**浏览器 → 本仓库前端/API** → **bridge（宿主机映射端口见 compose，默认 19190）** → **Evil0ctal（宿主机端口见 UPSTREAM，勿与其它项目冲突）** → 抖音 Web API。缺任何一环，`resolve` / 同步任务会失败或超时。

### 0. 本机环境

- 已安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)（Windows 需开启 WSL2 后端时保证 `host.docker.internal` 可用；`docker-compose.yml` 里 `bridge` 已配 `extra_hosts`）。
- 可选：Node.js 18+（跑前端）、Git。

### 1. 部署上游 Evil0ctal（必须在本机可访问端口，默认 **19001**）

任选其一（与 `bridge` 的 `UPSTREAM_BASE_URL=http://host.docker.internal:19001` 对齐；改端口则同步改 compose 里 `bridge.environment.UPSTREAM_BASE_URL`）。

**方式 A：Docker 跑上游（省事）**

```bash
docker pull evil0ctal/douyin_tiktok_download_api:latest
docker run -d --name douyin_upstream -p 19001:80 evil0ctal/douyin_tiktok_download_api:latest
```

容器内 API 监听 **80**，映射到宿主机 **19001**。抖音 Cookie 在容器路径 **`/app/crawlers/douyin/web/config.yaml`**（见上游 [README「Docker」与「配置文件修改」](https://github.com/Evil0ctal/Douyin_TikTok_Download_API)）。

**若你已 `docker run` 但未挂载卷**（最常见），用下面方式改 Cookie 即可：

1. 把配置拷到本机（PowerShell，路径可改成你喜欢的目录，**勿提交到 Git**）：

   ```powershell
   docker cp douyin_upstream:/app/crawlers/douyin/web/config.yaml $env:USERPROFILE\douyin-web-config.yaml
   ```

2. 用编辑器打开 `douyin-web-config.yaml`，找到 `TokenManager` → `douyin` → `headers` → **`Cookie:`**，整行替换为你登录 [douyin.com](https://www.douyin.com) 后在开发者工具里复制的 Cookie 字符串；**不要改**文件里注明禁止修改的 `User-Agent` 等项。

3. 拷回容器并重启：

   ```powershell
   docker cp $env:USERPROFILE\douyin-web-config.yaml douyin_upstream:/app/crawlers/douyin/web/config.yaml
   docker restart douyin_upstream
   ```

4. 浏览器打开 <http://localhost:19001/docs>，在 Swagger 里试 **`/api/douyin/web/get_sec_user_id`**（传入带抖音号的用户页 URL），能返回 `sec_uid` 即 Cookie 与链路基本正常。

**以后重建容器时**可改用卷挂载，避免每次 `cp`：准备同上编辑好的 `douyin-web-config.yaml`，删除旧容器后执行  
`docker run -d --name douyin_upstream -p 19001:80 -v "${env:USERPROFILE}\douyin-web-config.yaml:/app/crawlers/douyin/web/config.yaml" evil0ctal/douyin_tiktok_download_api:latest`  
（路径含空格时请给 `-v` 左侧加引号。）

**方式 B：源码运行上游**

```bash
git clone https://github.com/Evil0ctal/Douyin_TikTok_Download_API.git
cd Douyin_TikTok_Download_API
# 建议使用 Python 3.10+ 虚拟环境
pip install -r requirements.txt
```

1. 编辑仓库根目录 **`config.yaml`**：在 `API:` 下把 **`Host_Port`** 改为 **`19001`**（`Host_IP` 保持 `0.0.0.0` 即可）。
2. 编辑 **`crawlers/douyin/web/config.yaml`**：在 `TokenManager` → `douyin` → `headers` 下，把 **`Cookie`** 换成你在浏览器登录 [douyin.com](https://www.douyin.com) 后复制的 Cookie 字符串；**不要改**该文件中注释禁止修改的 `User-Agent` 等字段（见文件内英文说明）。
3. 启动：`python start.py`（或按上游文档使用 `start.sh` / systemd）。浏览器打开 <http://localhost:19001/docs> 应能看到 Swagger。

**Cookie 与风控**：匿名或过期 Cookie 容易导致 `get_sec_user_id` / 作品列表失败；更换 Cookie 后必须**重启上游进程/容器**。**两枚 Cookie 轮换**：起两个 Evil0ctal（不同端口、各自挂载一份 `crawlers/douyin/web/config.yaml`），在 `docker-compose.yml` 的 **`bridge`** 服务里设置 **`UPSTREAM_BASE_URLS`**（逗号分隔两个根地址，示例见 compose 注释）；内置 bridge 会按请求 **轮询** 上游。详见 [bridge/README.md](bridge/README.md)。

### 2. 启动本仓库（Postgres + Redis + bridge + api + worker）

在 **`g:\textloading`**（或你的克隆根目录）执行：

```bash
docker compose up -d --build
```

当前 `docker-compose.yml` 已默认 **`DOUYIN_ADAPTER=http`**，且 **`DOUYIN_HTTP_*` 指向 `http://bridge:9000/...`**，无需再手工取消注释。

### 3. 验证整条链路

| 步骤 | URL / 命令 | 期望 |
| --- | --- | --- |
| 上游文档 | <http://localhost:19001/docs> | 能打开 Swagger |
| bridge 健康检查 | <http://localhost:19190/health>（端口以 compose 为准） | 返回正常 |
| 试解析（把 `抖音号` 换成真实 unique_id） | <http://localhost:19190/douyin/resolve?unique_id=抖音号> | JSON 含 `sec_uid`；若上游未起或 Cookie 无效会 502/错误体 |
| 本 API 演示模式关闭 | <http://localhost:18080/config/public> | `demo_mode` 为 **`false`** |
| 依赖就绪 | <http://localhost:18080/ready> | 200 |

### 4. 前端操作

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 <http://localhost:5174>：注册 → 登录 → 输入抖音号发起同步 → 在任务/视频列表中打开链接，应为 **`https://www.douyin.com/video/<数字作品ID>`** 形式且可打开。

### 5. 常见问题

- **bridge 502**：上游未监听 19001、防火墙拦截、或 `UPSTREAM_BASE_URL` 与实际上游地址不一致。
- **resolve 成功但作品很少或为 0**：Cookie 失效、该账号隐私设置、或抖音风控；先在上游 `/docs` 里直接调 `get_sec_user_id` / `fetch_user_post_videos` 对比。
- **仍显示演示模式**：`DOUYIN_ADAPTER` 不是 `http`，或 API/Worker 环境不一致（compose 中应已一致）。

## 切换到真实数据（从 Mock 改为 http）

本仓库 **不包含** 直连抖音的爬虫实现（签名、Cookie 易变且涉及合规），真实数据依赖你自建的 **「桥接 HTTP 服务」**，本项目的 `http` 适配器只负责按固定契约去请求它。

### 第一步：部署上游 + 桥接

GitHub 上**没有**与 `DOUYIN_HTTP_*` 完全一致的双 GET 成品；高星、适合当 **HTTP 上游** 的仓库如下（仍需桥接映射）：

| 仓库 | Star 量级 | 维护 | 说明 |
| --- | --- | --- | --- |
| [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) | ~17k | README 显示 2025 年仍有提交 | **推荐**：自带 FastAPI，`/api/douyin/web/get_sec_user_id`、`/api/douyin/web/fetch_user_post_videos` 等 |
| [JoeanAmier/TikTokDownloader](https://github.com/JoeanAmier/TikTokDownloader) | ~14k | 提交活跃 | 偏采集/下载工具，需**自写**与本项目契约一致的桥接 |
| [Johnserf-Seed/TikTokDownload](https://github.com/Johnserf-Seed/TikTokDownload) | ~8.5k | 较弱 | 可作参考 |

**推荐路径（与本仓库对齐）**：

1. 克隆并部署 **Evil0ctal**，在本机 **19001** 端口启动（与 `bridge` 服务环境变量 `UPSTREAM_BASE_URL` 一致），按上游文档配置 **Cookie**。
2. `docker compose up -d --build` 会构建并启动 **[bridge/](bridge/)**（默认映射宿主机 **19190→9000**，可按需修改 compose）。桥接将上游转为项目所需两个 `GET`（见 [bridge/README.md](bridge/README.md)）。
3. 确认 `docker-compose.yml` 里 `api` / `worker` 的 `DOUYIN_ADAPTER` 为 **`http`**，且 **`DOUYIN_HTTP_*`** 指向 `http://bridge:9000/douyin/...`（仓库默认已如此；若你曾改为 `mock`，请改回并恢复两行 URL）。

若不用内置 `bridge`，也可自写任意服务，只要能提供契约中的 **两个 GET** 与 JSON 形状即可。

### 第二步：改环境变量（api 与 worker 必须完全一致）

| 变量 | 说明 |
| --- | --- |
| `DOUYIN_ADAPTER` | 改为 **`http`** |
| `DOUYIN_HTTP_RESOLVE_URL` | 必须包含字面量 **`{unique_id}`**（程序会替换为抖音号）。`GET` 返回 **`{"sec_uid":"..."}`** |
| `DOUYIN_HTTP_FEED_URL` | 必须包含 **`{sec_uid}`** 与 **`{cursor}`**。`GET` 返回 **`{"items":[{"aweme_id":"...","share_url":"..."}],"next_cursor":"...","has_more":true}`** |

约定细节：

- 首次同步时 `cursor` 为 **空字符串**；桥接应返回第一页，并在无更多数据时设 `has_more: false`。
- `share_url` 须为抖音站可打开的地址（一般为 **`https://www.douyin.com/video/<数字aweme_id>`**）。

### 第三步：重启

```bash
docker compose up -d --build
```

完成后访问 **`GET /config/public`**：`demo_mode` 应为 **`false`**；工作台不再显示橙色「演示模式」横幅。

`docker-compose.yml` 已包含 **`bridge` 服务**，且 **`DOUYIN_ADAPTER=http`** 与 **`DOUYIN_HTTP_*`（指向 `http://bridge:9000`）** 已对 `api` / `worker` 默认开启。若改回 Mock，将两者改为 `mock` 并去掉或注释 `DOUYIN_HTTP_*` 即可。

---

## 对接自建抖音 HTTP 服务（http 适配器，契约摘要）

设置环境变量（`docker-compose.yml` 的 `api` / `worker` 均需一致）：

| 变量 | 说明 |
| --- | --- |
| `DOUYIN_ADAPTER` | `mock`（默认）或 `http` |
| `DOUYIN_HTTP_RESOLVE_URL` | 必须包含 `{unique_id}`。`GET` 后返回 JSON：`{"sec_uid":"..."}` |
| `DOUYIN_HTTP_FEED_URL` | 必须包含 `{sec_uid}` 与 `{cursor}`。`GET` 后返回 JSON：`{"items":[{"aweme_id":"...","share_url":"..."}],"next_cursor":"...","has_more":true}` |

`cursor` 首次为空字符串；你的服务应据此返回第一页。

### 与高并发相关的环境变量（节选）

| 变量 | 默认值（compose 内） | 说明 |
| --- | --- | --- |
| `UVICORN_WORKERS` | `2` | API 进程数 |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | `10` / `30` | 异步连接池 |
| `RATE_LIMIT_SYNC_PER_USER_PER_MINUTE` | `30` | 每用户每分钟最多创建同步任务次数 |
| `DOUYIN_FETCH_MAX_CONCURRENT` | `8` | 全集群访问抖音适配器的并发上限 |
| `WORKER_MAX_JOBS` | `8` | 单 Worker 进程并行 job 数 |
| `WORKER_JOB_TIMEOUT` | `900` | 单 job 超时（秒） |

## API 摘要

- `POST /auth/register` `{ "email", "password" }`
- `POST /auth/login` → `{ "access_token" }`
- `POST /tasks/sync` Header `Authorization: Bearer <token>`，body `{ "unique_id": "y096031" }`
- `GET /tasks`、`GET /tasks/{id}`、`GET /videos`

## 常见问题：采集到的抖音链接打不开、提示「不是有效视频」

- **默认 `DOUYIN_ADAPTER=mock`** 时，数据是**联调用假数据**，不是抖音站上的真实作品 ID。此前 Mock 曾把 `sec_uid` 风格字符串写进 `/video/` 路径，更容易被误判；即使改为数字形态，**假 ID 在 [douyin.com/video/…](https://www.douyin.com/video/) 仍会无效**。
- **要在浏览器里打开真实视频页**，必须改为 **`DOUYIN_ADAPTER=http`**，由你部署的解析服务返回真实 **`aweme_id` / `share_url`**（与官方页面一致，一般为长数字作品 ID）。

### 为什么真实博主只有 40 条作品，系统却显示新增 100 条？

- **Mock 模式**下程序**不会访问抖音**，输入的抖音号只参与本地假 `sec_uid` 的生成，**作品条数、链接内容都与该账号真实主页无关**。
- 任务参数里「每批最多 100 条」指**本批最多写入 100 条新记录**；Mock 会按分页一直造数据直到凑满 100 条或假数据分页结束，所以经常出现「比真实作品数还多」——**不是爬虫算错，而是演示数据在占位**。
- 工作台在 Mock 下会显示 **「演示模式」** 提示（接口 `GET /config/public` 的 `demo_mode` / `demo_explain` 亦可给其它客户端使用）。

## 合规说明

非官方抓取可能违反平台协议；生产环境请自行评估法律与平台规则，并做好限流与审计。
