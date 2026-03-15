#!/usr/bin/env python3
"""Telegram Shell Bot — receives message → executes command → returns result, with persistent cd"""

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
# Default directory: current user's home
DEFAULT_CWD  = os.path.expanduser("~")

# ── Interactive command hint table ────────────────────────────────────────────
INTERACTIVE_HINTS: dict[str, str] = {
    "htop":   "htop → top -bn1 | head -20",
    "less":   "less → cat <file>",
    "more":   "more → cat <file>",
    "vim":    "vim → use cat to read, sed / echo '>' to edit",
    "vi":     "vi → use cat to read, sed / echo '>' to edit",
    "nano":   "nano → use cat to read, sed / echo '>' to edit",
    "watch":  "watch → while true; do <cmd>; sleep 2; done",
    "tmux":   "tmux is a terminal multiplexer, not available here",
    "screen": "screen is a terminal multiplexer, not available here",
    "ssh":    "ssh requires an interactive terminal, not available here",
    "su":     "su requires an interactive terminal, use sudo <command> instead",
    "irb":    "irb → ruby -e \"code\"",
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
def check_interactive(cmd: str) -> str | None:
    """Returns a friendly hint if the command requires an interactive terminal; otherwise None."""
    parts = cmd.split()
    if not parts:
        return None

    cmd_name = os.path.basename(parts[0])

    # tail -f detection
    if cmd_name == "tail" and any(f in parts for f in ("-f", "--follow", "-F")):
        return "tail -f → tail -n 50 <file>"

    # Detect pager/editor commands at the end of a pipe
    for segment in cmd.split("|")[1:]:
        pipe_cmd = segment.strip().split()
        if pipe_cmd:
            pipe_name = os.path.basename(pipe_cmd[0])
            if pipe_name in INTERACTIVE_HINTS:
                return INTERACTIVE_HINTS[pipe_name]

    # Always-interactive commands
    if cmd_name in INTERACTIVE_HINTS:
        return INTERACTIVE_HINTS[cmd_name]

    # Commands requiring batch flag
    if cmd_name in BATCH_FLAGS:
        required_flag = BATCH_FLAGS[cmd_name]

        # For top, strictly match flags like -b, -bn1
        if cmd_name == "top":
            has_batch = any(p.startswith("-") and "b" in p for p in parts[1:])
            if not has_batch:
                return f"top (interactive mode) → consider using top {required_flag}"

        # For man, intercept if no - flags provided
        elif cmd_name == "man":
            has_flag = any(p.startswith("-") for p in parts[1:])
            if not has_flag:
                return f"man (interactive mode) → consider using man {required_flag} <command>"

    # REPL command detection: must have execution flag or script file argument
    if cmd_name in REPL_CMDS:
        safe_flags = {"-c", "-e", "--version", "-V", "-h", "--help"}
        has_safe_flag = any(f in parts for f in safe_flags)
        has_script_file = any(not p.startswith("-") for p in parts[1:])
        if not (has_safe_flag or has_script_file):
            return f"{cmd_name} interactive mode not available, please provide a script file or -e/-c flag"

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
def handle_cd(text: str) -> tuple[bool, str]:
    """
    Handle pure cd commands. If compound logic (&&, etc.) is present, pass to execute.
    Returns (handled, message)
    """
    if any(op in text for op in ("&&", ";", "|", "||")):
        return False, ""  # Compound command, let shell handle it

    parts = text.split()
    target = parts[1] if len(parts) > 1 else "~"

    if target == "-":
        return True, "⚠️ cd - not supported (no OLDPWD)"

    target = os.path.expanduser(target)
    if not os.path.isabs(target):
        target = os.path.join(_read_cwd(), target)
    target = os.path.realpath(target)

    if os.path.isdir(target):
        _write_cwd(target)
        return True, f"📂 {target}"

    return True, f"❌ Directory does not exist or no permission: {parts[1] if len(parts) > 1 else '~'}"


# ── Telegram message sending and shortcut menu ───────────────────────────────
def _set_telegram_menu() -> None:
    """Register shortcut commands in the Telegram input menu"""
    commands = [
        {"command": "openclaw_start", "description": "▶️ Start OpenClaw"},
        {"command": "openclaw_stop", "description": "⏹ Stop OpenClaw"},
        {"command": "openclaw_restart", "description": "🔄 Restart OpenClaw"},
        {"command": "cwd", "description": "📂 View current directory"},
        {"command": "help", "description": "📖 View help"},
    ]
    try:
        resp = requests.post(f"{API}/setMyCommands", json={"commands": commands}, timeout=10)
        resp.raise_for_status()
        print("✅ Telegram shortcut menu registered!")
    except Exception as e:
        print(f"⚠️ Telegram menu registration failed: {e}")


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

    if not text:
        return

    # Access control: if env var not configured (0) or ID mismatch, deny all (prevent RCE)
    if ALLOWED_USER == 0 or user_id != ALLOWED_USER:
        send(chat_id, "⛔ Unauthorized", reply_to)
        return

    # Bot commands
    if text.startswith("/"):
        _handle_bot_command(chat_id, reply_to, text)
        return

    print(f"[{msg['chat'].get('username', chat_id)}] $ {text}")

    # Intercept interactive commands
    hint = check_interactive(text)
    if hint:
        send(chat_id, f"⚠️ Interactive command blocked\n\n{hint}", reply_to)
        return

    # Auto-correct top -b (without -n) → top -bn1
    parts = text.split()
    if os.path.basename(parts[0]) == "top" and "-b" in parts and "-n" not in text:
        idx = parts.index("-b")
        parts[idx] = "-bn1"
        text = " ".join(parts)
        send(chat_id, f"💡 Auto-corrected: {text}", reply_to)

    # Smart cd handling
    if parts[0] == "cd":
        handled, msg_text = handle_cd(text)
        if handled:
            send(chat_id, msg_text, reply_to)
            return

    # Execute command
    output  = execute(text)
    prefix  = f"[{_read_cwd()}] $ {text}\n"
    send(chat_id, prefix + output, reply_to, code=True)


def _handle_bot_command(chat_id: int, reply_to: int, text: str) -> None:
    if text == "/cwd":
        send(chat_id, f"📂 Current directory: {_read_cwd()}", reply_to)
    elif text.startswith("/help"):
        send(
            chat_id,
            "Send commands to execute, cd changes directory persistently\n"
            "/cwd  — View current directory\n"
            "/help — Help\n\n"
            "💡 OpenClaw shortcuts are available in the bottom-left menu",
            reply_to,
        )
    # OpenClaw shortcut commands
    elif text == "/openclaw_start":
        send(chat_id, "⏳ Starting OpenClaw Gateway...", reply_to)
        output = execute("env XDG_RUNTIME_DIR=/run/user/0 openclaw gateway start")
        send(chat_id, f"[Gateway Start]\n{output}", reply_to, code=True)
    elif text == "/openclaw_stop":
        send(chat_id, "⏳ Stopping OpenClaw Gateway...", reply_to)
        output = execute("env XDG_RUNTIME_DIR=/run/user/0 openclaw gateway stop")
        send(chat_id, f"[Gateway Stop]\n{output}", reply_to, code=True)
    elif text == "/openclaw_restart":
        send(chat_id, "⏳ Restarting OpenClaw Gateway...", reply_to)
        output = execute("env XDG_RUNTIME_DIR=/run/user/0 openclaw gateway restart")
        send(chat_id, f"[Gateway Restart]\n{output}", reply_to, code=True)
    else:
        send(chat_id, "Unknown command, send /help for usage", reply_to)


# ── Main loop ────────────────────────────────────────────────────────────────
def main() -> None:
    _init_cwd()
    _set_telegram_menu()  # Register shortcut menu on startup
    print("🐰 Telegram Shell Bot starting...")
    print(f"📂 Working directory: {_read_cwd()}")
    if ALLOWED_USER == 0:
        print("⚠️ Warning: ALLOWED_USER not configured, all access will be denied!")

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
