import os
import staypresent

url = os.getenv("RENDER_EXTERNAL_URL")

if not url:
    raise RuntimeError("RENDER_EXTERNAL_URL не задан (запуск не на Render?)")

staypresent.web.json({"status": "running"})
staypresent.cron(url, interval=240)
staypresent.run(
    "l6.py",
    port=int(os.getenv("PORT", 8080)),
    restart_on_crash=True,
    max_restarts=5,
    restart_delay=2.0,
)
