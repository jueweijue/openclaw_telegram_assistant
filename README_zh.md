# OpenClaw Telegram Assistant 🐰

> 🌐 **[English](./README.md)** | 中文

---

一个轻量、安全的 Telegram Bot，让你在 Telegram 里直接执行服务器 Shell 命令，内置 OpenClaw Gateway 管理快捷操作，并支持**多主机控制**。

## ✨ 功能特性

### 🖥️ Shell 命令执行
- 在 Telegram 中发送消息即执行 Shell 命令，结果以代码块格式返回
- **cd 持久化** — 切换目录后多次命令共享同一工作目录（每台主机独立）
- **超时保护** — 命令超时自动终止（默认 30s，可配置）
- **进程组清理** — 超时后 SIGTERM → SIGKILL 逐步清理，不残留僵尸进程

### 🖥️ 多主机控制
- **主机注册** — 通过 `/addhost` 交互式添加远程服务器（SSH 连接），自动测试连通性
- **点击切换** — `/hosts` 以按钮形式展示所有主机，点击即可切换活跃主机
- **独立工作目录** — 每台主机维护独立的持久化 cwd
- **连接池** — SSH 连接自动重用，断线自动重连
- **密钥/密码认证** — 支持 SSH 密钥文件和密码两种认证方式
- **添加时测试** — 新主机在保存前会先测试 SSH 连接

### 🛡️ 安全机制
- **用户白名单** — 仅允许指定 user_id 操作，未配置时拒绝所有访问
- **交互式命令拦截** — 自动识别并拦截需要终端交互的命令（`vim`、`htop`、`ssh`、`tail -f` 等），并给出替代建议
- **REPL 命令增强检测** — `python3`、`node` 等必须带 `-c`/脚本文件参数才能执行
- **路径注入防护** — 使用 `shlex.quote` 处理工作目录路径

### ⚡ 智能辅助
- **命令自动修正** — `top -b` → `top -bn1`，自动补全 batch 模式参数
- **交互命令替代提示** — `vim` → 用 `cat` 读取 / `sed` 编辑，`less` → `cat` 等

### 🌐 多语言支持 (i18n)
- **中英双语** — 所有用户可见的提示信息均支持中文和英文
- **独立语言偏好** — 每个用户可单独选择语言，重启后自动保持
- **快捷切换** — 发送 `/lang zh` 或 `/lang en` 即可即时切换

### 🔧 OpenClaw 集成
- 内置 `/openclaw_start`、`/openclaw_stop`、`/openclaw_restart` 命令
- 命令跟随活跃主机 — 可在任意已连接的机器上管理 OpenClaw

## 📦 安装

```bash
# 1. 克隆仓库
git clone https://github.com/jueweijue/openclaw_telegram_assistant.git
cd openclaw_telegram_assistant

# 2. 安装依赖
pip3 install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的 BOT_TOKEN 和 ALLOWED_USER

# 4. 启动
bash run.sh
```

## 🔑 配置

编辑 `.env` 文件：

| 变量 | 必填 | 说明 | 默认值 |
|------|------|------|--------|
| `BOT_TOKEN` | ✅ | Telegram Bot Token（从 @BotFather 获取） | — |
| `ALLOWED_USER` | ⚠️ | 允许使用 Bot 的 Telegram User ID（留 0 = 拒绝所有人） | `0` |
| `CMD_TIMEOUT` | ❌ | 命令超时秒数 | `30` |

### 获取 Bot Token

1. 在 Telegram 找 [@BotFather](https://t.me/BotFather)
2. 发送 `/newbot`，按提示创建
3. 复制 token 填入 `.env`

### 获取 User ID

1. 在 Telegram 找 [@userinfobot](https://t.me/userinfobot)
2. 发送任意消息，它会返回你的 user ID

## 🚀 作为 systemd 服务运行

先编辑 `openclaw-telegram-assistant.service`，将 `/path/to/project` 替换为你的实际项目目录：

```ini
WorkingDirectory=/path/to/project/openclaw_telegram_assistant
EnvironmentFile=/path/to/project/openclaw_telegram_assistant/.env
ExecStart=/usr/bin/python3 /path/to/project/openclaw_telegram_assistant/bot.py
```

然后执行：

```bash
sudo cp openclaw-telegram-assistant.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now openclaw-telegram-assistant
sudo systemctl status openclaw-telegram-assistant
sudo journalctl -u openclaw-telegram-assistant -f
```

## 📖 使用示例

### 基本命令

| 发送 | 说明 |
|------|------|
| `ls -la` | 列出当前目录 |
| `cd /var/log` | 切换到 /var/log（持久化） |
| `pwd` | 返回 `/var/log` |
| `top -bn1 \| head -10` | 查看 CPU 占用前 10 的进程 |
| `/cwd` | 查看当前工作目录 |
| `/lang` | 查看/切换语言 |
| `/help` | 查看帮助 |

### 多主机命令

| 发送 | 说明 |
|------|------|
| `/hosts` | 查看所有主机（点击按钮切换） |
| `/addhost` | 交互式添加新主机（自动测试连接） |
| `/delhost <name>` | 删除主机 |
| `/disconnect` | 断开所有 SSH 连接 |
| `/cancel` | 退出交互式流程 |

### OpenClaw 命令

| 发送 | 说明 |
|------|------|
| `/openclaw_start` | 启动 OpenClaw Gateway（在当前活跃主机上） |
| `/openclaw_stop` | 停止 OpenClaw Gateway（在当前活跃主机上） |
| `/openclaw_restart` | 重启 OpenClaw Gateway（在当前活跃主机上） |

### 被拦截的命令示例

| 发送 | 结果 |
|------|------|
| `vim test.txt` | ⚠️ 拦截，提示用 `cat` / `sed` |
| `htop` | ⚠️ 拦截，提示用 `top -bn1 \| head -20` |
| `tail -f /var/log/syslog` | ⚠️ 拦截，提示用 `tail -n 50` |
| `python3` | ⚠️ 拦截，提示传入 `-c` 或脚本文件 |

## 📂 项目结构

```
├── bot.py                              # 主入口 + 消息路由 + 命令处理
├── executor.py                         # 本地/远程执行器 + SSH 连接池
├── hosts.py                            # 主机注册表管理
├── hosts.json                          # 主机配置（自动生成，不提交）
├── run.sh                              # 启动脚本
├── openclaw-telegram-assistant.service  # systemd 服务文件
├── requirements.txt                    # Python 依赖
├── .env.example                        # 环境变量模板
├── .gitignore                          # Git 忽略规则
├── README.md                           # English README
└── README_zh.md                        # 本文件
```

## ⚠️ 安全提醒

- `.env` 文件包含 Bot Token，**绝对不要提交到版本库**
- `hosts.json` 可能包含密码，**绝对不要提交到版本库**
- 建议在服务器防火墙限制 SSH 访问，Bot 本身不暴露端口
- `ALLOWED_USER` 务必设置为你的 User ID，不要留 0 用于生产环境

## 📄 License

MIT
