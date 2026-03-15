# Telegram Shell Bot

极简 Telegram Bot，收到消息 → 执行 shell 命令 → 返回结果。

整个项目只有一个依赖 (`requests`)、一个文件 (`bot.py`)。

## 快速开始

```bash
# 1. 安装依赖
pip3 install requests

# 2. 配置
cp .env.example .env
# 编辑 .env，填入你的 BOT_TOKEN 和 ALLOWED_USER

# 3. 运行
bash run.sh
```

## 获取 Bot Token

1. 在 Telegram 找 @BotFather
2. 发送 `/newbot`，按提示创建
3. 拿到 token 填入 `.env`

## 获取你的 User ID

1. 在 Telegram 找 @userinfobot
2. 发送任意消息，它会返回你的 user id
3. 填入 `.env` 的 `ALLOWED_USER`

## 开机自启 (systemd)

```bash
cp tg-shell-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now tg-shell-bot
```

## 安全提醒

⚠️ **必须设置 ALLOWED_USER**，否则任何人都能远程执行你的服务器命令。
