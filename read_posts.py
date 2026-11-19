import os
import sqlite3
import secrets
from contextlib import closing
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, session, url_for, redirect
from authlib.integrations.flask_client import OAuth

app = Flask(__name__)
db_path = Path.home() / "doubleho-dev.sqlite3"

app.secret_key = os.environ["FLASK_SECRET_KEY"]
oauth = OAuth(app)
github = oauth.register(
    name = "github",
    client_id = os.environ["GITHUB_CLIENT_ID"],
    client_secret=os.environ["GITHUB_CLIENT_SECRET"],
    authorize_url = "https://github.com/login/oauth/authorize",
    access_token_url = "https://github.com/login/oauth/access_token",
    api_base_url="https://api.github.com/",
    client_kwargs={"code_challenge_method": "S256"},
)

app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("BLOG_COOKIE_SECURE") == "1"

@app.get("/api/posts")
def get_posts():
    with closing(sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)) as connection:
        rows = connection.execute("SELECT title, body FROM posts").fetchall()
    posts = [{"title": title, "body": body} for title, body in rows]
    return jsonify(posts)

@app.get("/")
def home():
    return send_from_directory(app.root_path, "index.html")

@app.get("/style.css")
def stylesheet():
    return send_from_directory(app.root_path, "style.css")

@app.post("/api/posts")
def create_post():
    user_id = session.get("github_user_id")
    if user_id is None:
        return jsonify(error="Sign on required."), 401
    if user_id != int(os.environ["BLOG_OWNER_ID"]):
        return jsonify(error="Owner access required."), 403
    expected_token = session.get("csrf_token")
    received_token = request.headers.get("X-CSRF-Token", "")
    if not expected_token or not secrets.compare_digest(expected_token, received_token):
        return jsonify(error="Invalid CSRF token."), 403
    if os.environ.get("BLOG_ENABLE_WRITES") != "1":
        return jsonify(error="Writing is disabled."), 403
    
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Send a JSON object."), 400

    title = data.get("title")
    body = data.get("body")
    if not isinstance(title, str) or not isinstance(body, str) or not title.strip() or not body.strip():
        return jsonify(error="Title and body are required."), 400

    with closing(sqlite3.connect(db_path.as_uri() + "?mode=rw", uri=True)) as connection:
        connection.execute(
            "INSERT INTO posts (title, body) VALUES (?, ?)",
            (title, body),
        )
        connection.commit()

    return jsonify(title=title, body=body), 201

@app.get("/auth/github")
def github_login():
    callback_url = os.environ.get("GITHUB_CALLBACK_URL") or url_for("github_callback", _external=True)
    return github.authorize_redirect(callback_url)

@app.get("/auth/github/callback")
def github_callback():
    token = github.authorize_access_token()
    response = github.get("user", token=token)
    response.raise_for_status()
    user = response.json()
    session.clear()
    session["github_user_id"] = user["id"]
    return redirect(url_for("home"))

@app.get("/api/me")
def get_me():
    user_id = session.get("github_user_id")
    is_owner = user_id == int(os.environ["BLOG_OWNER_ID"])
    if user_id is not None and "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return jsonify(
        authenticated = user_id is not None,
        is_owner = is_owner,
        csrf_token = session.get("csrf_token") if user_id is not None else None,
    )

@app.post("/auth/logout")
def logout():
    expected_token = session.get("csrf_token")
    received_token = request.headers.get("X-CSRF-Token", "")
    if not expected_token or not secrets.compare_digest(expected_token, received_token):
        return jsonify(error="Invalid CSRF token."), 403
    session.clear()
    return jsonify(message="Signed out.")