# EchoVault 服务器部署指南

> 目标：让 EchoVault 在云服务器上 7×24 小时运行，手机、电脑随时随地访问。
> 本文档是**照着抄**的手册：从买服务器到传歌到日常维护，每一步都给可执行命令。

---

## 〇、整体架构：代码与音乐是两条路

```
代码线（自动更新）          音乐线（手动上传）
┌─────────────────┐        ┌──────────────────────┐
│ GitHub（只存代码）│        │ 你的电脑（音乐库）     │
│ 不含任何音乐文件  │        │ music\ 里的所有歌     │
└────────┬────────┘        └──────────┬───────────┘
         │ git clone（服务器拉取）       │ rsync（手动上传）
         ▼                             ▼
┌───────────────────────────────────────────────┐
│              云服务器（Linux + Docker）          │
│  ┌─────────────────────┐   ┌─────────────────┐ │
│  │ 🐳 容器 = 代码       │   │ 💾 硬盘 = 音乐   │ │
│  │（git 拉下来构建的）   │   │ ~/echovault/ │ │
│  │                     │←挂载→│    music       │ │
│  └─────────────────────┘   └─────────────────┘ │
└───────────────────────────────────────────────┘
```

**核心规则：GitHub 只负责"程序"，你负责"歌"。** 公开仓库里永远不会出现你的音乐。

---

## 一、购买服务器

| 项目 | 推荐 | 说明 |
| --- | --- | --- |
| 产品 | 轻量应用服务器（阿里云/腾讯云） | 新用户常有优惠 |
| 配置 | 2核2G 起步 | EchoVault 单服务仅占约 300MB 内存，2G 还能跑别的服务 |
| 系统 | Ubuntu 22.04 或 Debian 12 | Docker 支持最好 |
| 磁盘 | 40GB+（默认够装 3000+ 首歌） | 1 首约 5MB |
| 地域 | 国内节点 | 自用无差别 |

---

## 二、服务器初始化（一次性，约 5 分钟）

### 1. 登录服务器

```bash
ssh root@服务器IP
```

> 用户名默认 `root`（提示符形如 `root@srv-xxxxxx:~#`，`srv-xxxxxx` 是主机名，不用管）。

### 2. 安装 Docker 与 Compose

```bash
curl -fsSL https://get.docker.com | sh
docker --version          # 验证：应显示版本号
docker compose version    # 验证：应显示 v2 版本号
```

### 3. 配置国内加速（国内服务器必做，否则构建要十几分钟）

**① Docker 镜像加速**（解决基础镜像从 Docker Hub 拉取慢）：

```bash
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json > /dev/null <<'EOF'
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://dockerproxy.com",
    "https://docker.1panel.live"
  ]
}
EOF
sudo systemctl restart docker
```

> 阿里云/腾讯云服务器也可用各自的专属加速地址（控制台有），效果更稳。

**② pip 镜像**：Dockerfile 已内置**阿里云 PyPI 镜像源**（阿里云服务器内网访问最快），无需手动配置。

### 4. 放行端口

- **云服务商控制台**：安全组 / 防火墙规则，放行 TCP **8848** 端口（如果之后用域名+HTTPS，再放行 80/443 并反代）
- **服务器系统防火墙**（如有开启）：

```bash
sudo ufw allow 8848/tcp
```

---

## 三、部署 EchoVault（一次性，约 3 分钟）

```bash
# 1. 拉代码（里面没有音乐，这是正常的）
git clone https://github.com/leetcode97/-EchoVault.git echovault
cd echovault

# 2. 创建音乐文件夹（就在项目里面，以后传歌都传这）
mkdir -p music

# 3. 构建镜像并后台启动（崩溃/重启自动拉起）
docker compose up -d --build

# 4. 验证服务在线
curl http://localhost:8848/api/stats
# 应返回类似：{"tracks":0,"albums":0,...}（此时还没传歌）

docker compose ps         # echovault 状态应为 Up
```

> 第一次 `up -d --build` 要下载基础镜像，视网络 1–5 分钟。

---

## 四、上传音乐（首次迁移）

### 音乐到底存哪？（先看懂这句）

歌曲物理上存在**服务器硬盘**的 `~/echovault/music` 文件夹，通过 Docker"挂载"借给容器看（容器内叫 `/data/music`，是**同一份文件，不是复制**）。你往这个文件夹放歌，EchoVault 约 20 秒后自动入库，**无需重启**。

