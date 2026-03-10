"""Flask-backend for the resume fact-checker web UI."""

import os
import sys
import tempfile

from flask import Flask, request, jsonify, send_file

# Allow importing project modules from parent directory
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from main import run_pipeline  # noqa: E402
from config import LLM_MODEL   # noqa: E402

app = Flask(__name__)

ALLOWED_EXTENSIONS = {".txt", ".pdf"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

INDEX_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")


@app.route("/")
def index():
    return send_file(INDEX_PATH)


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "model": LLM_MODEL})


@app.route("/api/check", methods=["POST"])
def check_resume():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": f"Unsupported file type '{ext}'. Allowed: .txt, .pdf"}), 400

    # Read content to check size
    content = file.read()
    if len(content) > MAX_FILE_SIZE:
        return jsonify({"error": f"File too large ({len(content)} bytes). Max: 5 MB"}), 400

    tmp = None
    try:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        tmp.write(content)
        tmp.close()

        report = run_pipeline(tmp.name, verbose=False)
        return jsonify(report)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if tmp and os.path.exists(tmp.name):
            os.unlink(tmp.name)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8080)
