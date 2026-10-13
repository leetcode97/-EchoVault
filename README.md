# 🏆 EchoVault

自托管个人音乐播放器：只播放你自己保存在本地的音乐文件，不依赖任何厂商曲库，天然无版权问题。手机（Android/iOS 浏览器）与电脑（Windows/macOS/Linux）多端访问，PWA 可添加到主屏幕获得类 App 体验。

## 功能

- 自动扫描音乐目录（mp3 / flac / m4a / aac / ogg / opus / wav）
- 读取 ID3/内嵌标签：标题、歌手、专辑、年份、流派、时长、封面
- 全部歌曲 / 专辑 / 歌手 三种视图 + 全局搜索
- 播放队列、进度拖动（HTTP Range）、倍速、音量记忆
- Android 锁屏媒体控制（Media Session）
- PWA：离线壳 + 添加到主屏幕

## 快速开始（Windows）

```powershell
cd "D:\CodeProjects\🏆 EchoVault"
.\run.ps1
```

脚本会自动创建虚拟环境、安装依赖并启动服务，浏览器打开 `http://localhost:8000`。

也可以手动执行：

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r server\requirements.txt
.\.venv\Scripts\python -m uvicorn server.app:app --host 0.0.0.0 --port 8000
```

## 配置音乐目录

编辑 `config.json`：

```json
{
  "music_dir": "music",
  "host": "0.0.0.0",
  "port": 8000
}
```

- `music_dir`：音乐文件夹路径，相对路径基于项目根目录，也支持绝对路径（如 `"D:\\Music"`）
- `host`：`0.0.0.0` 表示允许局域网/公网访问；只想本机访问可改 `127.0.0.1`

放入新音乐后，页面空态处或重新扫描按钮即可刷新曲库。

## 多端访问

| 场景 | 访问方式 | 说明 |
| --- | --- | --- |
| 本机电脑 | `http://localhost:8000` | 最快 |
| 手机（同一 WiFi） | `http://<电脑局域网IP>:8000` | 查看 IP：`ipconfig`，注意需放行 Windows 防火墙 8000 端口 |
| 出门在外（随时访问） | 云服务器 / Tailscale | 见下文 |

放行防火墙（管理员 PowerShell）：

```powershell
netsh advfirewall firewall add rule name="EchoVault" dir=in action=allow protocol=TCP localport=8000
```

## 部署到云服务器（随时随地访问）

音乐文件建议**不要**提交到 GitHub（体积大且有版权风险），代码提交、音乐用 rsync/scp 单独同步。

### 方式一：Docker（推荐）

```bash
# 服务器上
git clone <你的仓库> echovault && cd echovault
# 把音乐传到服务器并挂载
docker compose up -d
```

`docker-compose.yml` 默认把宿主机 `/srv/echovault/music` 挂载为音乐目录（可用环境变量 `MUSIC_DIR` 覆盖，挂载点在容器内 `/data/music`）。

### 方式二：裸机 systemd

```bash
pip install -r server/requirements.txt
nohup .venv/bin/python -m uvicorn server.app:app --host 0.0.0.0 --port 8000 &
```

配合 Nginx 反代 + HTTPS（建议，移动端 PWA 与锁屏控制更稳）。

### 方式三：Tailscale 组网（免费，电脑不关机时用）

手机与电脑都装 Tailscale，组网后手机直接访问 `http://<电脑TailscaleIP>:8000`，无需公网服务器，安全性高。

## API 一览

| 接口 | 说明 |
| --- | --- |
| `GET /api/library?q=` | 曲库列表（支持搜索） |
| `GET /api/albums` | 按专辑分组 |
| `GET /api/artists` | 按歌手分组 |
| `GET /api/stats` | 曲库统计 |
| `GET /api/cover/{id}` | 封面图 |
| `GET /api/stream/{id}` | 音频流（支持 Range 拖动） |
| `POST /api/rescan` | 重新扫描曲库 |

## 目录结构

```
EchoVault/
├── server/          # FastAPI 后端
│   ├── app.py       # 路由与静态服务
│   ├── scanner.py   # 扫描 + 标签/封面提取 + 缓存
│   └── requirements.txt
├── web/             # 前端 PWA
│   ├── index.html   ├── app.js  ├── style.css
│   ├── manifest.json ├── sw.js  └── icons/
├── music/           # 你的音乐（不入 git）
├── config.json      # 配置
├── run.ps1          # Windows 一键启动
├── Dockerfile / docker-compose.yml
└── .gitignore
```

## 路线图

- [x] 曲库扫描 / 元数据 / 封面 / 流式播放
- [x] 搜索 / 专辑 / 歌手 / 播放队列 / 倍速 / Media Session
- [ ] 歌单持久化（数据库）
- [ ] 歌词（LRC）显示
- [ ] 收听统计与智能推荐
- [ ] 移动端更好用的底部导航（PWA 打磨）
