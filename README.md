# yoink-bot

telegram bot that downloads video or audio from a youtube link.

## features

- downloads video up to 720p as mp4
- extracts audio as mp3 via ffmpeg
- inline keyboard format selector
- optional telegram user allowlist
- configurable file size threshold

## quick start

1. clone the repository and step into the directory:
```bash
git clone https://github.com/example/yoink-bot.git
cd yoink-bot
```

2. create the configuration file:
```bash
cp .env.example .env
```

3. set your bot token in `.env`:
```bash
BOT_TOKEN=your_token_here
```

4. launch the container:
```bash
docker compose up -d --build
```

5. inspect logs:
```bash
docker compose logs -f
```

## configuration

| variable | description | default |
| --- | --- | --- |
| `BOT_TOKEN` | telegram bot token from @botfather | required |
| `ALLOWED_USER_IDS` | comma-separated telegram user ids | empty (all allowed) |
| `MAX_FILE_MB` | maximum download size in megabytes | 50 |

## project layout

```text
.env.example
.gitignore
compose.yaml
Dockerfile
main.py
README.md
requirements.txt
```

## legal note

this project is for personal use only. users are responsible for complying with applicable copyright laws and third-party platform terms of service.

## license

MIT