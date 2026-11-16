# Paxyo Order bot (@paxorder_bot) on Fly.io.
# One shared-cpu-1x 512 MB machine, US region, always on.
# Webhook mode: Telegram pushes updates to https://<app>.fly.dev/<token-path>.
# Secrets (never in this repo) are set as Fly secrets, copied from Render:
#   TELEGRAM_BOT_TOKEN, BOT_API_SECRET, GEMINI_API_KEY,
#   DEEPSEEK_API_KEY, GROQ_API_KEY, ZEN_API_KEY, GLM_API_KEY,
#   QWEN_API_KEY, OPENROUTER_API_KEY, KILO_API_KEY,
#   GOOGLE_CLOUD_TTS_API_KEY, ADMIN_TELEGRAM_IDS,
#   WEBHOOK_URL=https://paxorder-bot.fly.dev
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "bot.py"]
