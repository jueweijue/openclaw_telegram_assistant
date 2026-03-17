#!/usr/bin/env python3
"""Command executor — local and remote (SSH) execution with unified interface."""

import os
import shlex
import signal
import subprocess
from dataclasses import dataclass

import paramiko

from hosts import load_hosts, LOCAL_HOST_KEY

# ── Config ───────────────────────────────────────────────────────────────────
TIMEOUT = int(os.environ.get("CMD_TIMEOUT", "30"))
DEFAULT_CWD = os.path.expanduser("~")
CWD_DIR = "/tmp/tg-shell-bot"
os.makedirs(CWD_DIR, exist_ok=True)


@dataclass
class ExecResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool

    @property
    def output(self) -> str:
        return self.stdout or self.stderr or ""

    def format(self) -> str:
        """Format result for display, including exit code / timeout markers."""
        text = self.output or "(无输出)"
        if self.timed_out:
            text += "\n❌ 命令超时，已终止"
        elif self.exit_code != 0:
            text += f"\n[exit code: {self.exit_code}]"
        return text


# ── Per-host CWD ─────────────────────────────────────────────────────────────
def _cwd_file(host_key: str) -> str:
    safe = host_key.replace("/", "_").replace("..", "_")
    return os.path.join(CWD_DIR, f"{safe}.cwd")


def read_cwd(host_key: str) -> str:
    path = _cwd_file(host_key)
    try:
        with open(path) as f:
            return f.read().strip() or DEFAULT_CWD
    except OSError:
        return DEFAULT_CWD


def write_cwd(host_key: str, path: str) -> None:
    with open(_cwd_file(host_key), "w") as f:
        f.write(path)


# ── Local executor ───────────────────────────────────────────────────────────
def execute_local(cmd: str, host_key: str = LOCAL_HOST_KEY) -> ExecResult:
    """Execute command locally with persistent cwd, timeout protection."""
    cwd = read_cwd(host_key)
    try:
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
            return ExecResult(stdout="", stderr="", exit_code=-1, timed_out=True)

        return ExecResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=proc.returncode,
            timed_out=(proc.returncode == 124),
        )
    except Exception as e:
        return ExecResult(stdout="", stderr=str(e), exit_code=-1, timed_out=False)


# ── SSH connection pool ──────────────────────────────────────────────────────
_ssh_pool: dict[str, paramiko.SSHClient] = {}


def _get_ssh_client(host_info: dict) -> paramiko.SSHClient:
    """Get or create an SSH connection. Reuses from pool."""
    key = f"{host_info['user']}@{host_info['host']}:{host_info.get('port', 22)}"

    if key in _ssh_pool:
        client = _ssh_pool[key]
        # Verify connection is alive
        try:
            transport = client.get_transport()
            if transport and transport.is_active():
                return client
        except Exception:
            pass
        # Stale connection, remove
        try:
            client.close()
        except Exception:
            pass
        del _ssh_pool[key]

    # Create new connection
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    connect_kwargs = {
        "hostname": host_info["host"],
        "port": host_info.get("port", 22),
        "username": host_info["user"],
        "timeout": 10,
    }

    if host_info.get("key_file"):
        key_path = os.path.expanduser(host_info["key_file"])
        connect_kwargs["key_filename"] = key_path
    elif host_info.get("password"):
        connect_kwargs["password"] = host_info["password"]
    else:
        # Try default SSH key
        default_key = os.path.expanduser("~/.ssh/id_rsa")
        if os.path.exists(default_key):
            connect_kwargs["key_filename"] = default_key

    client.connect(**connect_kwargs)
    _ssh_pool[key] = client
    return client


def close_all_ssh() -> None:
    """Close all pooled SSH connections."""
    for client in _ssh_pool.values():
        try:
            client.close()
        except Exception:
            pass
    _ssh_pool.clear()


def close_ssh(host_info: dict) -> None:
    """Close a specific SSH connection."""
    key = f"{host_info['user']}@{host_info['host']}:{host_info.get('port', 22)}"
    client = _ssh_pool.pop(key, None)
    if client:
        try:
            client.close()
        except Exception:
            pass


# ── Remote executor ──────────────────────────────────────────────────────────
def execute_remote(cmd: str, host_info: dict, host_key: str) -> ExecResult:
    """Execute command on remote host via SSH with persistent cwd."""
    cwd = read_cwd(host_key)
    try:
        client = _get_ssh_client(host_info)
        # Wrap with cd and timeout
        wrapped = f"cd {shlex.quote(cwd)} && timeout {TIMEOUT} {cmd}"
        stdin, stdout, stderr = client.exec_command(
            wrapped,
            timeout=TIMEOUT + 5,
        )
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")

        return ExecResult(
            stdout=out,
            stderr=err,
            exit_code=exit_code,
            timed_out=(exit_code == 124),
        )
    except Exception as e:
        return ExecResult(stdout="", stderr=str(e), exit_code=-1, timed_out=False)


# ── Unified interface ────────────────────────────────────────────────────────
def execute(cmd: str, host_key: str | None = None) -> tuple[ExecResult, str]:
    """
    Execute a command on the specified host (or default).
    Returns (ExecResult, resolved_host_key).
    """
    hosts = load_hosts()

    # Resolve host
    if host_key is None:
        from hosts import get_default_host
        host_key = get_default_host(hosts) or LOCAL_HOST_KEY

    if host_key not in hosts:
        return ExecResult(stdout="", stderr=f"❌ 主机不存在: {host_key}", exit_code=-1, timed_out=False), host_key

    info = hosts[host_key]

    if info["type"] == "local":
        return execute_local(cmd, host_key), host_key
    else:
        return execute_remote(cmd, info, host_key), host_key


def handle_cd(text: str, host_key: str) -> tuple[bool, str]:
    """
    Handle cd commands with per-host cwd persistence.
    Returns (handled, message).
    """
    if any(op in text for op in ("&&", ";", "|", "||")):
        return False, ""  # Compound command, let shell handle it

    parts = text.split()
    target = parts[1] if len(parts) > 1 else "~"

    if target == "-":
        return True, "⚠️ cd - 不支持（无 OLDPWD）"

    target = os.path.expanduser(target)
    if not os.path.isabs(target):
        target = os.path.join(read_cwd(host_key), target)

    # For remote hosts, we can't resolve symlinks locally, but we can normalize
    if host_key == LOCAL_HOST_KEY:
        target = os.path.realpath(target)

    if host_key == LOCAL_HOST_KEY and not os.path.isdir(target):
        return True, f"❌ 目录不存在或无权限: {parts[1] if len(parts) > 1 else '~'}"

    write_cwd(host_key, target)
    return True, f"📂 当前目录: {target}"
