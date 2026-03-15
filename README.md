# OpenClaw Telegram Assistant 🐰

> 🌐 English | **[中文](./README_zh.md)**

---

A lightweight, secure Telegram Bot that lets you execute server shell commands directly in Telegram, with built-in OpenClaw Gateway management shortcuts.

## ✨ Features

### 🖥️ Shell Command Execution
- Execute shell commands by sending messages in Telegram, results returned in code block format
- **Persistent `cd`** — directory changes persist across commands, no need to repeat `cd`
- **Timeout protection** — commands automatically terminated after timeout (default 30s, configurable), preventing hung processes
- **Process group cleanup** — graceful SIGTERM → SIGKILL escalation after timeout, no zombie processes

### 🛡️ Security
- **User whitelist** — only specified `user_id` can operate; all access denied when unconfigured
- **Interactive command interception** — automatically detects and blocks commands requiring a terminal (`vim`, `htop`, `ssh`, `tail -f`, etc.) with alternative suggestions
- **REPL command detection** — `python3`, `node`, etc. must include `-c` or a script file argument to prevent entering interactive mode
- **Path injection protection** — uses `shlex.quote` to sanitize working directory paths

### ⚡ Smart Assistance
- **Auto-correction** — `top -b` → `top -bn1`, automatically补全 batch mode flags
- **Interactive command alternatives** — `vim` → use `cat` to read / `sed` to edit, `less` → `cat`, etc.
- **OpenClaw shortcut menu** — built-in `/openclaw_start`, `/openclaw_stop`, `/openclaw_restart` commands in the Telegram input menu

### 🔧 OpenClaw Integration
- Built-in `/openclaw_start`, `/openclaw_stop`, `/openclaw_restart` commands
- One-click OpenClaw Gateway management, no SSH needed

## 📦 Installation

```bash
# 1. Clone the repository
git clone https://github.com/jueweijue/openclaw_telegram_assistant.git
cd openclaw_telegram_assistant

# 2. Install dependencies (only requests needed)
pip3 install -r requirements.txt

# 3. Configure environment variables
cp .env.example .env
# Edit .env, fill in your BOT_TOKEN and ALLOWED_USER

# 4. Start
bash run.sh
```

## 🔧 Configuration

Edit the `.env` file:

| Variable | Required | Description | Default |
|----------|----------|-------------|---------|
| `BOT_TOKEN` | ✅ | Telegram Bot Token (from @BotFather) | — |
| `ALLOWED_USER` | ⚠️ | Telegram User ID allowed to use the Bot (0 = deny all) | `0` |
| `CMD_TIMEOUT` | ❌ | Command timeout in seconds | `30` |

### Getting a Bot Token

1. Find [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts
3. Copy the token and paste it into `.env`

### Getting Your User ID

1. Find [@userinfobot](https://t.me/userinfobot) on Telegram
2. Send any message and it will return your user ID

## 🚀 Run as a systemd Service

Edit `openclaw-telegram-assistant.service` and replace `/path/to/project` with your actual project directory:

```ini
WorkingDirectory=/path/to/project/openclaw_telegram_assistant
EnvironmentFile=/path/to/project/openclaw_telegram_assistant/.env
ExecStart=/usr/bin/python3 /path/to/project/openclaw_telegram_assistant/bot.py
```

Then:

```bash
# Copy the service file
sudo cp openclaw-telegram-assistant.service /etc/systemd/system/

# Reload & start
sudo systemctl daemon-reload
sudo systemctl enable --now openclaw-telegram-assistant

# Check status
sudo systemctl status openclaw-telegram-assistant

# View logs
sudo journalctl -u openclaw-telegram-assistant -f
```

## 📖 Usage Examples

| Send | Description |
|------|-------------|
| `ls -la` | List current directory |
| `cd /var/log` | Change to /var/log (persistent) |
| `pwd` | Returns `/var/log` |
| `top -bn1 \| head -10` | Show top 10 CPU-consuming processes |
| `/cwd` | View current working directory |
| `/help` | View help |
| `/openclaw_restart` | Restart OpenClaw Gateway |

### Intercepted Command Examples

| Send | Result |
|------|--------|
| `vim test.txt` | ⚠️ Intercepted, suggests `cat` / `sed` |
| `htop` | ⚠️ Intercepted, suggests `top -bn1 \| head -20` |
| `tail -f /var/log/syslog` | ⚠️ Intercepted, suggests `tail -n 50` |
| `python3` | ⚠️ Intercepted, suggests passing `-c` or a script file |

## 📂 Project Structure

```
├── bot.py                              # Core logic
├── run.sh                              # Startup script
├── openclaw-telegram-assistant.service  # systemd service file
├── requirements.txt                    # Python dependencies
├── .env.example                        # Environment variable template
├── .gitignore                          # Git ignore rules
├── README.md                           # This file (English)
└── README_zh.md                        # Chinese README
```

## ⚠️ Security Notes

- The `.env` file contains your Bot Token — **never commit it to version control**
- It is recommended to restrict SSH access via server firewall; the Bot itself does not expose any ports
- Always set `ALLOWED_USER` to your own User ID; do not leave it as 0 in production

## 📄 License

MIT
