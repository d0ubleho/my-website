import os
import sqlite3
from contextlib import closing
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__)
db_path = Path.home() / "doubleho-dev.sqlite3"

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