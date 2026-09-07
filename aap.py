"""
SkillTrack Maharashtra — Backend API (SIH26135)
Phase 3: Authentication
"""

from functools import wraps
from flask import Flask, request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash

import db
from db import get_db, now_iso, new_token, init_db, seed_if_empty

app = Flask(__name__)


def err(message, code=400):
    """Consistent error response shape used across every endpoint."""
    return jsonify({"error": message}), code


def auth_required(role=None):
    """
    Decorator that protects a route. Checks for:
        Authorization: Bearer <token>
    Looks up which user that token belongs to, and (optionally) checks
    they have the right role. Attaches the user to `g.user` so the route
    function can use it.
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return err("Missing or invalid Authorization header.", 401)
            token = auth_header.split(" ", 1)[1].strip()

            conn = get_db()
            user = conn.execute("SELECT * FROM users WHERE api_token=?", (token,)).fetchone()
            conn.close()

            if not user:
                return err("Invalid or expired token.", 401)
            if role and user["role"] != role:
                return err("Forbidden — wrong role for this endpoint.", 403)

            g.user = user
            return f(*args, **kwargs)
        return wrapper
    return decorator


def user_to_dict(user):
    return {"id": user["id"], "username": user["username"], "role": user["role"]}


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "SkillTrack Maharashtra API"})


@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json(force=True, silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return err("username and password are required.")

    conn = get_db()
    existing = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if existing:
        conn.close()
        return err("That username is already taken.", 409)

    token = new_token()
    conn.execute(
        "INSERT INTO users (username, password_hash, role, api_token, created_at) VALUES (?,?,?,?,?)",
        (username, generate_password_hash(password), "trainee", token, now_iso())
    )
    conn.commit()
    user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()

    return jsonify({"token": token, "user": user_to_dict(user), "next_step": "consent"}), 201


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(force=True, silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        conn.close()
        return err("Invalid username or password.", 401)

    # Issue a fresh token on every login — invalidates any old session
    token = new_token()
    conn.execute("UPDATE users SET api_token=? WHERE id=?", (token, user["id"]))
    conn.commit()
    conn.close()

    return jsonify({"token": token, "user": user_to_dict(user)})


@app.route("/api/auth/logout", methods=["POST"])
@auth_required()
def logout():
    conn = get_db()
    conn.execute("UPDATE users SET api_token=? WHERE id=?", (new_token(), g.user["id"]))
    conn.commit()
    conn.close()
    return jsonify({"message": "Logged out. Token invalidated."})


@app.route("/api/auth/me", methods=["GET"])
@auth_required()
def me():
    return jsonify({"user": user_to_dict(g.user)})


if __name__ == "__main__":
    init_db()
    seed_if_empty()
    app.run(debug=True, host="0.0.0.0", port=5000)
