# textloading 生产服务器运维清单（逐项执行、逐项勾选）

> 使用方式：每完成一步，把该行 `- [ ]` 改成 `- [x]`，再执行「下一步」命令。  
> 环境默认：`/opt/textloading`、`/etc/textloading/textloading.env`、`docker compose -f /opt/textloading/docker-compose.yml`。

---

## 阶段 A — 基线确认（建议先做）

- [ ] **A1** — 确认 env 权限为仅 root/运维可读  
  **命令：** `sudo chmod 600 /etc/textloading/textloading.env && ls -la /etc/textloading/textloading.env`

- [ ] **A2** — 确认关键变量（应为：`UVICORN_WORKERS=1`，Redis 走 compose 内服务）  
  **命令：** `grep -E '^(UVICORN_WORKERS|REDIS_URL|DATABASE_URL)=' /etc/textloading/textloading.env | sed 's/:.*/:***masked***/'`

- [ ] **A3** — 确认 `deploy/textloading.env` 指向 `/etc`  
  **命令：** `readlink -f /opt/textloading/deploy/textloading.env`

- [ ] **A4** — 容器与健康检查  
  **命令：** `cd /opt/textloading && docker compose -f /opt/textloading/docker-compose.yml ps && curl -sS http://127.0.0.1:18180/health && curl -sS http://127.0.0.1:18180/ready`

- [ ] **A5** — API / Worker 最近无报错  
  **命令：** `docker compose -f /opt/textloading/docker-compose.yml logs api --tail 30 | tail -5`

---

## 阶段 B — 防火墙与安全组（与统一基建文档一致）

- [ ] **B1** — 核对 UFW：`22/80/443` 放行，`5432/6379` 不对公网（仅内网/Docker 段）  
  **命令：** `sudo ufw status verbose`

- [ ] **B2** —（若尚未添加）Docker 网段访问宿主 Postgres：`172.20.0.0/16 -> 5432`  
  **命令：** `sudo ufw status | grep -q '172.20.0.0/16.*5432' || sudo ufw allow from 172.20.0.0/16 to any port 5432 proto tcp comment 'docker textloading pg'`

- [ ] **B3** —（仅当 `REDIS_URL` 仍指向宿主时才需要）`172.20.0.0/16 -> 6379`  
  **命令：** `grep -q '^REDIS_URL=redis://redis:' /etc/textloading/textloading.env && echo 'Redis 已走 compose，跳过 B3' || sudo ufw allow from 172.20.0.0/16 to any port 6379 proto tcp comment 'docker textloading redis'`

- [ ] **B4** — 重载防火墙  
  **命令：** `sudo ufw reload`

---

## 阶段 C — Docker 服务自愈与校验

- [ ] **C1** — 重建并确保 api / worker / bridge 使用最新 env  
  **命令：** `cd /opt/textloading && docker compose -f /opt/textloading/docker-compose.yml up -d api worker bridge`

- [ ] **C2** —（可选）清理悬空镜像  
  **命令：** `docker image prune -f`

---

## 阶段 D — PostgreSQL 备份（宿主库：textloading_app）

- [ ] **D1** — 备份目录  
  **命令：** `sudo mkdir -p /opt/backups/textloading && sudo chown root:root /opt/backups/textloading`

- [ ] **D2** — 手动试跑一次逻辑备份（把 `<PGPASSWORD>` 换成实际或通过 `.pgpass`）  
  **命令：** `sudo mkdir -p /opt/backups/textloading && PGPASSWORD='<PGPASSWORD>' pg_dump -h 127.0.0.1 -U ab_app -d textloading_app -Fc -f /opt/backups/textloading/textloading_app_$(date +%F_%H%M).dump && ls -lh /opt/backups/textloading | tail -3`

- [ ] **D3** —（可选）每日 cron：由你写入 `crontab -e`，低峰执行 `pg_dump`；保留 14 天策略见 Ab 文档 §5.2

---

## 阶段 E — Nginx / HTTPS（网关）

- [ ] **E1** — 确认对外仅 `80/443`，反代到 `127.0.0.1:18180`，**勿**将 `18180` 开公网  
  **命令：** `sudo nginx -t 2>/dev/null; curl -sSI https://你的域名 2>/dev/null | head -5`

---

## 阶段 F — 后续工程优化（需改代码 / CI，非单行命令）

- [ ] **F1** — 将 `init_db()` 中 DDL/索引迁移移出 API lifespan，便于恢复 **`UVICORN_WORKERS=2`**  
- [ ] **F2** — 为 `api`/`worker` 在 `docker-compose.yml` 中增加 **`cpus` / `mem_limit`**  
- [ ] **F3** — 日志采集（SLS / Loki）与告警规则  

---

## 当前「下一步」建议

若阶段 **A** 尚未全部勾选：从 **A1** 开始依次执行。  
若 **A** 已完成：执行 **B1**，再根据输出决定是否执行 **B2–B4**。
