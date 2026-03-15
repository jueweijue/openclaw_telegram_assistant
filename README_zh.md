# OpenClaw Telegram Assistant 🐰

> 🌐 **[English](./README.md)** | 中文

---

一个轻量、安全的 Telegram Bot，让你在 Telegram 里直接执行服务器 Shell 命令，并内置 OpenClaw Gateway 管理快捷操作。

## ✨ 功能特性

### 🖥️ Shell 命令执行
- 在 Telegram 中发送消息即执行 Shell 命令，结果以代码块格式返回
- **cd 持久化** — 切换目录后多次命令共享同一工作目录，不用反复 `cd`
- **超时保护** — 命令超时自动终止（默认 30s，可配置），防止进程卡死
- **进程组清理** — 超时后 SIGTERM → SIGKILL 逐步清理，不残留僵尸进程

### 🛡️ 安全机制
- **用户白名单** — 仅允许指定 user_id 操作，未配置时拒绝所有访问
- **交互式命令拦截** — 自动识别并拦截需要终端交互的命令（`vim`、`htop`、`ssh`、`tail -f` 等），并给出替代建议
- **REPL 命令增强检测** — `python3`、`node` 等必须带 `-c`/脚本文件参数才能执行，防止进入交互模式
- **路径注入防护** — 使用 `shlex.quote` 处理工作目录路径

### ⚡ 智能辅助
- **命令自动修正** — `top -b` → `top -bn1`，自动补全 batch 模式参数
- **交互命令替代提示** — `vim` → 用 `cat` 读取 / `sed` 编辑，`less` → `cat` 等
- **OpenClaw 快捷菜单** — Telegram 输入框左侧内置 `/openclaw_start`、`/openclaw_stop`、`/openclaw_restart` 快捷按钮

### 🔧 OpenClaw 集成
- 内置 `/openclaw_start`、`/openclaw_stop`、`/openclaw_restart` 命令
- 一键管理 OpenClaw Gateway，无需 SSH 登录

## 📦 安装

```bash
# 1. 克隆仓库
git clone https://github.com/zaineye/openclaw_telegram_assistant.git
cd openclaw_telegram_assistant

# 2. 安装依赖（仅需 requests）
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

```bash
# 复制服务文件
sudo cp openclaw-telegram-assistant.service /etc/systemd/system/

# 重载 & 启动
sudo systemctl daemon-reload
sudo systemctl enable --now openclaw-telegram-assistant

# 查看状态
sudo systemctl status openclaw-telegram-assistant

# 查看日志
sudo journalctl -u openclaw-telegram-assistant -f
```

## 📖 使用示例

| 发送 | 说明 |
|------|------|
| `ls -la` | 列出当前目录 |
| `cd /var/log` | 切换到 /var/log（持久化） |
| `pwd` | 返回 `/var/log` |
| `top -bn1 \| head -10` | 查看 CPU 占用前 10 的进程 |
| `/cwd` | 查看当前工作目录 |
| `/help` | 查看帮助 |
| `/openclaw_restart` | 重启 OpenClaw Gateway |

### 被拦截的命令示例

| 发送 | 结果 |
|------|------|
| `vim test.txt` | ⚠️ 拦截，提示用 `cat` / `sed` |
| `htop` | ⚠️ 拦截，提示用 `top -bn1 \| head -20` |
| `tail -f /var/log/syslog` | ⚠️ 拦截，提示用 `tail -n 50` |
| `python3` | ⚠️ 拦截，提示传入 `-c` 或脚本文件 |

## 📂 项目结构

```
├── bot.py                              # 核心逻辑
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
- 建议在服务器防火墙限制 SSH 访问，Bot 本身不暴露端口
- `ALLOWED_USER` 务必设置为你的 User ID，不要留 0 用于生产环境

## 📄 License

MIT
