import os
import threading
import asyncio
import staypresent
from flask import Flask, request, jsonify, render_template

from bot_logic import (
    build_messages,
    ask_openrouter,
    get_user_status,
    OWNER_ID,
    FRIEND_IDS,
    VIP_IDS,
)

app = Flask(__name__)   # ← __name__, блядь, а не __main__. Запомни уже.


@app.route("/playground", methods=["GET"])
def playground():
    return render_template("playground.html")


@app.route("/api/playground", methods=["POST"])
def api_playground():
    data = request.get_json(silent=True) or {}

    try:
        user_id = int(data["user_id"])
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "user_id обязателен и должен быть числом"}), 400

    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message пуст"}), 400

    display_name = (data.get("display_name") or f"user_{user_id}").strip()
    messages = build_messages(user_id, display_name, message)

    try:
        answer = asyncio.run(ask_openrouter(messages))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "answer": answer,
        "role": get_user_status(user_id),
        "display_name": display_name,
    })


@app.route("/api/whoami", methods=["GET"])
def api_whoami():
    return jsonify({
        "owner": OWNER_ID,
        "friends": FRIEND_IDS,
        "vip": VIP_IDS,
    })


def start_bot():
    """Бот под присмотром StayPresent, в отдельном потоке, без своего порта."""
    try:
        staypresent.run(
            "l6.py",
            restart_on_crash=True,
            max_restarts=5,
            restart_delay=2.0,
            # port= НЕ передаём, сука! Иначе он займёт порт и Flask сдохнет.
        )
    except Exception as e:
        print(f"[StayPresent] пиздец, бот упал: {e}", flush=True)


if __name__ == "__main__":
    # Запускаем бота в фоне, daemon=True — умрёт вместе с Flask
    threading.Thread(target=start_bot, daemon=True).start()

    # Flask обслуживает API на порту, который даёт Render
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
