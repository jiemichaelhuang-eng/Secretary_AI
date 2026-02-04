# Discord Welcome Bot (Python)

Simple bot that posts a welcome message in the server's System Channel when a member joins.

## Setup

1. Create a Discord application and bot in the Developer Portal.
2. Enable **Server Members Intent** for your bot.
3. Invite the bot to your server with the appropriate permissions.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python bot.py
```

## Notes

- The bot posts in the server **System Channel**. If none is set, it does nothing.
- Ensure the bot has permission to send messages in the System Channel.
