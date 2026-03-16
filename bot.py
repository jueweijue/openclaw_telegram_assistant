#!/usr/bin/env python3
"""Telegram Shell Bot — receives message → executes command → returns result, with persistent cd"""

import json
import os
import shlex
import signal
import subprocess
import time
import requests

# ── Configuration ────────────────────────────────────────────────────────────
TOKEN        = os.environ["BOT_TOKEN"]
# Safety底线: if not configured, force to 0; all access will be denied
ALLOWED_USER = int(os.environ.get("ALLOWED_USER", "0"))
TIMEOUT      = int(os.environ.get("CMD_TIMEOUT", "30"))
API          = f"https://api.telegram.org/bot{TOKEN}"
CWD_FILE     = "/tmp/tg-shell-bot.cwd"
LANG_FILE    = "/tmp/tg-shell-bot.lang"
# Default directory: current user's home
DEFAULT_CWD  = os.path.expanduser("~")

# ── i18n ─────────────────────────────────────────────────────────────────────
SUPPORTED_LANGS = ("zh", "en")

TRANSLATIONS: dict[str, dict[str, str]] = {
    "zh": {
        "unauthorized":         "⛔ 未授权访问",
        "unknown_command":      "未知命令，发送 /help 查看用法",
        "interactive_blocked":  "⚠️ 交互式命令已被拦截\n\n{suggestion}",
        "auto_corrected":       "💡 自动修正: {cmd}",
        "current_dir":          "📂 当前目录: {dir}",
        "dir_not_found":        "❌ 目录不存在或无权限: {dir}",
        "cd_not_supported":     "⚠️ cd - 不支持（无 OLDPWD）",
        "cmd_timeout":          "❌ 命令超时，已终止（>{timeout}s）",
        "cmd_error":            "❌ 错误: {error}",
        "cmd_prefix":           "[{cwd}] $ {cmd}",
        "exit_code":            "[exit code: {code}]",
        "help_text":            (
            "发送命令即可执行，cd 切换目录（持久化）\n"
            "/cwd  — 查看当前目录\n"
            "/lang — 切换语言 (zh/en)\n"
            "/help — 帮助\n\n"
            "💡 底部菜单有 OpenClaw 快捷按钮"
        ),
        "lang_current":         "🌐 当前语言: {lang}",
        "lang_set":             "🌐 语言已切换为: {lang}",
        "lang_invalid":         "⚠️ 不支持的语言，请使用 /lang zh 或 /lang en",
        "lang_usage":           "📝 切换语言: /lang zh（中文）  |  /lang en（English）",
        "lang_zh":              "中文",
        "lang_en":              "English",
        "openclaw_start":       "⏳ 正在启动 OpenClaw Gateway...",
        "openclaw_stop":        "⏳ 正在停止 OpenClaw Gateway...",
        "openclaw_restart":     "⏳ 正在重启 OpenClaw Gateway...",
        "openclaw_start_label": "▶️ 启动 OpenClaw",
        "openclaw_stop_label":  "⏹ 停止 OpenClaw",
        "openclaw_restart_label":"🔄 重启 OpenClaw",
        "menu_cwd":             "📂 查看当前目录",
        "menu_help":            "📖 查看帮助",
        "menu_lang":            "🌐 切换语言",
        "bot_starting":         "🐰 Telegram Shell Bot 启动中...",
        "bot_workdir":          "📂 工作目录: {dir}",
        "bot_no_user":          "⚠️ 警告: ALLOWED_USER 未配置，所有访问将被拒绝！",
        "menu_registered":      "✅ Telegram 快捷菜单已注册！",
        "menu_failed":          "⚠️ Telegram 菜单注册失败: {error}",
        # Interactive hint templates
        "hint_tail_f":          "tail -f → tail -n 50 <file>",
        "hint_htop":            "htop → top -bn1 | head -20",
        "hint_less":            "less → cat <file>",
        "hint_more":            "more → cat <file>",
        "hint_vim":             "vim → 用 cat 读取，sed / echo '>' 编辑",
        "hint_nano":            "nano → 用 cat 读取，sed / echo '>' 编辑",
        "hint_watch":           "watch → while true; do <cmd>; sleep 2; done",
        "hint_tmux":            "tmux 是终端复用器，此处不可用",
        "hint_screen":          "screen 是终端复用器，此处不可用",
        "hint_ssh":             "ssh 需要交互式终端，此处不可用",
        "hint_su":              "su 需要交互式终端，请用 sudo <command> 代替",
        "hint_irb":             "irb → ruby -e \"code\"",
        "hint_top":             "top (交互模式) → 建议使用 {flag}",
        "hint_man":             "man (交互模式) → 建议使用 man {flag} <command>",
        "hint_repl":            "{cmd} 交互模式不可用，请提供脚本文件或 -e/-c 参数",
        "no_output":            "(无输出)",
    },
    "en": {
        "unauthorized":         "⛔ Unauthorized",
        "unknown_command":      "Unknown command, send /help for usage",
        "interactive_blocked":  "⚠️ Interactive command blocked\n\n{suggestion}",
        "auto_corrected":       "💡 Auto-corrected: {cmd}",
        "current_dir":          "📂 Current directory: {dir}",
        "dir_not_found":        "❌ Directory does not exist or no permission: {dir}",
        "cd_not_supported":     "⚠️ cd - not supported (no OLDPWD)",
        "cmd_timeout":          "❌ Command timed out, terminated (>{timeout}s)",
        "cmd_error":            "❌ Error: {error}",
        "cmd_prefix":           "[{cwd}] $ {cmd}",
        "exit_code":            "[exit code: {code}]",
        "help_text":            (
            "Send commands to execute, cd changes directory persistently\n"
            "/cwd  — View current directory\n"
            "/lang — Switch language (zh/en)\n"
            "/help — Help\n\n"
            "💡 OpenClaw shortcuts are available in the bottom-left menu"
        ),
        "lang_current":         "🌐 Current language: {lang}",
        "lang_set":             "🌐 Language switched to: {lang}",
        "lang_invalid":         "⚠️ Unsupported language, use /lang zh or /lang en",
        "lang_usage":           "📝 Switch language: /lang zh（中文）  |  /lang en（English）",
        "lang_zh":              "中文",
        "lang_en":              "English",
        "openclaw_start":       "⏳ Starting OpenClaw Gateway...",
        "openclaw_stop":        "⏳ Stopping OpenClaw Gateway...",
        "openclaw_restart":     "⏳ Restarting OpenClaw Gateway...",
        "openclaw_start_label": "▶️ Start OpenClaw",
        "openclaw_stop_label":  "⏹ Stop OpenClaw",
        "openclaw_restart_label":"🔄 Restart OpenClaw",
        "menu_cwd":             "📂 View current directory",
        "menu_help":            "📖 View help",
        "menu_lang":            "🌐 Switch language",
        "bot_starting":         "🐰 Telegram Shell Bot starting...",
        "bot_workdir":          "📂 Working directory: {dir}",
        "bot_no_user":          "⚠️ Warning: ALLOWED_USER not configured, all access will be denied!",
        "menu_registered":      "✅ Telegram shortcut menu registered!",
        "menu_failed":          "⚠️ Telegram menu registration failed: {error}",
        # Interactive hint templates
        "hint_tail_f":          "tail -f → tail -n 50 <file>",
        "hint_htop":            "htop → top -bn1 | head -20",
        "hint_less":            "less → cat <file>",
        "hint_more":            "more → cat <file>",
        "hint_vim":             "vim → use cat to read, sed / echo '>' to edit",
        "hint_nano":            "nano → use cat to read, sed / echo '>' to edit",
        "hint_watch":           "watch → while true; do <cmd>; sleep 2; done",
        "hint_tmux":            "tmux is a terminal multiplexer, not available here",
        "hint_screen":          "screen is a terminal multiplexer, not available here",
        "hint_ssh":             "ssh requires an interactive terminal, not available here",
        "hint_su":              "su requires an interactive terminal, use sudo <command> instead",
        "hint_irb":             "irb → ruby -e \"code\"",
        "hint_top":             "top (interactive mode) → consider using {flag}",
        "hint_man":             "man (interactive mode) → consider using man {flag} <command>",
        "hint_repl":            "{cmd} interactive mode not available, please provide a script file or -e/-c flag",
        "no_output":            "(no output)",
    },
}

