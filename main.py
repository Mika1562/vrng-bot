import os
import staypresent


if __name__ == "__main__":
    # Публичный health-эндпоинт: /health всегда отдаёт {"status": "ok"}
    staypresent.web.json({
        "status": "running",
        "service": "kate-discord-bot",
    })

    staypresent.run(
        "l6.py",
        port=int(os.getenv("PORT", 8080)),  # ← вот это поднимает сервер
        restart_on_crash=True,
        max_restarts=5,
        restart_delay=2.0,
    )
