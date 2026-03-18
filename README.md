# OpenClaw Telegram Assistant 🐰

> 🌐 English | **[中文](./README_zh.md)**

---

A lightweight, secure Telegram Bot that lets you execute server shell commands directly in Telegram, with built-in OpenClaw Gateway management, multi-host control, and API management.

## ✨ Features

### 🖥️ Shell Command Execution
- Execute shell commands by sending messages in Telegram, results returned in code block format
- **Persistent `cd`** — directory changes persist across commands per host
- **Timeout protection** — commands automatically terminated after timeout (default 30s)
- **Process group cleanup** — graceful SIGTERM → SIGKILL escalation, no zombie processes

### 🖥️ Multi-Host Control
- **Host registry** — add remote servers via interactive wizard (`/addhost`)
- **Tap to switch** — `/hosts` shows all hosts as buttons, tap to switch active host
- **Independent working directories** — each host maintains its own persistent cwd
- **SSH connection pooling** — connections auto-reused and auto-reconnected on failure
- **Key & password auth** — supports both SSH key file and password authentication
- **Connection test on add** — new hosts are tested before being saved
- **Per-host config path** — each host can have its own OpenClaw config path

### 🤖 API Management
- **Add API** — interactive wizard to add OpenAI-compatible API providers
  - Auto-detect protocol (openai-completions / openai-responses)
  - Fetch models from `/models` endpoint
  - Select models with paginated buttons (6 per page)
  - Manual model input for custom models
  - Existing provider detection — skip URL/key input, merge new models
- **Delete API** — delete entire provider or individual models
  - Delete entire provider with default model fallback
  - Delete individual models with multi-select buttons
  - Auto-cleanup of defaults.models references
- **Remote config** — writes config to the active host via SSH

### 🛡️ Security
- **User whitelist** — only specified `user_id` can operate; all access denied when unconfigured
- **Interactive command interception** — auto-detects and blocks commands requiring a terminal (`vim`, `htop`, `ssh`, `tail -f`, etc.) with alternative suggestions
- **REPL command detection** — `python3`, `node`, etc. must include `-c` or a script file
- **Path injection protection** — uses `shlex.quote` to sanitize paths

### ⚡ Smart Assistance
- **Auto-correction** — `top -b` → `top -bn1`
- **Interactive command alternatives** — `vim` → `cat`/`sed`, `less` → `cat`, etc.
- **Gateway restart feedback** — shows success/failure after restart

### 🌐 Multi-language (i18n)
- **Bilingual** — full Chinese and English support
- **Per-user preference** — each user chooses their own language, persisted across restarts
- **Easy switching** — `/lang zh` or `/lang en`

### 🔧 OpenClaw Integration
- Built-in `/openclaw_start`, `/openclaw_stop`, `/openclaw_restart` commands
- Commands follow the active host — manage OpenClaw on any connected machine

## 📦 Installation

```bash
git clone https://github.com/jueweijue/openclaw_telegram_assistant.git
cd openclaw_telegram_assistant

pip3 install -r requirements.txt

cp .env.example .env
# Edit .env, fill in your BOT_TOKEN and ALLOWED_USER

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
sudo cp openclaw-telegram-assistant.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now openclaw-telegram-assistant
sudo systemctl status openclaw-telegram-assistant
sudo journalctl -u openclaw-telegram-assistant -f
```

## 📖 Usage Examples

### Basic Commands

| Send | Description |
|------|-------------|
| `ls -la` | List current directory |
| `cd /var/log` | Change to /var/log (persistent) |
| `pwd` | Returns `/var/log` |
| `top -bn1 \| head -10` | Show top 10 CPU-consuming processes |
| `/cwd` | View current working directory |
| `/lang` | View / switch language |
| `/help` | View help |
| `/cancel` | Exit interactive wizard |

### Multi-Host Commands

| Send | Description |
|------|-------------|
| `/hosts` | List all hosts (tap a button to switch) |
| `/addhost` | Add a new host (interactive wizard, tests connection) |
| `/delhost <name>` | Remove a host |
| `/disconnect` | Disconnect all SSH sessions |

### API Management

| Send | Description |
|------|-------------|
| `/api` | Open API management menu |
| ➕ 添加API | Add API provider (interactive wizard) |
| 🗑️ 删除API | Delete provider or individual models |

### OpenClaw Commands

| Send | Description |
|------|-------------|
| `/openclaw_start` | Start OpenClaw Gateway (on active host) |
| `/openclaw_stop` | Stop OpenClaw Gateway (on active host) |
| `/openclaw_restart` | Restart OpenClaw Gateway (on active host) |

### Intercepted Commands

| Send | Result |
|------|--------|
| `vim test.txt` | ⚠️ Suggests `cat` / `sed` |
| `htop` | ⚠️ Suggests `top -bn1 \| head -20` |
| `tail -f /var/log/syslog` | ⚠️ Suggests `tail -n 50` |
| `python3` | ⚠️ Suggests `-c` or a script file |

## 📂 Project Structure

```
├── bot.py                              # Main entry, message routing, all commands
├── executor.py                         # Local/remote executor, SSH connection pool
├── hosts.py                            # Host registry management
├── hosts.json                          # Host config (auto-generated, gitignored)
├── run.sh                              # Startup script
├── openclaw-telegram-assistant.service  # systemd service file
├── requirements.txt                    # Python dependencies
├── .env.example                        # Environment variable template
├── .gitignore                          # Git ignore rules
├── README.md                           # This file
└── README_zh.md                        # Chinese README
```

## ⚠️ Security Notes

- The `.env` file contains your Bot Token — **never commit it**
- `hosts.json` may contain passwords — **never commit it**
- Restrict SSH access via firewall; the Bot itself does not expose any ports
- Always set `ALLOWED_USER` to your User ID in production

## 📄 License

MIT