# Default language
DEFAULT_LANG = "en"


def _load_langs() -> dict[int, str]:
    """Load per-user language preferences from file."""
    try:
        with open(LANG_FILE) as f:
            data = json.load(f)
            # Convert string keys back to int
            return {int(k): v for k, v in data.items()}
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def _save_langs(langs: dict[int, str]) -> None:
    """Save per-user language preferences to file."""
    with open(LANG_FILE, "w") as f:
        json.dump(langs, f)


# In-memory language cache
_user_langs: dict[int, str] = _load_langs()


def t(key: str, lang: str) -> str:
    """Translate a key to the given language."""
    return TRANSLATIONS.get(lang, TRANSLATIONS[DEFAULT_LANG]).get(key, key)


def get_user_lang(user_id: int | None) -> str:
    """Get language for a user, falling back to default."""
    if user_id is None:
        return DEFAULT_LANG
    return _user_langs.get(user_id, DEFAULT_LANG)


def set_user_lang(user_id: int, lang: str) -> None:
    """Set language for a user and persist."""
    _user_langs[user_id] = lang
    _save_langs(_user_langs)

# ── Interactive command hint table (translation keys) ────────────────────────
INTERACTIVE_HINT_KEYS: dict[str, str] = {
    "htop":   "hint_htop",
    "less":   "hint_less",
    "more":   "hint_more",
    "vim":    "hint_vim",
    "vi":     "hint_vim",
    "nano":   "hint_nano",
    "watch":  "hint_watch",
    "tmux":   "hint_tmux",
    "screen": "hint_screen",
    "ssh":    "hint_ssh",
    "su":     "hint_su",
    "irb":    "hint_irb",
}

