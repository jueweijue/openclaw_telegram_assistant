#!/usr/bin/env python3
"""Telegram Shell Bot — multi-host support, receives message → executes command → returns result"""

import json
import os
import re
import shlex
import time
from dataclasses import dataclass, field

import requests

from hosts import (
    load_hosts, save_hosts, add_host, remove_host,
    get_default_host, set_default_host, format_host_list, LOCAL_HOST_KEY,
)
from executor import (
    execute, execute_local, handle_cd, read_cwd, write_cwd,
    close_ssh, close_all_ssh,
)

# ── Configuration ────────────────────────────────────────────────────────────
TOKEN        = os.environ["BOT_TOKEN"]
ALLOWED_USER = int(os.environ.get("ALLOWED_USER", "0"))
TIMEOUT      = int(os.environ.get("CMD_TIMEOUT", "30"))
API          = f"https://api.telegram.org/bot{TOKEN}"
LANG_FILE    = "/tmp/tg-shell-bot.lang"
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
            "🖥️ 多主机控制:\n"
            "/hosts           — 查看所有主机（点击切换）\n"
            "/addhost         — 添加主机（交互式）\n"
            "/delhost <name>  — 删除主机\n"
            "/disconnect      — 断开所有 SSH 连接\n"
            "/api             — API 管理（添加/删除）\n"
            "发送 /cancel 退出交互式流程\n\n"
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
        # Interactive hints
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
        # Multi-host
        "hosts_list":           "🖥️ 主机列表:\n{list}\n\n💡 ⭐=默认  👈=当前活跃",
        "host_switched":        "✅ 已切换到主机: {name}",
        "host_not_found":       "❌ 主机不存在: {name}",
        "host_added":           "✅ 主机已添加: {name}",
        "host_exists":          "❌ 主机名已存在: {name}",
        "host_removed":         "✅ 主机已删除: {name}",
        "host_remove_local":    "❌ 不能删除本机 (local)",
        "host_prompt_name":     "📝 请输入主机名称（英文，如 my-vps）\n\n💡 发送 /cancel 退出",
        "host_prompt_host":     "📝 请输入主机地址（IP 或域名）：",
        "host_prompt_user":     "📝 请输入 SSH 用户名（默认 root）：",
        "host_prompt_port":     "📝 请输入 SSH 端口（默认 22）：",
        "host_prompt_auth":     "🔑 选择认证方式：",
        "host_auth_key":        "🔐 SSH 密钥",
        "host_auth_password":   "🔑 密码",
        "host_prompt_keyfile":  "📝 请输入密钥文件路径（如 ~/.ssh/id_rsa）：",
        "host_prompt_password": "📝 请输入 SSH 密码：",
        "host_add_cancelled":   "❌ 已取消添加主机",
        "host_on_prefix":       "[{host}] {cwd} $ {cmd}",
        "ssh_disconnected":     "✅ 所有 SSH 连接已断开",
        # API management
        "api_menu":             "🤖 API 管理",
        "api_prompt_name":      "📝 请输入 Provider 名称（如 deepseek、openrouter）\n\n💡 发送 /cancel 退出",
        "api_prompt_url":       "📝 请输入 Base URL（如 https://api.deepseek.com/v1）\n\n💡 发送 /cancel 退出",
        "api_prompt_key":       "📝 请输入 API Key\n\n💡 发送 /cancel 退出",
        "api_detecting":        "⏳ 正在探测协议并获取模型列表...",
        "api_fetch_fail":       "❌ 无法获取模型列表，请检查 URL 和 API Key",
        "api_selected":         "✅ 已选择: {models}",
        "api_select_header":    "🤖 {name} — 可用模型 (已选: {count})\n\n💡 发送 /cancel 退出",
        "api_confirm":          "✅ 确认选择",
        "api_manual_input":     "✏️ 手动输入",
        "api_prompt_manual":    "📝 请输入模型名称\n\n💡 发送 /cancel 退出",
        "api_manual_confirm":   "⚠️ 模型 **{model}** 不在 /models 列表中，是否确认添加？",
        "api_manual_yes":       "✅ 确认添加",
        "api_manual_no":        "❌ 取消",
        "api_no_selection":     "⚠️ 请至少选择一个模型",
        "api_writing":          "⏳ 正在写入配置...",
        "api_success":          "✅ API 添加成功！\n\nProvider: {name}\n模型数: {count}\n协议: {api_type}",
        "api_fail":             "❌ 写入配置失败: {error}",
        "api_exists_merged":    "ℹ️ Provider 已存在，新模型将合并到现有列表中",
        "api_restarting":       "🔄 重启 Gateway 中...",
        "api_restart_ok":       "✅ Gateway 重启完成",
        "api_restart_fail":     "⚠️ Gateway 重启失败，请手动检查",
        # API delete
        "api_del_title":        "🗑️ 删除 — 请选择操作:",
        "api_del_provider":     "🏭 删除整个Provider",
        "api_del_model":        "📦 删除单个模型",
        "api_del_select_prov":  "🗑️ 选择要删除的 Provider:",
        "api_del_confirm_prov": "⚠️ 确认删除整个 Provider: **{name}**\n\n将删除:\n• Provider 配置\n• {count} 个模型引用\n{default_msg}\n\n[✅ 确认] [❌ 取消]",
        "api_del_default_safe": "默认模型不受影响（当前: {model}）",
        "api_del_default_switch":"默认模型将自动切换到: {model}",
        "api_del_no_alt":       "❌ 无可用替代模型，无法删除（至少保留一个其他 Provider）",
        "api_del_prov_ok":      "✅ Provider {name} 已删除，{count} 个模型引用已清理",
        "api_del_select_model": "📦 {name} — 选择要删除的模型:",
        "api_del_model_confirm":"⚠️ 确认从 **{prov}** 删除 {count} 个模型？\n\n{models}\n{default_msg}",
        "api_del_model_ok":     "✅ 已从 {prov} 删除 {count} 个模型",
        "api_del_empty_prov":   "ℹ️ Provider {prov} 已无模型，自动删除整个 Provider",
        "api_del_cancelled":    "❌ 已取消删除",
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
            "🖥️ Multi-host:\n"
            "/hosts           — List all hosts (tap to switch)\n"
            "/addhost         — Add a host (interactive)\n"
            "/delhost <name>  — Remove a host\n"
            "/disconnect      — Disconnect all SSH sessions\n"
            "/api             — API management (add/delete)\n"
            "Send /cancel to exit interactive mode\n\n"
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
        # Interactive hints
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
        # Multi-host
        "hosts_list":           "🖥️ Hosts:\n{list}\n\n💡 ⭐=default  👈=active",
        "host_switched":        "✅ Switched to host: {name}",
        "host_not_found":       "❌ Host not found: {name}",
        "host_added":           "✅ Host added: {name}",
        "host_exists":          "❌ Host name already exists: {name}",
        "host_removed":         "✅ Host removed: {name}",
        "host_remove_local":    "❌ Cannot remove local host",
        "host_prompt_name":     "📝 Enter host name (English, e.g. my-vps)\n\n💡 Send /cancel to exit",
        "host_prompt_host":     "📝 Enter host address (IP or domain):",
        "host_prompt_user":     "📝 Enter SSH username (default: root):",
        "host_prompt_port":     "📝 Enter SSH port (default: 22):",
        "host_prompt_auth":     "🔑 Choose authentication method:",
        "host_auth_key":        "🔐 SSH Key",
        "host_auth_password":   "🔑 Password",
        "host_prompt_keyfile":  "📝 Enter key file path (e.g. ~/.ssh/id_rsa):",
        "host_prompt_password": "📝 Enter SSH password:",
        "host_add_cancelled":   "❌ Add host cancelled",
        "host_on_prefix":       "[{host}] {cwd} $ {cmd}",
        "ssh_disconnected":     "✅ All SSH connections disconnected",
        # API management
        "api_menu":             "🤖 API Management",
        "api_prompt_name":      "📝 Enter Provider name (e.g. deepseek, openrouter)\n\n💡 Send /cancel to exit",
        "api_prompt_url":       "📝 Enter Base URL (e.g. https://api.deepseek.com/v1)\n\n💡 Send /cancel to exit",
        "api_prompt_key":       "📝 Enter API Key\n\n💡 Send /cancel to exit",
        "api_detecting":        "⏳ Detecting protocol and fetching models...",
        "api_fetch_fail":       "❌ Failed to fetch models, check URL and API Key",
        "api_selected":         "✅ Selected: {models}",
        "api_select_header":    "🤖 {name} — Available models (selected: {count})\n\n💡 Send /cancel to exit",
        "api_confirm":          "✅ Confirm selection",
        "api_manual_input":     "✏️ Manual input",
        "api_prompt_manual":    "📝 Enter model name\n\n💡 Send /cancel to exit",
        "api_manual_confirm":   "⚠️ Model **{model}** is not in /models list. Add anyway?",
        "api_manual_yes":       "✅ Add anyway",
        "api_manual_no":        "❌ Cancel",
        "api_no_selection":     "⚠️ Please select at least one model",
        "api_writing":          "⏳ Writing config...",
        "api_success":          "✅ API added successfully!\n\nProvider: {name}\nModels: {count}\nProtocol: {api_type}",
        "api_fail":             "❌ Failed to write config: {error}",
        "api_exists_merged":    "ℹ️ Provider exists, new models will be merged",
        "api_restarting":       "🔄 Restarting Gateway...",
        "api_restart_ok":       "✅ Gateway restarted successfully",
        "api_restart_fail":     "⚠️ Gateway restart failed, please check manually",
        # API delete
        "api_del_title":        "🗑️ Delete — Choose an action:",
        "api_del_provider":     "🏭 Delete entire Provider",
        "api_del_model":        "📦 Delete individual models",
        "api_del_select_prov":  "🗑️ Select Provider to delete:",
        "api_del_confirm_prov": "⚠️ Confirm delete Provider: **{name}**\n\nWill delete:\n• Provider config\n• {count} model references\n{default_msg}\n\n[✅ Confirm] [❌ Cancel]",
        "api_del_default_safe": "Default model unaffected (current: {model})",
        "api_del_default_switch":"Default model will switch to: {model}",
        "api_del_no_alt":       "❌ No alternative models available, cannot delete (keep at least one other Provider)",
        "api_del_prov_ok":      "✅ Provider {name} deleted, {count} model references cleaned",
        "api_del_select_model": "📦 {name} — Select models to delete:",
        "api_del_model_confirm":"⚠️ Confirm deleting {count} models from **{prov}**?\n\n{models}\n{default_msg}",
        "api_del_model_ok":     "✅ Deleted {count} models from {prov}",
        "api_del_empty_prov":   "ℹ️ Provider {prov} has no models left, auto-deleted entire Provider",
        "api_del_cancelled":    "❌ Delete cancelled",
    },
}

