#!/usr/bin/env python3
"""Telegram Shell Bot — 收到消息 → 执行命令 → 返回结果，cd 持久化"""

import os
import shlex
import signal
import subprocess
import time
import requests

# ── 配置 ────────────────────────────────────────────────────────────────────
TOKEN        = os.environ["BOT_TOKEN"]
# 安全底线：如果未配置，强制为 0，后续逻辑将拒绝所有人访问
ALLOWED_USER = int(os.environ.get("ALLOWED_USER", "0"))
TIMEOUT      = int(os.environ.get("CMD_TIMEOUT", "30"))
API          = f"https://api.telegram.org/bot{TOKEN}"
CWD_FILE     = "/tmp/tg-shell-bot.cwd"
# 默认目录改为当前运行用户的家目录
DEFAULT_CWD  = os.path.expanduser("~")

# ── 交互式命令提示表 ─────────────────────────────────────────────────────────
INTERACTIVE_HINTS: dict[str, str] = {
    "htop":   "htop → top -bn1 | head -20",
    "less":   "less → cat <文件>",
    "more":   "more → cat <文件>",
    "vim":    "vim → 读取用 cat，编辑用 sed / echo '>'",
    "vi":     "vi → 读取用 cat，编辑用 sed / echo '>'",
    "nano":   "nano → 读取用 cat，编辑用 sed / echo '>'",
    "watch":  "watch → while true; do <cmd>; sleep 2; done",
    "tmux":   "tmux 是终端多路复用器，无法在此使用",
    "screen": "screen 是终端多路复用器，无法在此使用",
    "ssh":    "ssh 需要交互终端，无法在此使用",
    "su":     "su 需要交互终端，用 sudo <命令> 代替",
    "irb":    "irb → ruby -e \"代码\"",
}

# 需要额外 flag 才能非交互运行的命令
BATCH_FLAGS: dict[str, str] = {
    "top": "-bn1",
    "man": "-P cat",
}

# 无参数时会进入交互 REPL 的命令
REPL_CMDS = {"python", "python3", "node", "mysql", "psql", "ruby", "lua"}


# ── 工作目录持久化 ────────────────────────────────────────────────────────────
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


# ── 交互式命令检测 ────────────────────────────────────────────────────────────
def check_interactive(cmd: str) -> str | None:
    """若命令需要交互终端，返回友好提示；否则返回 None。"""
    parts = cmd.split()
    if not parts:
        return None

    cmd_name = os.path.basename(parts[0])

    # tail -f 检测
    if cmd_name == "tail" and any(f in parts for f in ("-f", "--follow", "-F")):
        return "tail -f → tail -n 50 <文件>"

    # 管道末尾的分页/编辑命令检测
    for segment in cmd.split("|")[1:]:
        pipe_cmd = segment.strip().split()
        if pipe_cmd:
            pipe_name = os.path.basename(pipe_cmd[0])
            if pipe_name in INTERACTIVE_HINTS:
                return INTERACTIVE_HINTS[pipe_name]

    # 永远交互的命令
    if cmd_name in INTERACTIVE_HINTS:
        return INTERACTIVE_HINTS[cmd_name]

    # 需要 batch flag 的命令检测
    if cmd_name in BATCH_FLAGS:
        required_flag = BATCH_FLAGS[cmd_name]
        
        # 对于 top，严格匹配形如 -b, -bn1 等参数
        if cmd_name == "top":
            has_batch = any(p.startswith("-") and "b" in p for p in parts[1:])
            if not has_batch:
                return f"top（交互模式）→ 建议使用 top {required_flag}"
                
        # 对于 man，如果没有任何 - 开头的参数，则提示拦截
        elif cmd_name == "man":
            has_flag = any(p.startswith("-") for p in parts[1:])
            if not has_flag:
                return f"man（交互模式）→ 建议使用 man {required_flag} <命令>"

    # REPL 命令增强检测：必须带有执行标志或脚本文件参数，否则拦截
    if cmd_name in REPL_CMDS:
        safe_flags = {"-c", "-e", "--version", "-V", "-h", "--help"}
        has_safe_flag = any(f in parts for f in safe_flags)
        has_script_file = any(not p.startswith("-") for p in parts[1:])
        if not (has_safe_flag or has_script_file):
            return f"{cmd_name} 交互模式不可用，请传入脚本文件或 -e/-c 参数"

    return None


# ── 命令执行 ─────────────────────────────────────────────────────────────────
def execute(cmd: str) -> str:
    """在持久化 cwd 下执行 shell 命令，三重防卡死 + 进程组清理。"""
    cwd = _read_cwd()
    try:
        # shlex.quote 防止路径注入破坏 bash 语法
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
            return f"❌ 命令超时，已终止（>{TIMEOUT}s）"

        output = stdout or stderr or "(无输出)"
        if proc.returncode == 124:
            output += "\n❌ 命令超时，已被终止"
        elif proc.returncode != 0:
            output += f"\n[exit code: {proc.returncode}]"
        return output

    except Exception as e:
        return f"❌ 错误: {e}"