# Commands that need extra flags to run non-interactively
BATCH_FLAGS: dict[str, str] = {
    "top": "-bn1",
    "man": "-P cat",
}

# Commands that enter interactive REPL without arguments
REPL_CMDS = {"python", "python3", "node", "mysql", "psql", "ruby", "lua"}


# ── Working directory persistence ────────────────────────────────────────────
def _init_cwd() -> None:
    if not os.path.exists(CWD_FILE):
        _write_cwd(DEFAULT_CWD)

def _read_cwd() -> str:
    try:
        return open(CWD_FILE).read().strip() or DEFAULT_CWD
    except OSError:
        return DEFAULT_CWD

def _write_cwd(path: str) -> None:
    with open(CWD_FILE, "w") as f:
        f.write(path)


# ── Interactive command detection ────────────────────────────────────────────
def check_interactive(cmd: str, lang: str = DEFAULT_LANG) -> str | None:
    """Returns a friendly hint if the command requires an interactive terminal; otherwise None."""
    parts = cmd.split()
    if not parts:
        return None

    cmd_name = os.path.basename(parts[0])

    # tail -f detection
    if cmd_name == "tail" and any(f in parts for f in ("-f", "--follow", "-F")):
        return t("hint_tail_f", lang)

    # Detect pager/editor commands at the end of a pipe
    for segment in cmd.split("|")[1:]:
        pipe_cmd = segment.strip().split()
        if pipe_cmd:
            pipe_name = os.path.basename(pipe_cmd[0])
            if pipe_name in INTERACTIVE_HINT_KEYS:
                return t(INTERACTIVE_HINT_KEYS[pipe_name], lang)

    # Always-interactive commands
    if cmd_name in INTERACTIVE_HINT_KEYS:
        return t(INTERACTIVE_HINT_KEYS[cmd_name], lang)

    # Commands requiring batch flag
    if cmd_name in BATCH_FLAGS:
        required_flag = BATCH_FLAGS[cmd_name]

        # For top, strictly match flags like -b, -bn1
        if cmd_name == "top":
            has_batch = any(p.startswith("-") and "b" in p for p in parts[1:])
            if not has_batch:
                return t("hint_top", lang).format(flag=required_flag)

        # For man, intercept if no - flags provided
        elif cmd_name == "man":
            has_flag = any(p.startswith("-") for p in parts[1:])
            if not has_flag:
                return t("hint_man", lang).format(flag=required_flag)

    # REPL command detection: must have execution flag or script file argument
    if cmd_name in REPL_CMDS:
        safe_flags = {"-c", "-e", "--version", "-V", "-h", "--help"}
        has_safe_flag = any(f in parts for f in safe_flags)
        has_script_file = any(not p.startswith("-") for p in parts[1:])
        if not (has_safe_flag or has_script_file):
            return t("hint_repl", lang).format(cmd=cmd_name)

    return None