DEFAULT_LANG = "en"


# ── Language helpers ─────────────────────────────────────────────────────────
def _load_langs() -> dict[int, str]:
    try:
        with open(LANG_FILE) as f:
            data = json.load(f)
            return {int(k): v for k, v in data.items()}
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def _save_langs(langs: dict[int, str]) -> None:
    with open(LANG_FILE, "w") as f:
        json.dump(langs, f)


_user_langs: dict[int, str] = _load_langs()


def t(key: str, lang: str) -> str:
    return TRANSLATIONS.get(lang, TRANSLATIONS[DEFAULT_LANG]).get(key, key)


def get_user_lang(user_id: int | None) -> str:
    if user_id is None:
        return DEFAULT_LANG
    return _user_langs.get(user_id, DEFAULT_LANG)


def set_user_lang(user_id: int, lang: str) -> None:
    _user_langs[user_id] = lang
    _save_langs(_user_langs)


# ── Interactive command detection ────────────────────────────────────────────
INTERACTIVE_HINT_KEYS: dict[str, str] = {
    "htop": "hint_htop", "less": "hint_less", "more": "hint_more",
    "vim": "hint_vim", "vi": "hint_vim", "nano": "hint_nano",
    "watch": "hint_watch", "tmux": "hint_tmux", "screen": "hint_screen",
    "ssh": "hint_ssh", "su": "hint_su", "irb": "hint_irb",
}

BATCH_FLAGS: dict[str, str] = {"top": "-bn1", "man": "-P cat"}

REPL_CMDS = {"python", "python3", "node", "mysql", "psql", "ruby", "lua"}


def check_interactive(cmd: str, lang: str = DEFAULT_LANG) -> str | None:
    parts = cmd.split()
    if not parts:
        return None
    cmd_name = os.path.basename(parts[0])
    if cmd_name == "tail" and any(f in parts for f in ("-f", "--follow", "-F")):
        return t("hint_tail_f", lang)
    for segment in cmd.split("|")[1:]:
        pipe_cmd = segment.strip().split()
        if pipe_cmd:
            pipe_name = os.path.basename(pipe_cmd[0])
            if pipe_name in INTERACTIVE_HINT_KEYS:
                return t(INTERACTIVE_HINT_KEYS[pipe_name], lang)
    if cmd_name in INTERACTIVE_HINT_KEYS:
        return t(INTERACTIVE_HINT_KEYS[cmd_name], lang)
    if cmd_name in BATCH_FLAGS:
        required_flag = BATCH_FLAGS[cmd_name]
        if cmd_name == "top":
            has_batch = any(p.startswith("-") and "b" in p for p in parts[1:])
            if not has_batch:
                return t("hint_top", lang).format(flag=required_flag)
        elif cmd_name == "man":
            has_flag = any(p.startswith("-") for p in parts[1:])
            if not has_flag:
                return t("hint_man", lang).format(flag=required_flag)
    if cmd_name in REPL_CMDS:
        safe_flags = {"-c", "-e", "--version", "-V", "-h", "--help"}
        has_safe_flag = any(f in parts for f in safe_flags)
        has_script_file = any(not p.startswith("-") for p in parts[1:])
        if not (has_safe_flag or has_script_file):
            return t("hint_repl", lang).format(cmd=cmd_name)
    return None


# ── Per-user active host selection ───────────────────────────────────────────
_active_hosts: dict[int, str] = {}  # user_id → host_key


def get_active_host(user_id: int | None) -> str | None:
    """Get the active host for a user. Returns None to use default."""
    if user_id is None:
        return None
    return _active_hosts.get(user_id)


def set_active_host(user_id: int, host_key: str) -> None:
    _active_hosts[user_id] = host_key


# ── Host add wizard state ────────────────────────────────────────────────────
@dataclass
class HostAddWizard:
    step: str  # name, host, user, port, auth, keyfile, password, config_path
    name: str = ""
    host: str = ""
    user: str = "root"
    port: int = 22
    auth_method: str = "key"  # key or password
    key_file: str = ""
    password: str = ""
    config_path: str = ""


# ── API management wizard state ──────────────────────────────────────────────
MODELS_PER_PAGE = 6

@dataclass
class ApiWizard:
    step: str  # name, url, key, select
    name: str = ""
    base_url: str = ""
    api_key: str = ""
    api_type: str = ""
    models: list = field(default_factory=list)
    selected: set = field(default_factory=set)
    page: int = 0
    is_existing: bool = False

_add_wizards: dict[int, HostAddWizard] = {}
_api_wizards: dict[int, ApiWizard] = {}


# ── Telegram message sending ─────────────────────────────────────────────────
def _set_telegram_menu() -> None:
    lang = DEFAULT_LANG
    commands = [
        {"command": "hosts",          "description": "🖥️ Hosts & multi-host controls"},
        {"command": "api",            "description": "🤖 API management"},
        {"command": "cwd",            "description": t("menu_cwd", lang)},
        {"command": "lang",           "description": t("menu_lang", lang)},
        {"command": "help",           "description": t("menu_help", lang)},
        {"command": "openclaw_start", "description": t("openclaw_start_label", lang)},
        {"command": "openclaw_stop",  "description": t("openclaw_stop_label", lang)},
        {"command": "openclaw_restart","description": t("openclaw_restart_label", lang)},
    ]
    try:
        resp = requests.post(f"{API}/setMyCommands", json={"commands": commands}, timeout=10)
        resp.raise_for_status()
        print(t("menu_registered", lang))
    except Exception as e:
        print(t("menu_failed", lang).format(error=e))


