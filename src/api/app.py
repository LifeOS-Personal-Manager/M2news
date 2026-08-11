from __future__ import annotations

import json
from pathlib import Path

from flask import Flask, jsonify, redirect, send_from_directory

from src.config import Settings, load_settings


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or load_settings()
    data_dir = settings.output_dir.resolve()
    app = Flask(__name__)

    @app.get("/news/<date>.json")
    def news_json(date: str):
        path = data_dir / f"{date}.json"
        if not path.exists():
            return jsonify({"error": "not_found", "date": date}), 404
        return send_from_directory(data_dir, path.name, mimetype="application/json")

    @app.get("/news/<date>.html")
    def news_html(date: str):
        path = data_dir / f"{date}.html"
        if not path.exists():
            return jsonify({"error": "not_found", "date": date}), 404
        return send_from_directory(data_dir, path.name, mimetype="text/html")

    @app.get("/news/latest")
    def news_latest():
        latest_path = data_dir / "latest.json"
        if not latest_path.exists():
            return jsonify({"error": "not_found"}), 404
        payload = json.loads(latest_path.read_text(encoding="utf-8"))
        return redirect(f"/news/{payload['date']}.html", code=302)

    @app.get("/news/latest.json")
    def news_latest_json():
        path = data_dir / "latest.json"
        if not path.exists():
            return jsonify({"error": "not_found"}), 404
        return send_from_directory(data_dir, path.name, mimetype="application/json")

    return app


app = create_app()