# ── Command execution ────────────────────────────────────────────────────────
def execute(cmd: str) -> str:
    """Execute a shell command under persistent cwd with triple hang-protection and process group cleanup."""
    cwd = _read_cwd()
    try:
        # shlex.quote prevents path injection from breaking bash syntax
        wrapped = f"cd {shlex.quote(cwd)} && timeout {TIMEOUT} {cmd}"
        proc = subprocess.Popen(
            wrapped,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env={**os.environ, "HOME": DEFAULT_CWD},
        )
        try:
            stdout, stderr = proc.communicate(timeout=TIMEOUT + 5)
        except subprocess.TimeoutExpired:
            pgid = os.getpgid(proc.pid)
            try:
                os.killpg(pgid, signal.SIGTERM)
                proc.wait(timeout=3)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                os.killpg(pgid, signal.SIGKILL)
                proc.wait()
            return f"❌ Command timed out, terminated (>{TIMEOUT}s)"

        output = stdout or stderr or "(no output)"
        if proc.returncode == 124:
            output += "\n❌ Command timed out, terminated"
        elif proc.returncode != 0:
            output += f"\n[exit code: {proc.returncode}]"
        return output

    except Exception as e:
        return f"❌ Error: {e}"


# ── cd handling ──────────────────────────────────────────────────────────────
def handle_cd(text: str, lang: str = DEFAULT_LANG) -> tuple[bool, str]:
    """
    Handle pure cd commands. If compound logic (&&, etc.) is present, pass to execute.
    Returns (handled, message)
    """
    if any(op in text for op in ("&&", ";", "|", "||")):
        return False, ""  # Compound command, let shell handle it

    parts = text.split()
    target = parts[1] if len(parts) > 1 else "~"

    if target == "-":
        return True, t("cd_not_supported", lang)

    target = os.path.expanduser(target)
    if not os.path.isabs(target):
        target = os.path.join(_read_cwd(), target)
    target = os.path.realpath(target)

    if os.path.isdir(target):
        _write_cwd(target)
        return True, t("current_dir", lang).format(dir=target)

    return True, t("dir_not_found", lang).format(dir=parts[1] if len(parts) > 1 else "~")


# ── Telegram message sending and shortcut menu ───────────────────────────────
def _set_telegram_menu() -> None:
    """Register shortcut commands in the Telegram input menu (default language)"""
    lang = DEFAULT_LANG
    commands = [
        {"command": "openclaw_start", "description": t("openclaw_start_label", lang)},
        {"command": "openclaw_stop",  "description": t("openclaw_stop_label", lang)},
        {"command": "openclaw_restart","description": t("openclaw_restart_label", lang)},
        {"command": "cwd",            "description": t("menu_cwd", lang)},
        {"command": "lang",           "description": t("menu_lang", lang)},
        {"command": "help",           "description": t("menu_help", lang)},
    ]
    try:
        resp = requests.post(f"{API}/setMyCommands", json={"commands": commands}, timeout=10)
        resp.raise_for_status()
        print(t("menu_registered", lang))
    except Exception as e:
        print(t("menu_failed", lang).format(error=e))


def send(chat_id: int, text: str, reply_to: int | None = None, code: bool = False) -> None:
    """Send a message; when code=True, format with MarkdownV2 code blocks."""
    if code:
        # Properly escape backslashes and backticks, preserve original output, prevent 400 errors
        safe = text[:4000].replace('\\', '\\\\').replace('`', '\\`')
        payload: dict = {
            "chat_id": chat_id,
            "text": f"```\n{safe}\n```",
            "parse_mode": "MarkdownV2",
        }
    else:
        payload = {"chat_id": chat_id, "text": text[:4096]}

    if reply_to is not None:
        payload["reply_to_message_id"] = reply_to

    try:
        resp = requests.post(f"{API}/sendMessage", json=payload, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"⚠️ Failed to send message: {e}")