def send(chat_id: int, text: str, reply_to: int | None = None, code: bool = False) -> None:
    if code:
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


def send_hosts_menu(chat_id: int, reply_to: int, user_id: int | None, lang: str) -> None:
    """Send hosts list with inline buttons for switching."""
    hosts = load_hosts()
    active = get_active_host(user_id)
    if active is None:
        active = get_default_host(hosts)

    # Build text
    lines = ["🖥️ **主机列表**\n"]
    for key, info in hosts.items():
        markers = []
        if key == active:
            markers.append("✅当前")
        marker = " ".join(markers)
        if info["type"] == "local":
            lines.append(f"📍 {key} {marker}  (本机)")
        else:
            lines.append(f"🖥️ {key} {marker}  {info['user']}@{info['host']}")
    text = "\n".join(lines)

    # Build buttons — one row per host
    buttons = []
    for key, info in hosts.items():
        label = f"{'✅ ' if key == active else '🔄 '}{key}"
        buttons.append([{"text": label, "callback_data": f"host:{key}"}])

    # Action buttons
    buttons.append([
        {"text": "➕ 添加主机", "callback_data": "action:addhost"},
        {"text": "🔌 断开SSH", "callback_data": "action:disconnect"},
    ])

    payload = {
        "chat_id": chat_id,
        "text": text,
        "reply_markup": {"inline_keyboard": buttons},
    }
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    try:
        resp = requests.post(f"{API}/sendMessage", json=payload, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"⚠️ Failed to send hosts menu: {e}")


def answer_callback_query(callback_query_id: str, text: str = "") -> None:
    """Answer a callback query to dismiss the loading spinner."""
    try:
        requests.post(f"{API}/answerCallbackQuery", json={
            "callback_query_id": callback_query_id,
            "text": text,
            "show_alert": False,
        }, timeout=5)
    except Exception as e:
        print(f"⚠️ Failed to answer callback: {e}")


def handle_callback_query(cb: dict) -> None:
    """Handle inline button callbacks."""
    query_id = cb["id"]
    chat_id = cb["message"]["chat"]["id"]
    msg_id = cb["message"]["message_id"]
    user_id = cb.get("from", {}).get("id")
    data = cb.get("data", "")
    lang = get_user_lang(user_id)

    # Access control
    if ALLOWED_USER == 0 or user_id != ALLOWED_USER:
        answer_callback_query(query_id, "⛔ Unauthorized")
        return

    if data.startswith("host:"):
        # Switch host
        name = data[5:]
        hosts = load_hosts()
        if name not in hosts:
            answer_callback_query(query_id, f"❌ {name} not found")
            return
        if user_id is not None:
            set_active_host(user_id, name)
        answer_callback_query(query_id, f"✅ Switched to {name}")

        # Edit the message to update active indicator
        send_hosts_menu(chat_id, msg_id, user_id, lang)
        # Delete the old message to avoid clutter
        try:
            requests.post(f"{API}/deleteMessage", json={
                "chat_id": chat_id, "message_id": msg_id,
            }, timeout=5)
        except Exception:
            pass

    elif data == "action:addhost":
        answer_callback_query(query_id)
        _add_wizards[user_id] = HostAddWizard(step="name")
        send(chat_id, t("host_prompt_name", lang), msg_id)

    elif data == "action:disconnect":
        answer_callback_query(query_id)
        close_all_ssh()
        send(chat_id, t("ssh_disconnected", lang), msg_id)

    elif data == "action:api_add":
        answer_callback_query(query_id)
        _api_wizards[user_id] = ApiWizard(step="name")
        send(chat_id, t("api_prompt_name", lang), msg_id)

    elif data.startswith("model:"):
        _handle_model_callback(query_id, chat_id, msg_id, user_id, data, lang)

    elif data.startswith("page:"):
        _handle_page_callback(query_id, chat_id, msg_id, user_id, data, lang)

    elif data == "action:api_delete":
        answer_callback_query(query_id)
        _send_delete_type_menu(chat_id, msg_id, user_id, lang)

    elif data == "del:type:prov":
        answer_callback_query(query_id)
        _send_delete_prov_list(chat_id, msg_id, user_id, lang)

    elif data == "del:type:model":
        answer_callback_query(query_id)
        _send_delete_model_prov_list(chat_id, msg_id, user_id, lang)

    elif data.startswith("delprov:"):
        _handle_delprov_callback(query_id, chat_id, msg_id, user_id, data, lang)

    elif data.startswith("delmodel:"):
        _handle_delmodel_callback(query_id, chat_id, msg_id, user_id, data, lang)

    else:
        answer_callback_query(query_id)


# ── Message routing ──────────────────────────────────────────────────────────
def handle_message(msg: dict) -> None:
    chat_id    = msg["chat"]["id"]
    reply_to   = msg["message_id"]
    user_id    = msg.get("from", {}).get("id")
    text       = msg.get("text", "").strip()
    lang       = get_user_lang(user_id)

    if not text:
        return

    # Access control
    if ALLOWED_USER == 0 or user_id != ALLOWED_USER:
        send(chat_id, t("unauthorized", lang), reply_to)
        return

    # ── API management wizard (interactive multi-step) ──
    if user_id in _api_wizards:
        _handle_api_wizard(chat_id, reply_to, text, user_id, lang)
        return

    # ── Host add wizard (interactive multi-step) ──
    if user_id in _add_wizards:
        _handle_wizard(chat_id, reply_to, text, user_id, lang)
        return

    # Bot commands
    if text.startswith("/"):
        _handle_bot_command(chat_id, reply_to, text, user_id, lang)
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

    # Auto-correct top -b → top -bn1
    parts = text.split()
    if os.path.basename(parts[0]) == "top" and "-b" in parts and "-n" not in text:
        idx = parts.index("-b")
        parts[idx] = "-bn1"
        text = " ".join(parts)
        send(chat_id, t("auto_corrected", lang).format(cmd=text), reply_to)

    # Resolve active host
    active_host = get_active_host(user_id)

    # Smart cd handling (per-host)
    if parts[0] == "cd":
        target_host = active_host or get_default_host(load_hosts()) or LOCAL_HOST_KEY
        handled, msg_text = handle_cd(text, target_host)
        if handled:
            send(chat_id, msg_text, reply_to)
            return

    # Execute command
    result, resolved_host = execute(text, active_host)
    host_info = load_hosts().get(resolved_host, {})
    host_label = resolved_host if resolved_host != LOCAL_HOST_KEY else ""

    cwd = read_cwd(resolved_host)
    if host_label:
        prefix = t("host_on_prefix", lang).format(host=host_label, cwd=cwd, cmd=text) + "\n"
    else:
        prefix = t("cmd_prefix", lang).format(cwd=cwd, cmd=text) + "\n"

    send(chat_id, prefix + result.format(), reply_to, code=True)

    hint = _lang_hint(user_id)
    if hint:
        send(chat_id, hint)


def _lang_hint(user_id: int | None) -> str | None:
    if user_id is None or user_id in _user_langs:
        return None
    return "💡 Language: /lang zh for 中文  |  /lang en for English"


# ── Add host wizard handler ──────────────────────────────────────────────────
def _handle_wizard(chat_id: int, reply_to: int, text: str, user_id: int, lang: str) -> None:
    wizard = _add_wizards[user_id]

    # Cancel
    if text.lower() in ("/cancel", "cancel", "取消"):
        del _add_wizards[user_id]
        send(chat_id, t("host_add_cancelled", lang), reply_to)
        return

    if wizard.step == "name":
        if not re.match(r'^[a-zA-Z0-9_-]+$', text):
            send(chat_id, "⚠️ 名称只能包含字母、数字、下划线和连字符", reply_to)
            return
        wizard.name = text
        wizard.step = "host"
        send(chat_id, t("host_prompt_host", lang), reply_to)

    elif wizard.step == "host":
        wizard.host = text
        wizard.step = "user"
        send(chat_id, t("host_prompt_user", lang), reply_to)

    elif wizard.step == "user":
        if text and text != "-":
            wizard.user = text
        wizard.step = "port"
        send(chat_id, t("host_prompt_port", lang), reply_to)

    elif wizard.step == "port":
        if text and text != "-":
            try:
                wizard.port = int(text)
            except ValueError:
                send(chat_id, "⚠️ 端口必须是数字", reply_to)
                return
        wizard.step = "auth"
        send(chat_id, t("host_prompt_auth", lang) + "\n1️⃣ SSH 密钥\n2️⃣ 密码", reply_to)

    elif wizard.step == "auth":
        if text in ("1", "key", "密钥"):
            wizard.auth_method = "key"
            wizard.step = "keyfile"
            send(chat_id, t("host_prompt_keyfile", lang), reply_to)
        elif text in ("2", "password", "密码"):
            wizard.auth_method = "password"
            wizard.step = "password"
            send(chat_id, t("host_prompt_password", lang), reply_to)
        else:
            send(chat_id, "⚠️ 请选择 1 或 2", reply_to)

    elif wizard.step == "keyfile":
        wizard.key_file = text
        _finish_add_host(chat_id, reply_to, user_id, lang)

    elif wizard.step == "password":
        wizard.password = text
        _finish_add_host(chat_id, reply_to, user_id, lang)


