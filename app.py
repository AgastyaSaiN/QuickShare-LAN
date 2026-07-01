import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from flask import Flask, abort, jsonify, render_template, request, send_from_directory
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "shared_files"
PAD_FILE = BASE_DIR / "shared_pad.txt"
MAX_PAD_LENGTH = 200_000

UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("QUICKLAN_SECRET", uuid4().hex),
    MAX_CONTENT_LENGTH=2 * 1024 * 1024 * 1024,
    UPLOAD_FOLDER=str(UPLOAD_DIR),
)
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

pad_lock = threading.Lock()
pad_text = PAD_FILE.read_text(encoding="utf-8") if PAD_FILE.exists() else ""


def file_details(path):
    stat = path.stat()
    return {
        "name": path.name,
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(
            stat.st_mtime, tz=timezone.utc
        ).isoformat(),
    }


def available_filename(filename):
    candidate = UPLOAD_DIR / filename
    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1

    while candidate.exists():
        candidate = UPLOAD_DIR / f"{stem} ({counter}){suffix}"
        counter += 1

    return candidate


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/files")
def list_files():
    files = [
        file_details(path)
        for path in UPLOAD_DIR.iterdir()
        if path.is_file() and not path.name.startswith(".")
    ]
    files.sort(key=lambda item: item["modified"], reverse=True)
    return jsonify(files)


@app.post("/api/upload")
def upload_files():
    incoming_files = request.files.getlist("files")
    if not incoming_files:
        return jsonify({"error": "No files were selected."}), 400

    saved = []
    for incoming in incoming_files:
        filename = secure_filename(incoming.filename or "")
        if not filename:
            continue

        destination = available_filename(filename)
        incoming.save(destination)
        saved.append(file_details(destination))

    if not saved:
        return jsonify({"error": "None of the selected files had valid names."}), 400

    socketio.emit("files_changed")
    return jsonify({"files": saved}), 201


@app.get("/files/<path:filename>")
def download_file(filename):
    if Path(filename).name != filename or not (UPLOAD_DIR / filename).is_file():
        abort(404)
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=True)


@app.delete("/api/files/<path:filename>")
def delete_file(filename):
    if Path(filename).name != filename:
        abort(404)

    target = UPLOAD_DIR / filename
    if not target.is_file():
        abort(404)

    target.unlink()
    socketio.emit("files_changed")
    return jsonify({"deleted": filename})


@socketio.on("connect")
def handle_connect():
    emit("pad_update", {"text": pad_text})


@socketio.on("pad_update")
def handle_pad_update(data):
    global pad_text

    text = data.get("text", "") if isinstance(data, dict) else ""
    if not isinstance(text, str):
        return
    text = text[:MAX_PAD_LENGTH]

    with pad_lock:
        pad_text = text
        PAD_FILE.write_text(pad_text, encoding="utf-8")

    emit("pad_update", {"text": pad_text}, broadcast=True, include_self=False)


@app.errorhandler(413)
def file_too_large(_error):
    return jsonify({"error": "Upload is larger than the 2 GB server limit."}), 413


if __name__ == "__main__":
    port = int(os.environ.get("QUICKLAN_PORT", "57321"))
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=False,
        allow_unsafe_werkzeug=True,
    )
