#!/usr/bin/env python3
"""Host registry — manage remote and local hosts."""

import json
import os

HOSTS_FILE = os.environ.get("HOSTS_FILE", os.path.join(os.path.dirname(__file__), "hosts.json"))
LOCAL_HOST_KEY = "local"


def _default_hosts() -> dict:
    """Default registry: local machine only."""
    return {
        LOCAL_HOST_KEY: {
            "name": LOCAL_HOST_KEY,
            "type": "local",
            "default": True,
        }
    }


def load_hosts() -> dict:
    """Load host registry from file. Returns default local host if file missing."""
    try:
        with open(HOSTS_FILE) as f:
            data = json.load(f)
            if not data:
                return _default_hosts()
            return data
    except (OSError, json.JSONDecodeError):
        return _default_hosts()


def save_hosts(hosts: dict) -> None:
    """Persist host registry to file."""
    with open(HOSTS_FILE, "w") as f:
        json.dump(hosts, f, indent=2, ensure_ascii=False)


def get_default_host(hosts: dict) -> str | None:
    """Return the key of the default host."""
    for key, info in hosts.items():
        if info.get("default"):
            return key
    # Fallback: first key or "local"
    if LOCAL_HOST_KEY in hosts:
        return LOCAL_HOST_KEY
    return next(iter(hosts), None)


def set_default_host(hosts: dict, name: str) -> bool:
    """Set a host as default. Returns True on success."""
    if name not in hosts:
        return False
    for key in hosts:
        hosts[key]["default"] = (key == name)
    save_hosts(hosts)
    return True


def add_host(hosts: dict, name: str, host: str, port: int = 22,
             user: str = "root", key_file: str | None = None,
             password: str | None = None, config_path: str | None = None) -> bool:
    """Add a remote host. Returns True on success, False if name exists."""
    if name in hosts:
        return False
    entry = {
        "name": name,
        "type": "remote",
        "host": host,
        "port": port,
        "user": user,
    }
    if key_file:
        entry["key_file"] = key_file
    if password:
        entry["password"] = password
    entry["config_path"] = config_path or "~/.openclaw/openclaw.json"
    hosts[name] = entry
    save_hosts(hosts)
    return True


def remove_host(hosts: dict, name: str) -> bool:
    """Remove a host. Cannot remove 'local'. Returns True on success."""
    if name == LOCAL_HOST_KEY or name not in hosts:
        return False
    was_default = hosts[name].get("default", False)
    del hosts[name]
    # If we removed the default, make local default
    if was_default and LOCAL_HOST_KEY in hosts:
        hosts[LOCAL_HOST_KEY]["default"] = True
    save_hosts(hosts)
    return True


def format_host_list(hosts: dict, active: str | None = None) -> str:
    """Format host list for display."""
    lines = []
    for key, info in hosts.items():
        marker = ""
        if info.get("default"):
            marker += " ⭐"
        if key == active:
            marker += " 👈"
        if info["type"] == "local":
            lines.append(f"  📍 {key}{marker}  (本机)")
        else:
            lines.append(
                f"  🖥️ {key}{marker}  "
                f"{info['user']}@{info['host']}:{info.get('port', 22)}"
            )
    return "\n".join(lines) if lines else "  (无主机)"