def _finish_add_host(chat_id: int, reply_to: int, user_id: int, lang: str) -> None:
    wizard = _add_wizards[user_id]

    # Build host info for testing
    host_info = {
        "name": wizard.name,
        "type": "remote",
        "host": wizard.host,
        "port": wizard.port,
        "user": wizard.user,
    }
    if wizard.auth_method == "key" and wizard.key_file:
        host_info["key_file"] = wizard.key_file
    elif wizard.auth_method == "password" and wizard.password:
        host_info["password"] = wizard.password

    # Test connection before saving
    send(chat_id, "⏳ 正在测试连接...", reply_to)
    import paramiko
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        connect_kwargs = {
            "hostname": host_info["host"],
            "port": host_info.get("port", 22),
            "username": host_info["user"],
            "timeout": 10,
        }
        if host_info.get("key_file"):
            connect_kwargs["key_filename"] = os.path.expanduser(host_info["key_file"])
        elif host_info.get("password"):
            connect_kwargs["password"] = host_info["password"]
        client.connect(**connect_kwargs)
        # Quick command test
        stdin, stdout, stderr = client.exec_command("echo ok", timeout=5)
        result = stdout.read().decode().strip()
        client.close()

        if result == "ok":
            # Connection works, save it
            hosts = load_hosts()
            kwargs = {"name": wizard.name, "host": wizard.host,
                      "port": wizard.port, "user": wizard.user}
            if host_info.get("key_file"):
                kwargs["key_file"] = host_info["key_file"]
            elif host_info.get("password"):
                kwargs["password"] = host_info["password"]
            if add_host(hosts, **kwargs):
                send(chat_id, f"✅ 连接成功！主机 {wizard.name} 已添加", reply_to)
            else:
                send(chat_id, t("host_exists", lang).format(name=wizard.name), reply_to)
        else:
            send(chat_id, f"❌ 连接测试异常（echo 返回: {result}），未添加", reply_to)

    except Exception as e:
        send(chat_id, f"❌ 连接失败: {e}\n\n主机未添加，请检查信息后重试", reply_to)
    finally:
        try:
            client.close()
        except Exception:
            pass

    del _add_wizards[user_id]


# ── API management functions ─────────────────────────────────────────────────
def _send_api_menu(chat_id: int, reply_to: int, lang: str) -> None:
    """Send API management menu with inline buttons."""
    buttons = [[
        {"text": "➕ 添加API", "callback_data": "action:api_add"},
    ], [
        {"text": "🗑️ 删除API", "callback_data": "action:api_delete"},
    ]]
    payload = {
        "chat_id": chat_id,
        "text": t("api_menu", lang),
        "reply_markup": {"inline_keyboard": buttons},
    }
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    try:
        requests.post(f"{API}/sendMessage", json=payload, timeout=10)
    except Exception as e:
        print(f"⚠️ Failed to send API menu: {e}")


def _handle_api_wizard(chat_id: int, reply_to: int, text: str, user_id: int, lang: str) -> None:
    """Handle API wizard text input."""
    wizard = _api_wizards[user_id]

    # Cancel
    if text.lower() in ("/cancel", "cancel", "取消"):
        del _api_wizards[user_id]
        send(chat_id, t("host_add_cancelled", lang).replace("主机", "API"), reply_to)
        return

    if wizard.step == "name":
        wizard.name = text.strip()
        # Check if provider already exists - skip url/key steps
        existing = _get_existing_provider(user_id, wizard.name)
        if existing:
            wizard.base_url = existing.get("baseUrl", "")
            wizard.api_key = existing.get("apiKey", "")
            wizard.is_existing = True
            send(chat_id, f"ℹ️ Provider **{wizard.name}** 已存在，直接获取模型列表...", reply_to)
            _api_fetch_models(chat_id, reply_to, user_id, lang)
        else:
            wizard.step = "url"
            send(chat_id, t("api_prompt_url", lang), reply_to)

    elif wizard.step == "url":
        url = text.strip().rstrip("/")
        wizard.base_url = url
        wizard.step = "key"
        send(chat_id, t("api_prompt_key", lang), reply_to)

    elif wizard.step == "key":
        wizard.api_key = text.strip()
        # Fetch models
        _api_fetch_models(chat_id, reply_to, user_id, lang)

    elif wizard.step == "manual_input":
        # User typed a model name manually
        model_name = text.strip()
        if not model_name:
            return
        # Check if it matches a known model
        found = False
        for i, m in enumerate(wizard.models):
            if m == model_name:
                wizard.selected.add(i)
                found = True
                break
        if found:
            wizard.step = "select"
            _send_model_selection(chat_id, reply_to, user_id, lang)
        else:
            # Not in list - confirm with user via buttons
            wizard.step = "select"  # go back to select after confirm
            buttons = [[
                {"text": t("api_manual_yes", lang), "callback_data": f"model:forceadd:{model_name}"},
                {"text": t("api_manual_no", lang), "callback_data": "model:canceladd"},
            ]]
            payload = {
                "chat_id": chat_id,
                "text": t("api_manual_confirm", lang).format(model=model_name),
                "parse_mode": "Markdown",
                "reply_markup": {"inline_keyboard": buttons},
            }
            if reply_to:
                payload["reply_to_message_id"] = reply_to
            try:
                requests.post(f"{API}/sendMessage", json=payload, timeout=10)
            except Exception:
                pass


def _api_fetch_models(chat_id: int, reply_to: int, user_id: int, lang: str) -> None:
    """Fetch models from API endpoint."""
    wizard = _api_wizards[user_id]
    send(chat_id, t("api_detecting", lang), reply_to)

    # Detect protocol
    active = get_active_host(user_id)
    # Probe /responses
    probe_cmd = (
        f'curl -s -o /dev/null -w "%{{http_code}}" -m 6 -X POST '
        f'-H "Authorization: Bearer {shlex.quote(wizard.api_key)}" '
        f'-H "Content-Type: application/json" '
        f'{shlex.quote(wizard.base_url)}/responses'
    )
    result, _ = execute(probe_cmd, active)
    code = result.output.strip()
    if code and code not in ("404", "405", "000"):
        wizard.api_type = "openai-responses"
    else:
        wizard.api_type = "openai-completions"

    # Fetch models
    fetch_cmd = (
        f'curl -s -m 12 '
        f'-H "Authorization: Bearer {shlex.quote(wizard.api_key)}" '
        f'-H "User-Agent: Mozilla/5.0" '
        f'{shlex.quote(wizard.base_url)}/models'
    )
    result, _ = execute(fetch_cmd, active)

    if not result.output or result.exit_code != 0:
        send(chat_id, t("api_fetch_fail", lang), reply_to)
        del _api_wizards[user_id]
        return

    # Parse model IDs
    import re as _re
    model_ids = _re.findall(r'"id"\s*:\s*"([^"]+)"', result.output)
    if not model_ids:
        send(chat_id, t("api_fetch_fail", lang), reply_to)
        del _api_wizards[user_id]
        return

    wizard.models = sorted(set(model_ids))
    wizard.selected = set()
    wizard.page = 0

    # Check if provider already exists
    check_cmd = f'cat {shlex.quote(_get_config_path(user_id))} 2>/dev/null'
    result, _ = execute(check_cmd, active)
    if result.output:
        import json as _json
        try:
            cfg = _json.loads(result.output)
            existing = (((cfg.get("models") or {}).get("providers") or {}).get(wizard.name) or {})
            if existing:
                wizard.is_existing = True
                send(chat_id, t("api_exists_merged", lang), reply_to)
        except Exception:
            pass

    _send_model_selection(chat_id, reply_to, user_id, lang)


