# 部署与运维手册

## 使用界面
部署后访问 `http://localhost:8000/` 打开轻量管理界面，API 文档位于 `/docs`。界面使用当前会话内存中的个人 Token，不应在公共终端上使用。

## 部署前
- Docker Engine 与 Docker Compose 插件。
- 为 `DAEP_ADMIN_TOKEN` 和 `DAEP_WORKER_TOKEN` 分别生成独立随机密钥（至少 32 字节）；不要提交 `.env`。
- `DAEP_WORKER_TOKEN` 必须同时配置在 API 与 Worker 服务中，不能与管理员 Token 复用。
- 配置可信反向代理并启用 TLS；限制 API 暴露范围。

## 部署
```bash
cp .env.example .env
# 编辑 .env
docker compose -f docker-compose.rc6.yaml up --build -d
docker compose -f docker-compose.rc6.yaml ps
 curl http://localhost:8000/health
```

## 查看日志
```bash
docker compose -f docker-compose.rc6.yaml logs -f daep-api
```

## 备份与恢复（SQLite 基线）
```bash
docker compose -f docker-compose.rc6.yaml stop daep-api
docker run --rm -v daep-enterprise-release_daep-data:/data -v "$PWD/backup:/backup" alpine sh -c 'cp /data/daep.db /backup/daep.db'
docker compose -f docker-compose.rc6.yaml start daep-api
```
恢复前停止服务，将备份文件覆盖到数据卷中的 `/data/daep.db`，再启动服务。生产环境应迁移 PostgreSQL 并采用经验证的在线备份与恢复流程。

## 升级
1. 备份数据库和环境配置。
2. 固定镜像 Tag 与代码 Commit。
3. 在预生产环境执行升级与回归测试。
4. 生产执行 `docker compose pull`（若使用镜像仓库）或 `docker compose build`，再 `up -d`。
5. 检查 `/health`、日志、关键业务 API。

## 故障处理
- 401：检查 Bearer Token 和环境变量。
- 数据目录不可写：检查 Docker volume 权限。
- 容器反复重启：查看 `docker compose logs`。
- 不可直接删除数据库文件；先停服务并备份。