# ── cd 处理 ──────────────────────────────────────────────────────────────────
def handle_cd(text: str) -> tuple[bool, str]:
    """
    处理纯 cd 命令。若包含 && 等复合逻辑，交由 execute 跑完，不拦截。
    返回 (handled, message)
    """
    if any(op in text for op in ("&&", ";", "|", "||")):
        return False, ""  # 是复合命令，让 shell 自己去跑（但不持久化）

    parts = text.split()
    target = parts[1] if len(parts) > 1 else "~"

    if target == "-":
        return True, "⚠️ cd - 不支持（无 OLDPWD）"

    target = os.path.expanduser(target)
    if not os.path.isabs(target):
        target = os.path.join(_read_cwd(), target)
    target = os.path.realpath(target)

    if os.path.isdir(target):
        _write_cwd(target)
        return True, f"📂 {target}"

    return True, f"❌ 目录不存在或无权限: {parts[1] if len(parts) > 1 else '~'}"


# ── Telegram 消息发送与快捷菜单 ───────────────────────────────────────────────
def _set_telegram_menu() -> None:
    """自动向 Telegram 注册输入框左侧的快捷命令菜单"""
    commands = [
        {"command": "openclaw_start", "description": "▶️ 启动 OpenClaw"},
        {"command": "openclaw_stop", "description": "⏹ 停止 OpenClaw"},
        {"command": "openclaw_restart", "description": "🔄 重启 OpenClaw"},
        {"command": "cwd", "description": "📂 查看当前目录"},
        {"command": "help", "description": "📖 查看帮助"},
    ]
    try:
        resp = requests.post(f"{API}/setMyCommands", json={"commands": commands}, timeout=10)
        resp.raise_for_status()
        print("✅ Telegram 快捷菜单注册成功！")
    except Exception as e:
        print(f"⚠️ Telegram 菜单注册失败: {e}")


def send(chat_id: int, text: str, reply_to: int | None = None, code: bool = False) -> None:
    """发送消息；code=True 时用 MarkdownV2 代码块格式化。"""
    if code:
        # 正确转义反斜杠和反引号，保留原始输出内容，防止 API 报错 400
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
        print(f"⚠️ 发送消息失败: {e}")


# ── 消息路由 ─────────────────────────────────────────────────────────────────
def handle_message(msg: dict) -> None:
    chat_id    = msg["chat"]["id"]
    reply_to   = msg["message_id"]
    user_id    = msg.get("from", {}).get("id")
    text       = msg.get("text", "").strip()

    if not text:
        return

    # 权限鉴定：未配置环境变量(0) 或 ID 不匹配，一律拒绝 (防止 RCE)
    if ALLOWED_USER == 0 or user_id != ALLOWED_USER:
        send(chat_id, "⛔ 未授权", reply_to)
        return

    # Bot 命令
    if text.startswith("/"):
        _handle_bot_command(chat_id, reply_to, text)
        return

    print(f"[{msg['chat'].get('username', chat_id)}] $ {text}")

    # 拦截交互式命令
    hint = check_interactive(text)
    if hint:
        send(chat_id, f"⚠️ 交互式命令被拦截\n\n{hint}", reply_to)
        return

    # 自动修正 top -b（无 -n）→ top -bn1
    parts = text.split()
    if os.path.basename(parts[0]) == "top" and "-b" in parts and "-n" not in text:
        idx = parts.index("-b")
        parts[idx] = "-bn1"
        text = " ".join(parts)
        send(chat_id, f"💡 自动修正: {text}", reply_to)

    # 智能处理 cd
    if parts[0] == "cd":
        handled, msg_text = handle_cd(text)
        if handled:
            send(chat_id, msg_text, reply_to)
            return

    # 执行命令
    output  = execute(text)
    prefix  = f"[{_read_cwd()}] $ {text}\n"
    send(chat_id, prefix + output, reply_to, code=True)


def _handle_bot_command(chat_id: int, reply_to: int, text: str) -> None:
    if text == "/cwd":
        send(chat_id, f"📂 当前目录: {_read_cwd()}", reply_to)
    elif text.startswith("/help"):
        send(
            chat_id,
            "发送命令即可执行，cd 会持久切换目录\n"
            "/cwd  — 查看当前目录\n"
            "/help — 帮助\n\n"
            "💡 左下角菜单已配置 OpenClaw 快捷操作",
            reply_to,
        )
    # OpenClaw 快捷操作拦截
    elif text == "/openclaw_start":
        send(chat_id, "⏳ 正在启动 OpenClaw Gateway...", reply_to)
        output = execute("env XDG_RUNTIME_DIR=/run/user/0 openclaw gateway start")
        send(chat_id, f"[Gateway Start]\n{output}", reply_to, code=True)
    elif text == "/openclaw_stop":
        send(chat_id, "⏳ 正在停止 OpenClaw Gateway...", reply_to)
        output = execute("env XDG_RUNTIME_DIR=/run/user/0 openclaw gateway stop")
        send(chat_id, f"[Gateway Stop]\n{output}", reply_to, code=True)
    elif text == "/openclaw_restart":
        send(chat_id, "⏳ 正在重启 OpenClaw Gateway...", reply_to)
        output = execute("env XDG_RUNTIME_DIR=/run/user/0 openclaw gateway restart")
        send(chat_id, f"[Gateway Restart]\n{output}", reply_to, code=True)
    else:
        send(chat_id, "未知命令，发送 /help 查看帮助", reply_to)


# ── 主循环 ───────────────────────────────────────────────────────────────────
def main() -> None:
    _init_cwd()
    _set_telegram_menu()  # 启动时自动注册左下角快捷菜单
    print("🐰 Telegram Shell Bot 启动中...")
    print(f"📂 工作目录: {_read_cwd()}")
    if ALLOWED_USER == 0:
        print("⚠️ 警告: 未配置 ALLOWED_USER，所有人将被拒绝访问！")

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