类比：像 U 盘插电脑——文件在 U 盘里，电脑挂载后能打开；拔掉（删容器）文件还在 U 盘。

### Windows 电脑上传，三选一

**方案 A：rsync（推荐，增量/断点续传，适合大批量）**

需要 Git Bash（随 Git 安装自带）或 WSL，在**本地电脑**执行：

```bash
rsync -avP "D:/CodeProjects/🏆 EchoVault/music/" root@服务器IP:~/echovault/music/
```

**方案 B：scp（PowerShell 直接可用，适合少量文件）**

```powershell
scp -r "D:\CodeProjects\🏆 EchoVault\music\*" root@服务器IP:~/echovault/music/
```

**方案 C：宝塔面板 / WinSCP（图形界面）**

登录面板把本地文件拖进 `~/echovault/music/` 即可。

### 传完验证

```bash
curl http://localhost:8848/api/stats    # tracks 应变成你的歌曲数
```

或直接手机/电脑浏览器打开 `http://服务器IP:8848` 看曲库。

---

## 五、日常使用（每天就这几条）

| 场景 | 操作 |
| --- | --- |
| **加新歌** | 往 `~/echovault/music` 传文件即可，20 秒自动入库，什么都不用重启 |
| **改代码/更新版本** | 本地 `git push` → 服务器 `git pull` → `docker compose up -d --build` |
| **看日志** | `docker compose logs -f echovault` |
| **重启服务** | `docker compose restart` |
| **暂停服务** | `docker compose down`（数据保留，随时可再启动） |
| **彻底重置** | `docker compose down -v`（连缓存一起删，慎用） |

---

## 六、安全建议（强烈建议，按需选做）

| 优先级 | 事项 | 做法 |
| --- | --- | --- |
| ⭐⭐⭐ | **访问密码** | EchoVault 目前无内置鉴权，公网 8848 任何人可访问。方案 A：**Tailscale 组网**（免费，只你的设备能连）；方案 B：Nginx 反代 + HTTPS + 账号密码 |
| ⭐⭐⭐ | **备份音乐** | 音乐是服务器上的唯一副本！定期 `rsync -avP root@服务器IP:~/echovault/music/ ./music-backup/` 拉回本地，或同步到网盘/对象存储 |
| ⭐⭐ | **HTTPS（PWA）** | 手机"添加到主屏幕"要求 HTTPS。长期使用建议域名 + 证书（免费证书可申请） |
| ⭐⭐ | **服务器 SSH 安全** | 修改默认 SSH 端口、禁用 root 密码登录改密钥登录（网上教程很多） |

---

## 七、常见问题排查

| 症状 | 原因与解决 |
| --- | --- |
| 端口 8848 被占用 | `docker compose down` 后重试；或 `ss -tlnp | grep 8848` 看谁占着 |
| 传歌很慢 | 检查服务器带宽上限、安全组入站规则；rsync 会自动续传 |
| 曲库没刷新 | 确认文件真的在 `~/echovault/music`；等 20 秒；或 `curl -X POST http://localhost:8848/api/rescan` 手动扫 |
| 手机打不开 | 手机和服务器要在同一网络？——不，手机走公网，确认安全组放行 8848、服务绑定 `0.0.0.0`（配置里默认已是） |
| 服务器重启后服务没了 | 不应发生：`docker compose` 配了 `restart: unless-stopped`；若没有自动拉起，执行 `docker compose up -d` |
| 容器删了歌还在吗 | 在。歌在服务器硬盘 `~/echovault/music`，不在容器里 |
| 从 GitHub 拉的代码没有 music 文件夹 | 正常。音乐永远手动传（见第四节），代码与数据分离是设计 |

---

## 八、附录

### 本地电脑启动（不部署也能用）

```powershell
cd D:\CodeProjects\🏆 EchoVault
.\run.ps1        # 一键启动，浏览器打开 http://localhost:8848
```

### 相关文件

| 文件 | 作用 |
| --- | --- |
| `docker-compose.yml` | 容器编排：端口、音乐挂载、缓存卷 |
| `Dockerfile` | 镜像构建（只打包代码，不含音乐） |
| `config.json` | 本地配置（服务器上由 docker-compose 环境变量覆盖） |
| `.gitignore` | 已锁定 `music/` 与全部音频格式，杜绝版权风险 |