# ── Message routing ──────────────────────────────────────────────────────────
def handle_message(msg: dict) -> None:
    chat_id    = msg["chat"]["id"]
    reply_to   = msg["message_id"]
    user_id    = msg.get("from", {}).get("id")
    text       = msg.get("text", "").strip()
    lang       = get_user_lang(user_id)

    if not text:
        return

    # Access control: if env var not configured (0) or ID mismatch, deny all (prevent RCE)
    if ALLOWED_USER == 0 or user_id != ALLOWED_USER:
        send(chat_id, t("unauthorized", lang), reply_to)
        return

    # Bot commands
    if text.startswith("/"):
        _handle_bot_command(chat_id, reply_to, text, user_id, lang)
        # Show language hint for first-time users
        hint = _lang_hint(user_id)
        if hint:
            send(chat_id, hint)
        return

    print(f"[{msg['chat'].get('username', chat_id)}] $ {text}")

    # Intercept interactive commands
    hint = check_interactive(text, lang)
    if hint:
        send(chat_id, t("interactive_blocked", lang).format(suggestion=hint), reply_to)
        return

    # Auto-correct top -b (without -n) → top -bn1
    parts = text.split()
    if os.path.basename(parts[0]) == "top" and "-b" in parts and "-n" not in text:
        idx = parts.index("-b")
        parts[idx] = "-bn1"
        text = " ".join(parts)
        send(chat_id, t("auto_corrected", lang).format(cmd=text), reply_to)

    # Smart cd handling
    if parts[0] == "cd":
        handled, msg_text = handle_cd(text, lang)
        if handled:
            send(chat_id, msg_text, reply_to)
            return

    # Execute command
    output  = execute(text)
    prefix  = t("cmd_prefix", lang).format(cwd=_read_cwd(), cmd=text) + "\n"
    send(chat_id, prefix + output, reply_to, code=True)

    # Show language hint for first-time users (after their command response)
    hint = _lang_hint(user_id)
    if hint:
        send(chat_id, hint)


def _lang_hint(user_id: int | None) -> str | None:
    """Return a language hint for users who haven't set a preference yet. One-time only."""
    if user_id is None or user_id in _user_langs:
        return None
    return "💡 Language: /lang zh for 中文  |  /lang en for English"


def _handle_bot_command(chat_id: int, reply_to: int, text: str, user_id: int | None, lang: str) -> None:
    if text == "/cwd":
        send(chat_id, t("current_dir", lang).format(dir=_read_cwd()), reply_to)
    elif text.startswith("/help"):
        send(chat_id, t("help_text", lang), reply_to)
    elif text.startswith("/lang"):
        parts = text.split()
        if len(parts) < 2:
            # No argument: show current language + usage
            msg = t("lang_current", lang).format(lang=t(f"lang_{lang}", lang))
            msg += "\n\n" + t("lang_usage", lang)
            send(chat_id, msg, reply_to)
            return
        new_lang = parts[1].lower().strip()
        if new_lang not in SUPPORTED_LANGS:
            send(chat_id, t("lang_invalid", lang), reply_to)
            return
        if user_id is not None:
            set_user_lang(user_id, new_lang)
        send(chat_id, t("lang_set", new_lang).format(lang=t(f"lang_{new_lang}", new_lang)), reply_to)
    # OpenClaw shortcut commands
    elif text == "/openclaw_start":
        send(chat_id, t("openclaw_start", lang), reply_to)
        output = execute("env XDG_RUNTIME_DIR=/run/user/0 openclaw gateway start")
        send(chat_id, f"[Gateway Start]\n{output}", reply_to, code=True)
    elif text == "/openclaw_stop":
        send(chat_id, t("openclaw_stop", lang), reply_to)
        output = execute("env XDG_RUNTIME_DIR=/run/user/0 openclaw gateway stop")
        send(chat_id, f"[Gateway Stop]\n{output}", reply_to, code=True)
    elif text == "/openclaw_restart":
        send(chat_id, t("openclaw_restart", lang), reply_to)
        output = execute("env XDG_RUNTIME_DIR=/run/user/0 openclaw gateway restart")
        send(chat_id, f"[Gateway Restart]\n{output}", reply_to, code=True)
    else:
        send(chat_id, t("unknown_command", lang), reply_to)


# ── Main loop ────────────────────────────────────────────────────────────────
def main() -> None:
    _init_cwd()
    _set_telegram_menu()  # Register shortcut menu on startup
    print(t("bot_starting", DEFAULT_LANG))
    print(t("bot_workdir", DEFAULT_LANG).format(dir=_read_cwd()))
    if ALLOWED_USER == 0:
        print(t("bot_no_user", DEFAULT_LANG))

    offset = 0
    while True:
        try:
            resp = requests.get(
                f"{API}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35,
            )
            data = resp.json()
            if not data.get("ok"):
                time.sleep(2)
                continue

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message")
                if msg:
                    handle_message(msg)

        except requests.exceptions.ReadTimeout:
            continue
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(3)


if __name__ == "__main__":
    main()
