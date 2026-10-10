import os
import asyncio
import staypresent
from flask import request, jsonify

from bot_logic import build_messages, ask_openrouter, get_user_status

# Flask-приложение, которое обслуживает staypresent
app = Flask(_main_)

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
    """Отдаёт владельца/друзей/VIP — чтобы страница подставила ID по кнопке."""
    from bot_logic import OWNER_ID, FRIEND_IDS, VIP_IDS
    return jsonify({
        "owner": OWNER_ID,
        "friends": FRIEND_IDS,
        "vip": VIP_IDS,
    })

staypresent.web.html("templates/playground.html", path="/playground")

staypresent.run(
    "l6.py",
    port=int(os.getenv("PORT", 8080)),
    restart_on_crash=True,
    max_restarts=5,
    restart_delay=2.0,
)
