"""Flask app factory for the Ecosystem Research dashboard."""

from flask import Flask
from pathlib import Path


def create_app(default_chain=None):
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )
    app.config["DEFAULT_CHAIN"] = default_chain or "near"
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB upload limit

    from .app import bp
    app.register_blueprint(bp)

    from .pipeline_api import pipeline_bp
    app.register_blueprint(pipeline_bp)

    return app
