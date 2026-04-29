# Douyin 薄桥接（Evil0ctal → textloading 契约）

本目录实现两个 `GET`，供主项目 `DOUYIN_ADAPTER=http` 使用，内部请求已部署的 [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API)。

## 映射关系

| 本桥接 | 上游 Evil0ctal（`UPSTREAM_BASE_URL` 根路径下） |
|--------|-----------------------------------------------|
| `GET /douyin/resolve?unique_id=` | `GET /api/douyin/web/get_sec_user_id?url=https://www.douyin.com/user/{unique_id}` |
| `GET /douyin/feed?sec_uid=&cursor=` | `GET /api/douyin/web/fetch_user_post_videos?sec_user_id=&max_cursor=&count=` |

返回 JSON 已转换为主项目 `HttpProxyDouyinAdapter` 所需字段：`sec_uid`、`items[].aweme_id`、`share_url`、`next_cursor`、`has_more`。

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `UPSTREAM_BASE_URL` | `http://host.docker.internal:19001` | 单个 Evil0ctal 根地址（无尾部 `/`） |
| `UPSTREAM_BASE_URLS` | 空 | **多实例轮询**：逗号或分号分隔多个根地址（与上面二选一；若设置且非空，则**忽略** `UPSTREAM_BASE_URL`）。用于「两个 Cookie = 两个上游容器、不同端口」 |
| `UPSTREAM_TIMEOUT_SECONDS` | `60` | 请求上游超时 |
| `BRIDGE_FEED_PAGE_SIZE` | `20` | 每页条数（与上游 `count` 一致） |

### 两个 Cookie 轮换（推荐做法）

Evil0ctal **每个进程/容器只读一份** `crawlers/douyin/web/config.yaml`，因此要两枚 Cookie 请起 **两个上游**，例如：

- 实例 A：`docker run ... -p 19001:80 -v %USERPROFILE%\douyin-cookie-a.yaml:/app/crawlers/douyin/web/config.yaml ...`
- 实例 B：另起容器 `-p 19002:80`，挂载 **另一份** 含 Cookie B 的 yaml。

然后设置 bridge：

```text
UPSTREAM_BASE_URLS=http://host.docker.internal:19001,http://host.docker.internal:19002
```

bridge 对 `resolve` / `feed` 的每次上游请求 **轮流** 选用列表中的地址（简单轮询，分散风控压力）。`GET /health` 会返回 `upstreams` 与 `rotation: true/false`。

## 本地运行

1. 按上游文档在本机 **19001** 端口启动 Evil0ctal（端口可改，需与 `UPSTREAM_BASE_URL` 一致），并配置好 **Cookie** 等。
2. 本桥接：

```bash
cd bridge
pip install -r requirements.txt
set UPSTREAM_BASE_URL=http://127.0.0.1:19001
uvicorn main:app --host 0.0.0.0 --port 9000
```

3. 主项目 `.env` / compose 中设置：

- `DOUYIN_ADAPTER=http`
- `DOUYIN_HTTP_RESOLVE_URL=http://bridge:9000/douyin/resolve?unique_id={unique_id}`（Docker 内）或 `http://127.0.0.1:9000/...`（本机全本地）
- `DOUYIN_HTTP_FEED_URL=http://bridge:9000/douyin/feed?sec_uid={sec_uid}&cursor={cursor}`

## 说明

- 部分抖音号在 Web 端路径可能与 `https://www.douyin.com/user/{unique_id}` 不一致；若 `resolve` 失败，需在上游支持的前提下扩展桥接的 URL 拼装规则。
- 合规与风控由上游与使用者自行负责。
