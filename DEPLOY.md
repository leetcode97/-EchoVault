# EchoVault 服务器部署指南（Linux + Docker）

> 音乐文件**永不进 Git**（`.gitignore` 已锁定），服务器上的音乐只存在于挂载目录。

## 一、服务器准备

- 系统：Ubuntu 22.04 / Debian 12（或同类 Linux）
- 安装 Docker 与 Compose 插件：

```bash
curl -fsSL https://get.docker.com | sh
docker --version          # 验证
docker compose version    # 验证 Compose v2
```

- 云服务商**安全组放行 8000 端口**（或之后用 Nginx 反代到 80/443）

## 二、部署（一次性）

```bash
# 1. 拉代码（仓库设为 private）
git clone <你的GitHub仓库地址> echovault
cd echovault

# 2. 构建镜像并后台启动（restart: unless-stopped，重启自愈）
docker compose up -d --build

# 3. 验证
curl http://localhost:8000/api/stats     # 返回 {"tracks":0,...} 即成功
docker compose ps                        # echovault 应为 Up 状态
```

## 三、传音乐（首次迁移）

- 服务器音乐目录：`/srv/echovault/music`（`docker-compose.yml` 已挂载，容器只读）
- 本地 Windows → 服务器，推荐 rsync（增量、断点续传）：

```bash
# 本地（Git Bash / WSL 里执行）
rsync -avP ./music/ 用户名@服务器IP:/srv/echovault/music/
```

- 或用宝塔面板 / WinSCP 手动上传
- **传完 20 秒内 EchoVault 自动扫描，无需重启**

## 四、日常操作

| 场景 | 命令 |
|---|---|
| 改代码 | 本地 `git push` → 服务器 `git pull` → `docker compose up -d --build` |
| 加新歌 | 直接传进 `/srv/echovault/music`，自动生效 |
| 看日志 | `docker compose logs -f echovault` |
| 暂停服务 | `docker compose down`（数据保留） |
| 彻底重置 | `docker compose down -v`（连缓存一起删，慎用） |
| 备份恢复 | 音乐在 `/srv/echovault/music`，整个目录拷走/拷回即可 |

## 五、安全（强烈建议，按需选做）

1. **访问密码**：EchoVault 目前无内置鉴权，公网 8000 任何人可访问
   - 方案 A（推荐）：**Tailscale 组网**，只允许你自己的设备访问（免费，无需域名）
   - 方案 B：Nginx 反代 + 域名 + HTTPS + BasicAuth
2. **PWA 安装**：手机"添加到主屏幕"要求 HTTPS（`localhost` 除外）——长期使用建议域名 + HTTPS
3. **备份**：音乐是服务器上的唯一副本，定期 `rsync` 回本地或同步到对象存储

## 六、常见问题

- **端口冲突**：`docker compose down` 后重试
- **传歌很慢**：检查服务器带宽与安全组入站规则
- **曲库没刷新**：确认文件确实在 `/srv/echovault/music`（不是别处），等待 20 秒或调用 `POST /api/rescan`