def _get_existing_provider(user_id: int, name: str) -> dict | None:
    """Check if a provider exists in config and return its info."""
    active = get_active_host(user_id)
    config_path = _get_config_path(user_id)
    cmd = f'cat {shlex.quote(os.path.expanduser(config_path))} 2>/dev/null'
    result, _ = execute(cmd, active)
    if not result.output:
        return None
    import json as _json
    try:
        cfg = _json.loads(result.output)
        providers = (((cfg.get("models") or {}).get("providers") or {}))
        return providers.get(name)
    except Exception:
        return None


def _get_config_path(user_id: int) -> str:
    """Get config path for the user's active host."""
    active = get_active_host(user_id)
    hosts = load_hosts()
    if active and active in hosts:
        return hosts[active].get("config_path", "~/.openclaw/openclaw.json")
    return "~/.openclaw/openclaw.json"


def _send_model_selection(chat_id: int, reply_to: int, user_id: int, lang: str) -> None:
    """Send or update the model selection message with buttons."""
    wizard = _api_wizards[user_id]
    total_pages = max(1, (len(wizard.models) + MODELS_PER_PAGE - 1) // MODELS_PER_PAGE)
    start = wizard.page * MODELS_PER_PAGE
    end = min(start + MODELS_PER_PAGE, len(wizard.models))
    page_models = wizard.models[start:end]

    header = t("api_select_header", lang).format(
        name=wizard.name, count=len(wizard.selected)
    )

    lines = [header]
    buttons = []

    # Manual input button
    buttons.append([{"text": t("api_manual_input", lang), "callback_data": "model:manual"}])

    # Model buttons - 2 per row
    row = []
    for idx in range(start, end):
        model_name = wizard.models[idx]
        display = model_name[:25] + "..." if len(model_name) > 25 else model_name
        check = "✅" if idx in wizard.selected else "⬜"
        row.append({"text": f"{check} {display}", "callback_data": f"model:toggle:{idx}"})
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Pagination
    if total_pages > 1:
        nav_row = []
        if wizard.page > 0:
            nav_row.append({"text": "⬅️", "callback_data": f"page:{wizard.page - 1}"})
        nav_row.append({"text": f"{wizard.page + 1}/{total_pages}", "callback_data": "page:noop"})
        if wizard.page < total_pages - 1:
            nav_row.append({"text": "➡️", "callback_data": f"page:{wizard.page + 1}"})
        buttons.append(nav_row)

    # Confirm button
    buttons.append([{"text": t("api_confirm", lang), "callback_data": "model:confirm"}])

    payload = {
        "chat_id": chat_id,
        "text": header,
        "reply_markup": {"inline_keyboard": buttons},
    }
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    try:
        requests.post(f"{API}/sendMessage", json=payload, timeout=10)
    except Exception as e:
        print(f"⚠️ Failed to send model selection: {e}")


def _handle_model_callback(query_id: str, chat_id: int, msg_id: int,
                           user_id: int, data: str, lang: str) -> None:
    """Handle model selection button callbacks."""
    if user_id not in _api_wizards:
        answer_callback_query(query_id, "⚠️ Session expired")
        return

    wizard = _api_wizards[user_id]
    parts = data.split(":", 2)
    action = parts[1] if len(parts) > 1 else ""

    if action == "toggle" and len(parts) > 2:
        idx = int(parts[2])
        if idx in wizard.selected:
            wizard.selected.discard(idx)
        else:
            wizard.selected.add(idx)
        answer_callback_query(query_id)
        # Edit message to update buttons
        _edit_model_selection(chat_id, msg_id, user_id, lang)

    elif action == "confirm":
        if not wizard.selected:
            answer_callback_query(query_id, t("api_no_selection", lang))
            return
        answer_callback_query(query_id)
        _api_write_config(chat_id, msg_id, user_id, lang)

    elif action == "manual":
        answer_callback_query(query_id)
        wizard.step = "manual_input"
        send(chat_id, t("api_prompt_manual", lang), msg_id)

    elif action.startswith("forceadd:"):
        model_name = action[9:]
        # Add as custom model
        wizard.models.append(model_name)
        wizard.selected.add(len(wizard.models) - 1)
        answer_callback_query(query_id, f"✅ Added {model_name}")
        wizard.step = "select"
        _edit_model_selection(chat_id, msg_id, user_id, lang)

    elif action == "canceladd":
        answer_callback_query(query_id)
        wizard.step = "select"
        _edit_model_selection(chat_id, msg_id, user_id, lang)

    else:
        answer_callback_query(query_id)


def _handle_page_callback(query_id: str, chat_id: int, msg_id: int,
                          user_id: int, data: str, lang: str) -> None:
    """Handle pagination button callbacks."""
    if user_id not in _api_wizards:
        answer_callback_query(query_id, "⚠️ Session expired")
        return

    wizard = _api_wizards[user_id]
    page = data.split(":", 1)[1]

    if page == "noop":
        answer_callback_query(query_id)
        return

    wizard.page = int(page)
    answer_callback_query(query_id)
    _edit_model_selection(chat_id, msg_id, user_id, lang)


def _edit_model_selection(chat_id: int, msg_id: int, user_id: int, lang: str) -> None:
    """Edit the model selection message in place."""
    wizard = _api_wizards[user_id]
    total_pages = max(1, (len(wizard.models) + MODELS_PER_PAGE - 1) // MODELS_PER_PAGE)
    start = wizard.page * MODELS_PER_PAGE
    end = min(start + MODELS_PER_PAGE, len(wizard.models))

    header = t("api_select_header", lang).format(
        name=wizard.name, count=len(wizard.selected)
    )

    buttons = []
    buttons.append([{"text": t("api_manual_input", lang), "callback_data": "model:manual"}])

    row = []
    for idx in range(start, end):
        model_name = wizard.models[idx]
        display = model_name[:25] + "..." if len(model_name) > 25 else model_name
        check = "✅" if idx in wizard.selected else "⬜"
        row.append({"text": f"{check} {display}", "callback_data": f"model:toggle:{idx}"})
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    if total_pages > 1:
        nav_row = []
        if wizard.page > 0:
            nav_row.append({"text": "⬅️", "callback_data": f"page:{wizard.page - 1}"})
        nav_row.append({"text": f"{wizard.page + 1}/{total_pages}", "callback_data": "page:noop"})
        if wizard.page < total_pages - 1:
            nav_row.append({"text": "➡️", "callback_data": f"page:{wizard.page + 1}"})
        buttons.append(nav_row)

    buttons.append([{"text": t("api_confirm", lang), "callback_data": "model:confirm"}])

    try:
        requests.post(f"{API}/editMessageText", json={
            "chat_id": chat_id,
            "message_id": msg_id,
            "text": header,
            "reply_markup": {"inline_keyboard": buttons},
        }, timeout=10)
    except Exception as e:
        print(f"⚠️ Failed to edit model selection: {e}")


def _api_write_config(chat_id: int, msg_id: int, user_id: int, lang: str) -> None:
    """Write API config to the active host."""
    wizard = _api_wizards[user_id]
    active = get_active_host(user_id)
    config_path = _get_config_path(user_id)

    send(chat_id, t("api_writing", lang), msg_id)

    # Build selected models
    selected_models = []
    for idx in sorted(wizard.selected):
        mid = wizard.models[idx]
        selected_models.append({
            "id": mid,
            "name": f"{wizard.name} / {mid}",
            "input": ["text"],
            "contextWindow": 128000,
            "maxTokens": 16384,
            "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
        })

    write_script = """import json, os
with open("/tmp/tg-bot-input.json") as f:
    inp = json.load(f)
path = inp["config_path"]
os.makedirs(os.path.dirname(path), exist_ok=True)
try:
    with open(path) as f: obj = json.load(f)
except: obj = {}
models_cfg = obj.setdefault("models", {})
models_cfg["mode"] = "merge"
providers = models_cfg.setdefault("providers", {})
name = inp["name"]
new_models = inp["models"]
if name in providers:
    existing = providers[name].setdefault("models", [])
    existing_ids = {m["id"] for m in existing if isinstance(m, dict)}
    for m in new_models:
        if m["id"] not in existing_ids:
            existing.append(m)
else:
    providers[name] = {
        "baseUrl": inp["base_url"],
        "apiKey": inp["api_key"],
        "api": inp["api_type"],
        "models": new_models,
    }
agents = obj.setdefault("agents", {})
defaults = agents.setdefault("defaults", {})
dm = defaults.setdefault("models", {})
for m in new_models:
    ref = f"{name}/{m['id']}"
    dm.setdefault(ref, {})
with open(path, "w") as f:
    json.dump(obj, f, ensure_ascii=False, indent=2)
    f.write("\\n")
print("OK")
"""

    output, _ = _run_remote_script(write_script, active, {
        "config_path": os.path.expanduser(config_path),
        "name": wizard.name,
        "base_url": wizard.base_url,
        "api_key": wizard.api_key,
        "api_type": wizard.api_type,
        "models": selected_models,
    })

    if "OK" in output:
        send(chat_id, t("api_success", lang).format(
            name=wizard.name, count=len(wizard.selected), api_type=wizard.api_type
        ), msg_id)
        send(chat_id, t("api_restarting", lang))
        r, _ = execute("openclaw gateway restart", active)
        msg = t("api_restart_ok", lang) if r.exit_code == 0 else t("api_restart_fail", lang)
        send(chat_id, msg)
    else:
        send(chat_id, t("api_fail", lang).format(error=output[:200]), msg_id)

    del _api_wizards[user_id]


# ── Remote script execution helper ───────────────────────────────────────────
def _run_remote_script(script: str, host_key: str | None, input_data: dict | None = None) -> tuple:
    """Run a Python script on a remote host via base64 temp files.
    Returns (output_string, ExecResult).
    """
    import base64
    script_b64 = base64.b64encode(script.encode()).decode()
    if input_data:
        data_json = json.dumps(input_data, ensure_ascii=False)
        data_b64 = base64.b64encode(data_json.encode()).decode()
        cmd = (
            f"echo '{data_b64}' | base64 -d > /tmp/tg-bot-input.json && "
            f"echo '{script_b64}' | base64 -d > /tmp/tg-bot-script.py && "
            f"python3 /tmp/tg-bot-script.py && "
            f"rm -f /tmp/tg-bot-input.json /tmp/tg-bot-script.py"
        )
    else:
        cmd = (
            f"echo '{script_b64}' | base64 -d > /tmp/tg-bot-script.py && "
            f"python3 /tmp/tg-bot-script.py && "
            f"rm -f /tmp/tg-bot-script.py"
        )
    result, _ = execute(cmd, host_key)
    return result.output.strip(), result


# ── API delete functions ─────────────────────────────────────────────────────
def _get_providers(user_id: int) -> dict:
    """Fetch all providers from config on active host."""
    active = get_active_host(user_id)
    config_path = _get_config_path(user_id)
    cmd = f'cat {shlex.quote(os.path.expanduser(config_path))} 2>/dev/null'
    result, _ = execute(cmd, active)
    if not result.output:
        return {}
    import json as _json
    try:
        cfg = _json.loads(result.output)
        return (((cfg.get("models") or {}).get("providers") or {}))
    except Exception:
        return {}


def _get_default_model_ref(user_id: int) -> str | None:
    """Get current default model reference."""
    active = get_active_host(user_id)
    config_path = _get_config_path(user_id)
    cmd = f'cat {shlex.quote(os.path.expanduser(config_path))} 2>/dev/null'
    result, _ = execute(cmd, active)
    if not result.output:
        return None
    import json as _json
    try:
        cfg = _json.loads(result.output)
        model_obj = (((cfg.get("agents") or {}).get("defaults") or {}).get("model"))
        if isinstance(model_obj, str):
            return model_obj
        if isinstance(model_obj, dict):
            return model_obj.get("primary")
    except Exception:
        pass
    return None


def _edit_message(chat_id: int, msg_id: int, text: str, buttons: list) -> None:
    """Edit a message's text and buttons."""
    try:
        requests.post(f"{API}/editMessageText", json={
            "chat_id": chat_id,
            "message_id": msg_id,
            "text": text,
            "reply_markup": {"inline_keyboard": buttons},
        }, timeout=10)
    except Exception as e:
        print(f"⚠️ Failed to edit message: {e}")


def _send_delete_type_menu(chat_id: int, msg_id: int, user_id: int, lang: str) -> None:
    """Show delete type selection menu."""
    buttons = [[
        {"text": t("api_del_provider", lang), "callback_data": "del:type:prov"},
    ], [
        {"text": t("api_del_model", lang), "callback_data": "del:type:model"},
    ], [
        {"text": "❌ 取消", "callback_data": "del:cancel"},
    ]]
    _edit_message(chat_id, msg_id, t("api_del_title", lang), buttons)


def _send_delete_prov_list(chat_id: int, msg_id: int, user_id: int, lang: str) -> None:
    """Show provider list for deletion."""
    providers = _get_providers(user_id)
    if not providers:
        _edit_message(chat_id, msg_id, "ℹ️ 没有可删除的 Provider", [[
            {"text": "🔙 返回", "callback_data": "action:api_delete"},
        ]])
        return

    buttons = []
    row = []
    for name, info in providers.items():
        models = info.get("models", [])
        count = len(models) if isinstance(models, list) else 0
        btn_text = f"{name} ({count})"
        row.append({"text": btn_text, "callback_data": f"delprov:sel:{name}"})
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([{"text": "❌ 取消", "callback_data": "action:api_delete"}])
    _edit_message(chat_id, msg_id, t("api_del_select_prov", lang), buttons)


def _handle_delprov_callback(query_id: str, chat_id: int, msg_id: int,
                              user_id: int, data: str, lang: str) -> None:
    """Handle delete provider callbacks."""
    parts = data.split(":", 2)
    action = parts[1] if len(parts) > 1 else ""
    name = parts[2] if len(parts) > 2 else ""

    if action == "sel":
        # Show confirmation
        answer_callback_query(query_id)
        providers = _get_providers(user_id)
        prov = providers.get(name, {})
        models = prov.get("models", [])
        count = len(models) if isinstance(models, list) else 0

        default_ref = _get_default_model_ref(user_id)
        default_msg = ""
        if default_ref and default_ref.startswith(name + "/"):
            # Need to switch default
            alt_refs = [r for r in _collect_all_refs(user_id) if not r.startswith(name + "/")]
            if alt_refs:
                default_msg = t("api_del_default_switch", lang).format(model=alt_refs[0])
            else:
                default_msg = t("api_del_no_alt", lang)
                _edit_message(chat_id, msg_id, default_msg, [[
                    {"text": "🔙 返回", "callback_data": "del:type:prov"},
                ]])
                return
        else:
            if default_ref:
                default_msg = t("api_del_default_safe", lang).format(model=default_ref)

        msg = t("api_del_confirm_prov", lang).format(
            name=name, count=count, default_msg=default_msg
        )
        buttons = [[
            {"text": "✅ 确认删除", "callback_data": f"delprov:yes:{name}"},
        ], [
            {"text": "❌ 取消", "callback_data": "del:type:prov"},
        ]]
        _edit_message(chat_id, msg_id, msg, buttons)

    elif action == "yes":
        answer_callback_query(query_id)
        _exec_delete_provider(chat_id, msg_id, user_id, name, lang)

    elif action == "cancel":
        answer_callback_query(query_id, t("api_del_cancelled", lang))
        _send_api_menu(chat_id, msg_id, lang)


def _collect_all_refs(user_id: int) -> list[str]:
    """Collect all available model references."""
    providers = _get_providers(user_id)
    refs = []
    for pname, pinfo in providers.items():
        for m in pinfo.get("models", []):
            if isinstance(m, dict) and m.get("id"):
                refs.append(f"{pname}/{m['id']}")
    return refs


def _exec_delete_provider(chat_id: int, msg_id: int, user_id: int,
                           name: str, lang: str) -> None:
    """Execute provider deletion on the active host."""
    active = get_active_host(user_id)
    config_path = _get_config_path(user_id)

    script = """import json, os
with open("/tmp/tg-bot-input.json") as f:
    inp = json.load(f)
path = inp["config_path"]
prov_name = inp["name"]
with open(path) as f: obj = json.load(f)
providers = obj.get("models", {}).get("providers", {})
agents = obj.get("agents", {})
defaults = agents.get("defaults", {})
dm = defaults.get("models", {})
model_obj = defaults.get("model")
primary = None
if isinstance(model_obj, str): primary = model_obj
elif isinstance(model_obj, dict): primary = model_obj.get("primary")
if primary and primary.startswith(prov_name + "/"):
    alt = [r for r in dm.keys() if not r.startswith(prov_name + "/")]
    if alt:
        if isinstance(model_obj, str): defaults["model"] = alt[0]
        elif isinstance(model_obj, dict): model_obj["primary"] = alt[0]
    else:
        print("NO_ALT")
        raise SystemExit(1)
for fk in ("modelFallback", "imageModelFallback"):
    val = defaults.get(fk)
    if isinstance(val, str) and val.startswith(prov_name + "/"):
        alt = [r for r in dm.keys() if not r.startswith(prov_name + "/")]
        if alt: defaults[fk] = alt[0]
removed = [r for r in list(dm.keys()) if r.startswith(prov_name + "/")]
for r in removed: dm.pop(r, None)
providers.pop(prov_name, None)
with open(path, "w") as f:
    json.dump(obj, f, ensure_ascii=False, indent=2)
    f.write("\\n")
print(f"OK:{len(removed)}")
"""

    output, _ = _run_remote_script(script, active, {"config_path": os.path.expanduser(config_path), "name": name})

    if output.startswith("OK:"):
        count = output.split(":")[1]
        send(chat_id, t("api_del_prov_ok", lang).format(name=name, count=count), msg_id)
        send(chat_id, t("api_restarting", lang))
        r, _ = execute("openclaw gateway restart", active)
        msg = t("api_restart_ok", lang) if r.exit_code == 0 else t("api_restart_fail", lang)
        send(chat_id, msg)
    elif output == "NO_ALT":
        send(chat_id, t("api_del_no_alt", lang), msg_id)
    else:
        send(chat_id, t("api_fail", lang).format(error=output[:200]), msg_id)


def _send_delete_model_prov_list(chat_id: int, msg_id: int, user_id: int, lang: str) -> None:
    """Show provider list for model-level deletion."""
    providers = _get_providers(user_id)
    if not providers:
        _edit_message(chat_id, msg_id, "ℹ️ 没有可操作的 Provider", [[
            {"text": "🔙 返回", "callback_data": "action:api_delete"},
        ]])
        return

    buttons = []
    row = []
    for name, info in providers.items():
        models = info.get("models", [])
        count = len(models) if isinstance(models, list) else 0
        row.append({"text": f"{name} ({count})", "callback_data": f"delmodel:prov:{name}"})
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([{"text": "❌ 取消", "callback_data": "action:api_delete"}])
    _edit_message(chat_id, msg_id, t("api_del_select_prov", lang), buttons)


def _handle_delmodel_callback(query_id: str, chat_id: int, msg_id: int,
                               user_id: int, data: str, lang: str) -> None:
    """Handle delete model callbacks."""
    parts = data.split(":", 2)
    action = parts[1] if len(parts) > 1 else ""
    name = parts[2] if len(parts) > 2 else ""

    if action == "prov":
        # Show model selection for this provider
        answer_callback_query(query_id)
        providers = _get_providers(user_id)
        prov = providers.get(name, {})
        models = prov.get("models", [])
        if not models:
            _edit_message(chat_id, msg_id, "ℹ️ 该 Provider 没有模型", [[
                {"text": "🔙 返回", "callback_data": "del:type:model"},
            ]])
            return

        # Initialize a temporary selection state (stored as ApiWizard for simplicity)
        model_names = [m.get("id", str(m)) if isinstance(m, dict) else str(m) for m in models]
        _api_wizards[user_id] = ApiWizard(
            step="delmodel_select", name=name,
            models=model_names, selected=set(), page=0
        )
        _send_delmodel_selection(chat_id, msg_id, user_id, lang)

    elif action == "toggle":
        if user_id not in _api_wizards:
            answer_callback_query(query_id, "⚠️ Session expired")
            return
        idx = int(parts[2])
        wizard = _api_wizards[user_id]
        if idx in wizard.selected:
            wizard.selected.discard(idx)
        else:
            wizard.selected.add(idx)
        answer_callback_query(query_id)
        _edit_delmodel_selection(chat_id, msg_id, user_id, lang)

    elif action == "page":
        if user_id not in _api_wizards:
            answer_callback_query(query_id, "⚠️ Session expired")
            return
        if parts[2] == "noop":
            answer_callback_query(query_id)
            return
        page = int(parts[2])
        _api_wizards[user_id].page = page
        answer_callback_query(query_id)
        _edit_delmodel_selection(chat_id, msg_id, user_id, lang)

    elif action == "confirm":
        if user_id not in _api_wizards:
            answer_callback_query(query_id, "⚠️ Session expired")
            return
        wizard = _api_wizards[user_id]
        if not wizard.selected:
            answer_callback_query(query_id, t("api_no_selection", lang))
            return
        answer_callback_query(query_id)
        _exec_delete_models(chat_id, msg_id, user_id, wizard.name, wizard, lang)

    elif action == "cancel":
        answer_callback_query(query_id, t("api_del_cancelled", lang))
        if user_id in _api_wizards:
            del _api_wizards[user_id]
        _send_api_menu(chat_id, msg_id, lang)


def _send_delmodel_selection(chat_id: int, msg_id: int, user_id: int, lang: str) -> None:
    """Send model selection for deletion."""
    wizard = _api_wizards[user_id]
    total_pages = max(1, (len(wizard.models) + MODELS_PER_PAGE - 1) // MODELS_PER_PAGE)
    start = wizard.page * MODELS_PER_PAGE
    end = min(start + MODELS_PER_PAGE, len(wizard.models))

    header = f"📦 {wizard.name} — 选择要删除的模型 (已选: {len(wizard.selected)})\n\n💡 点击选择/取消"

    buttons = []
    row = []
    for idx in range(start, end):
        mname = wizard.models[idx]
        display = mname[:25] + "..." if len(mname) > 25 else mname
        check = "✅" if idx in wizard.selected else "⬜"
        row.append({"text": f"{check} {display}", "callback_data": f"delmodel:toggle:{idx}"})
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    if total_pages > 1:
        nav = []
        if wizard.page > 0:
            nav.append({"text": "⬅️", "callback_data": f"delmodel:page:{wizard.page - 1}"})
        nav.append({"text": f"{wizard.page + 1}/{total_pages}", "callback_data": "delmodel:noop"})
        if wizard.page < total_pages - 1:
            nav.append({"text": "➡️", "callback_data": f"delmodel:page:{wizard.page + 1}"})
        buttons.append(nav)

    buttons.append([
        {"text": "🗑️ 删除选中", "callback_data": "delmodel:confirm"},
        {"text": "❌ 取消", "callback_data": "delmodel:cancel"},
    ])
    _edit_message(chat_id, msg_id, header, buttons)


def _edit_delmodel_selection(chat_id: int, msg_id: int, user_id: int, lang: str) -> None:
    """Edit model deletion selection in place."""
    wizard = _api_wizards[user_id]
    total_pages = max(1, (len(wizard.models) + MODELS_PER_PAGE - 1) // MODELS_PER_PAGE)
    start = wizard.page * MODELS_PER_PAGE
    end = min(start + MODELS_PER_PAGE, len(wizard.models))

    header = f"📦 {wizard.name} — 选择要删除的模型 (已选: {len(wizard.selected)})\n\n💡 点击选择/取消"

    buttons = []
    row = []
    for idx in range(start, end):
        mname = wizard.models[idx]
        display = mname[:25] + "..." if len(mname) > 25 else mname
        check = "✅" if idx in wizard.selected else "⬜"
        row.append({"text": f"{check} {display}", "callback_data": f"delmodel:toggle:{idx}"})
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    if total_pages > 1:
        nav = []
        if wizard.page > 0:
            nav.append({"text": "⬅️", "callback_data": f"delmodel:page:{wizard.page - 1}"})
        nav.append({"text": f"{wizard.page + 1}/{total_pages}", "callback_data": "delmodel:noop"})
        if wizard.page < total_pages - 1:
            nav.append({"text": "➡️", "callback_data": f"delmodel:page:{wizard.page + 1}"})
        buttons.append(nav)

    buttons.append([
        {"text": "🗑️ 删除选中", "callback_data": "delmodel:confirm"},
        {"text": "❌ 取消", "callback_data": "delmodel:cancel"},
    ])
    _edit_message(chat_id, msg_id, header, buttons)


def _exec_delete_models(chat_id: int, msg_id: int, user_id: int,
                         prov_name: str, wizard: ApiWizard, lang: str) -> None:
    """Execute model deletion on the active host."""
    active = get_active_host(user_id)
    config_path = _get_config_path(user_id)

    to_delete = [wizard.models[i] for i in sorted(wizard.selected)]

    script = """import json, os
with open("/tmp/tg-bot-input.json") as f:
    inp = json.load(f)
path = inp["config_path"]
prov_name = inp["prov_name"]
to_delete = inp["to_delete"]
with open(path) as f: obj = json.load(f)
providers = obj.get("models", {}).get("providers", {})
agents = obj.get("agents", {})
defaults = agents.get("defaults", {})
dm = defaults.get("models", {})
prov = providers.get(prov_name)
if not prov:
    print("NOT_FOUND")
    raise SystemExit(1)
models = prov.get("models", [])
new_models = [m for m in models if not (isinstance(m, dict) and m.get("id") in to_delete)]
prov["models"] = new_models
for mid in to_delete:
    dm.pop(f"{prov_name}/{mid}", None)
model_obj = defaults.get("model")
primary = None
if isinstance(model_obj, str): primary = model_obj
elif isinstance(model_obj, dict): primary = model_obj.get("primary")
if primary and any(primary == f"{prov_name}/{mid}" for mid in to_delete):
    alt = [r for r in dm.keys() if not any(r == f"{prov_name}/{d}" for d in to_delete)]
    if alt:
        if isinstance(model_obj, str): defaults["model"] = alt[0]
        elif isinstance(model_obj, dict): model_obj["primary"] = alt[0]
for fk in ("modelFallback", "imageModelFallback"):
    val = defaults.get(fk)
    if isinstance(val, str) and any(val == f"{prov_name}/{mid}" for mid in to_delete):
        alt = [r for r in dm.keys() if not any(r == f"{prov_name}/{d}" for d in to_delete)]
        if alt: defaults[fk] = alt[0]
if not new_models:
    providers.pop(prov_name, None)
    print(f"EMPTY:{prov_name}")
with open(path, "w") as f:
    json.dump(obj, f, ensure_ascii=False, indent=2)
    f.write("\\n")
print(f"OK:{len(to_delete)}")
"""

    output, _ = _run_remote_script(script, active, {
        "config_path": os.path.expanduser(config_path),
        "prov_name": prov_name,
        "to_delete": to_delete,
    })

    if output.startswith("OK:"):
        count = output.split(":")[1]
        send(chat_id, t("api_del_model_ok", lang).format(prov=prov_name, count=count), msg_id)
        if "EMPTY:" in output:
            empty_prov = output.split("EMPTY:")[1].split("\n")[0]
            send(chat_id, t("api_del_empty_prov", lang).format(prov=empty_prov))
        send(chat_id, t("api_restarting", lang))
        r, _ = execute("openclaw gateway restart", active)
        msg = t("api_restart_ok", lang) if r.exit_code == 0 else t("api_restart_fail", lang)
        send(chat_id, msg)
    else:
        send(chat_id, t("api_fail", lang).format(error=output[:200]), msg_id)

    if user_id in _api_wizards:
        del _api_wizards[user_id]


# ── Bot command handler ──────────────────────────────────────────────────────
def _handle_bot_command(chat_id: int, reply_to: int, text: str, user_id: int | None, lang: str) -> None:
    hosts = load_hosts()

    if text == "/cwd":
        active = get_active_host(user_id) if user_id else None
        target = active or get_default_host(hosts) or LOCAL_HOST_KEY
        send(chat_id, t("current_dir", lang).format(dir=read_cwd(target)), reply_to)

    elif text.startswith("/help"):
        send(chat_id, t("help_text", lang), reply_to)

    elif text.startswith("/lang"):
        parts = text.split()
        if len(parts) < 2:
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

    # ── Multi-host commands ──
    elif text == "/hosts":
        send_hosts_menu(chat_id, reply_to, user_id, lang)

    elif text.startswith("/use"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            send(chat_id, "📝 用法: /use <主机名>", reply_to)
            return
        name = parts[1].strip()
        if name not in hosts:
            send(chat_id, t("host_not_found", lang).format(name=name), reply_to)
            return
        if user_id is not None:
            set_active_host(user_id, name)
        send(chat_id, t("host_switched", lang).format(name=name), reply_to)

    elif text == "/addhost":
        _add_wizards[user_id] = HostAddWizard(step="name")
        send(chat_id, t("host_prompt_name", lang), reply_to)

    elif text.startswith("/delhost"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            send(chat_id, "📝 用法: /delhost <主机名>", reply_to)
            return
        name = parts[1].strip()
        if name == LOCAL_HOST_KEY:
            send(chat_id, t("host_remove_local", lang), reply_to)
            return
        if remove_host(hosts, name):
            # Clear active host if it was the deleted one
            if user_id and _active_hosts.get(user_id) == name:
                del _active_hosts[user_id]
            send(chat_id, t("host_removed", lang).format(name=name), reply_to)
        else:
            send(chat_id, t("host_not_found", lang).format(name=name), reply_to)

    elif text == "/disconnect":
        close_all_ssh()
        send(chat_id, t("ssh_disconnected", lang), reply_to)

    elif text == "/api":
        _send_api_menu(chat_id, reply_to, lang)

    # ── OpenClaw shortcuts ──
    elif text == "/openclaw_start":
        active = get_active_host(user_id) if user_id else None
        send(chat_id, t("openclaw_start", lang), reply_to)
        result, _ = execute("env XDG_RUNTIME_DIR=/run/user/0 openclaw gateway start", active)
        send(chat_id, f"[Gateway Start]\n{result.format()}", reply_to, code=True)

    elif text == "/openclaw_stop":
        active = get_active_host(user_id) if user_id else None
        send(chat_id, t("openclaw_stop", lang), reply_to)
        result, _ = execute("env XDG_RUNTIME_DIR=/run/user/0 openclaw gateway stop", active)
        send(chat_id, f"[Gateway Stop]\n{result.format()}", reply_to, code=True)

    elif text == "/openclaw_restart":
        active = get_active_host(user_id) if user_id else None
        send(chat_id, t("openclaw_restart", lang), reply_to)
        result, _ = execute("env XDG_RUNTIME_DIR=/run/user/0 openclaw gateway restart", active)
        send(chat_id, f"[Gateway Restart]\n{result.format()}", reply_to, code=True)

    elif text == "/cancel":
        send(chat_id, "💡 当前没有正在进行的交互流程", reply_to)

    else:
        send(chat_id, t("unknown_command", lang), reply_to)


# ── Main loop ────────────────────────────────────────────────────────────────
def main() -> None:
    _set_telegram_menu()
    print(t("bot_starting", DEFAULT_LANG))
    default = get_default_host(load_hosts()) or LOCAL_HOST_KEY
    print(f"📂 Default host: {default}")
    if ALLOWED_USER == 0:
        print(t("bot_no_user", DEFAULT_LANG))

    offset = 0
    while True:
        try:
            resp = requests.get(
                f"{API}/getUpdates",
                params={"offset": offset, "timeout": 30,
                        "allowed_updates": '["message", "callback_query"]'},
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
                cb = update.get("callback_query")
                if cb:
                    handle_callback_query(cb)

        except requests.exceptions.ReadTimeout:
            continue
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(3)


if __name__ == "__main__":
    main()
