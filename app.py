# app.py
from datetime import datetime
from flask import (
    Flask,
    send_file,
    abort,
    render_template_string,
    request,
    redirect,
    url_for,
    flash,
)
import mimetypes
import os
import tempfile
import zipfile
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("FILE_SHARE_SECRET", "lan-file-share")

def _max_upload_bytes(default: int = 4 * 1024 * 1024 * 1024) -> int:
    value = os.environ.get("FILE_SHARE_MAX_UPLOAD")
    try:
        return int(value) if value else default
    except (TypeError, ValueError):
        return default


app.config["MAX_CONTENT_LENGTH"] = _max_upload_bytes()

SHARED_DIR = os.path.join(os.path.dirname(__file__), "shared")
ROOT_PATH = os.path.realpath(SHARED_DIR)
os.makedirs(ROOT_PATH, exist_ok=True)
mimetypes.init()

def _zip_spool_bytes(default_mb: int = 256) -> int:
    value = os.environ.get("FILE_SHARE_ZIP_SPOOL_MB")
    try:
        parsed = int(value)
        if parsed > 0:
            return parsed * 1024 * 1024
    except (TypeError, ValueError):
        pass
    return default_mb * 1024 * 1024

ZIP_SPOOL_THRESHOLD = _zip_spool_bytes()

# HTML template for file browser
HTML_PAGE = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <title>LAN File Share</title>
    <style>
      :root { color-scheme: light dark; }
      * { box-sizing: border-box; }
      body { font-family: "Inter", "Segoe UI", system-ui, sans-serif; margin: 0; background: #0f172a; color: #e2e8f0; padding: 32px; }
      @media (max-width: 640px) { body { padding: 16px; } }
      a { color: #38bdf8; text-decoration: none; }
      a:hover { text-decoration: underline; }
      h2 { margin: 0; font-size: 28px; }
      .app-shell { max-width: 1200px; margin: auto; background: rgba(15, 23, 42, 0.75); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 16px; padding: 28px; box-shadow: 0 30px 80px rgba(15, 23, 42, 0.45); backdrop-filter: blur(12px); }
      .header { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 16px; align-items: center; }
      .breadcrumbs { font-size: 14px; color: #94a3b8; }
      .breadcrumbs strong { color: #f8fafc; }
      .toolbar { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 20px; align-items: center; }
      .search { flex: 1 1 260px; position: relative; }
      .search input { width: 100%; padding: 10px 36px 10px 12px; border-radius: 8px; border: 1px solid rgba(148, 163, 184, 0.4); background: rgba(15, 23, 42, 0.6); color: inherit; }
      .search span { position: absolute; right: 12px; top: 50%; transform: translateY(-50%); font-size: 12px; color: #94a3b8; }
      .upload { flex: 0 0 280px; padding: 12px 16px; border-radius: 12px; border: 1px dashed rgba(148, 163, 184, 0.5); background: rgba(15, 23, 42, 0.6); display: flex; flex-direction: column; gap: 8px; }
      .upload label { font-weight: 600; font-size: 14px; color: #f8fafc; }
      .upload input { font-size: 14px; }
      .upload button { cursor: pointer; border: none; padding: 8px 12px; border-radius: 8px; background: linear-gradient(135deg, #38bdf8, #6366f1); color: #0f172a; font-weight: 600; }
      .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin-top: 24px; }
      .stat { border-radius: 12px; padding: 16px; background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(148, 163, 184, 0.25); }
      .stat-value { font-size: 24px; font-weight: 700; color: #f8fafc; }
      .stat-label { font-size: 13px; color: #94a3b8; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.05em; }
      table { border-collapse: collapse; width: 100%; margin-top: 24px; overflow: hidden; border-radius: 14px; border: 1px solid rgba(148, 163, 184, 0.3); background: rgba(15, 23, 42, 0.7); }
      th, td { padding: 14px 16px; text-align: left; font-size: 14px; }
      thead { background: rgba(148, 163, 184, 0.1); }
      tbody tr { border-top: 1px solid rgba(148, 163, 184, 0.15); transition: background 0.18s ease; }
      tbody tr:hover { background: rgba(56, 189, 248, 0.08); }
      .entry-name { display: flex; align-items: center; gap: 8px; font-weight: 600; color: #f8fafc; }
      .badge { font-size: 12px; padding: 2px 8px; border-radius: 999px; background: rgba(148, 163, 184, 0.2); color: #94a3b8; }
      .badge.folder { background: rgba(45, 212, 191, 0.15); color: #5eead4; }
      .actions { display: flex; flex-wrap: wrap; gap: 8px; }
      .btn { padding: 6px 10px; border-radius: 8px; border: 1px solid rgba(148, 163, 184, 0.4); font-size: 13px; font-weight: 600; color: inherit; background: transparent; text-decoration: none; }
      .btn:hover { border-color: #38bdf8; color: #38bdf8; }
      .messages { list-style: none; padding: 0; margin: 20px 0 0; }
      .messages li { margin: 6px 0; padding: 10px 12px; border-radius: 10px; font-weight: 600; }
      .messages .success { background: #e6ffed; color: #035b17; }
      .messages .error { background: #ffecec; color: #b20202; }
      .hint { margin-top: 24px; color: #94a3b8; font-size: 14px; line-height: 1.5; }
      code { background: rgba(15, 23, 42, 0.8); padding: 3px 6px; border-radius: 6px; border: 1px solid rgba(148, 163, 184, 0.2); color: #e2e8f0; }
      .empty { text-align: center; padding: 48px 0; color: #94a3b8; }
    </style>
  </head>
  <body>
    <div class="app-shell">
      <div class="header">
        <div>
          <h2>📂 LAN File Share</h2>
          <div class="breadcrumbs">
            {% for crumb in breadcrumbs %}
              {% if loop.last %}
                <strong>{{ crumb.name }}</strong>
              {% else %}
                <a href="{{ url_for('browse', req_path=crumb.path) }}">{{ crumb.name }}</a> /
              {% endif %}
            {% endfor %}
          </div>
        </div>
        <div>
          <strong>Serving:</strong> <code>{{ root_path }}</code>
        </div>
      </div>

      {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
          <ul class="messages">
            {% for category, msg in messages %}
              <li class="{{ category }}">{{ msg }}</li>
            {% endfor %}
          </ul>
        {% endif %}
      {% endwith %}

      <div class="toolbar">
        <div class="search">
          <input type="search" id="filter" placeholder="Filter files and folders…" aria-label="Filter files and folders">
          <span>⌘/Ctrl + K</span>
        </div>
        <form class="upload" action="{{ url_for('upload', req_path=req_path) }}" method="post" enctype="multipart/form-data">
          <label>Upload to this folder</label>
          <input type="file" name="files" multiple required>
          <button type="submit">Upload</button>
        </form>
      </div>

      <div class="stats">
        <div class="stat">
          <div class="stat-value">{{ stats.folders }}</div>
          <div class="stat-label">Folders</div>
        </div>
        <div class="stat">
          <div class="stat-value">{{ stats.files }}</div>
          <div class="stat-label">Files</div>
        </div>
        <div class="stat">
          <div class="stat-value">{{ stats.total_size }}</div>
          <div class="stat-label">Visible Size</div>
        </div>
      </div>

      <table id="entries">
        <thead>
          <tr>
            <th>Name</th>
            <th>Type</th>
            <th>Size</th>
            <th>Modified</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {% if req_path %}
            <tr data-entry>
              <td colspan="5"><a href="{{ url_for('browse', req_path=parent_path) }}">⬆️ Up one level</a></td>
            </tr>
          {% endif %}
          {% for entry in entries %}
            <tr data-entry data-name="{{ entry.name | lower }}">
              <td>
                <div class="entry-name">
                  {% if entry.is_dir %}
                    📁 <a href="{{ url_for('browse', req_path=entry.rel_path) }}">{{ entry.name }}</a>
                    <span class="badge folder">Folder</span>
                  {% else %}
                    📄 <a href="{{ url_for('view', req_path=entry.rel_path) }}">{{ entry.name }}</a>
                    <span class="badge">{{ entry.type }}</span>
                  {% endif %}
                </div>
              </td>
              <td>{{ entry.type }}</td>
              <td>{{ entry.size_display }}</td>
              <td>{{ entry.mtime }}</td>
              <td>
                <div class="actions">
                  {% if entry.is_dir %}
                    <a class="btn" href="{{ url_for('browse', req_path=entry.rel_path) }}">Open</a>
                    <a class="btn" href="{{ url_for('download', req_path=entry.rel_path) }}">Zip</a>
                  {% else %}
                    <a class="btn" href="{{ url_for('view', req_path=entry.rel_path) }}">Preview</a>
                    <a class="btn" href="{{ url_for('download', req_path=entry.rel_path) }}">Download</a>
                  {% endif %}
                </div>
              </td>
            </tr>
          {% else %}
            <tr><td class="empty" colspan="5">Folder is empty.</td></tr>
          {% endfor %}
        </tbody>
      </table>

      <p class="hint">Share this address on your LAN: <code>http://{{ request.host }}/</code></p>
      <p class="hint">Moving very large files? Copy any download link and run <code>curl -C - -O &lt;download-url&gt;</code> (or another resumable downloader) to keep transfers going if your network drops.</p>
    </div>

    <script>
      const filterInput = document.getElementById("filter");
      const rows = Array.from(document.querySelectorAll("tr[data-entry]"));
      function applyFilter(value) {
        const needle = value.trim().toLowerCase();
        rows.forEach((row) => {
          if (!needle) {
            row.style.display = "";
            return;
          }
          const name = row.dataset.name || "";
          row.style.display = name.includes(needle) ? "" : "none";
        });
      }
      filterInput?.addEventListener("input", (event) => {
        applyFilter(event.target.value);
      });
      window.addEventListener("keydown", (event) => {
        if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
          event.preventDefault();
          filterInput?.focus();
        }
      });
    </script>
  </body>
</html>
"""

# HTML template for viewing files
VIEW_PAGE = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <title>Viewing {{ fname }}</title>
    <style>
      body { font-family: system-ui, Arial; margin: 20px; }
      video, audio, img, iframe { max-width: 90%; display: block; margin-top: 20px; }
      pre { background: #eee; padding: 10px; border-radius: 6px; overflow-x: auto; }
    </style>
  </head>
  <body>
    <h2>📄 Viewing: {{ fname }}</h2>
    <p>
      <a href="{{ url_for('download', req_path=rel_path) }}">⬇ Download</a> ·
      <a href="{{ url_for('browse', req_path=parent_path) }}">← Back to folder</a>
    </p>
    {% if ext in ['.mp4', '.webm', '.ogg'] %}
      <video controls preload="metadata">
        <source src="{{ url_for('serve_file', req_path=rel_path) }}">
      </video>
    {% elif ext in ['.mp3', '.wav', '.ogg'] %}
      <audio controls preload="metadata">
        <source src="{{ url_for('serve_file', req_path=rel_path) }}">
      </audio>
    {% elif ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'] %}
      <img src="{{ url_for('serve_file', req_path=rel_path) }}" alt="{{ fname }}">
    {% elif ext in ['.txt', '.log', '.md', '.py', '.json', '.csv'] %}
      <pre>{{ text_content }}</pre>
    {% elif ext in ['.pdf'] %}
      <iframe src="{{ url_for('serve_file', req_path=rel_path) }}" width="90%" height="600"></iframe>
    {% else %}
      <p>No preview available. <a href="{{ url_for('download', req_path=rel_path) }}">Download instead</a>.</p>
    {% endif %}
  </body>
</html>
"""

def clean_subpath(raw_path: str) -> str:
    if not raw_path:
        return ""
    cleaned = raw_path.replace("\\", "/").strip("/")
    return "" if cleaned in ("", ".") else cleaned


def safe_path(subpath: str = "") -> str:
    candidate = os.path.realpath(os.path.join(ROOT_PATH, subpath))
    if os.path.commonpath([candidate, ROOT_PATH]) != ROOT_PATH:
        abort(404)
    return candidate


def path_join(base: str, leaf: str) -> str:
    if not base:
        return leaf
    return "/".join([base, leaf])


def human_size(num: int) -> str:
    step = 1024.0
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num < step or unit == "TB":
            return f"{num:.1f} {unit}" if unit != "B" else f"{int(num)} B"
        num /= step
    return f"{num:.1f} TB"


def build_breadcrumbs(subpath: str):
    crumbs = [{"name": "Home", "path": ""}]
    if not subpath:
        return crumbs
    parts = subpath.split("/")
    acc = []
    for part in parts:
        acc.append(part)
        crumbs.append({"name": part, "path": "/".join(acc)})
    return crumbs


def list_entries(abs_path: str, rel_path: str):
    entries = []
    names = sorted(
        os.listdir(abs_path),
        key=lambda n: (not os.path.isdir(os.path.join(abs_path, n)), n.lower()),
    )
    for name in names:
        full = os.path.join(abs_path, name)
        rel = path_join(rel_path, name)
        is_dir = os.path.isdir(full)
        try:
            stat = os.stat(full)
        except OSError:
            continue
        mime, _ = mimetypes.guess_type(full)
        entries.append(
            {
                "name": name,
                "rel_path": rel,
                "is_dir": is_dir,
                "type": "Folder" if is_dir else (mime or "File"),
                "size_display": "—" if is_dir else human_size(stat.st_size),
                "size_bytes": 0 if is_dir else stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            }
        )
    return entries


@app.route("/", defaults={"req_path": ""})
@app.route("/browse/<path:req_path>")
def browse(req_path: str):
    rel_path = clean_subpath(req_path)
    abs_path = safe_path(rel_path)
    if not os.path.exists(abs_path):
        abort(404)
    if os.path.isfile(abs_path):
        return redirect(url_for("view", req_path=rel_path))
    entries = list_entries(abs_path, rel_path)
    file_count = sum(1 for entry in entries if not entry["is_dir"])
    folder_count = len(entries) - file_count
    total_bytes = sum(entry["size_bytes"] for entry in entries if not entry["is_dir"])
    stats = {
        "files": file_count,
        "folders": folder_count,
        "total_size": human_size(total_bytes),
    }
    parent = "/".join(rel_path.split("/")[:-1]) if rel_path else ""
    return render_template_string(
        HTML_PAGE,
        entries=entries,
        breadcrumbs=build_breadcrumbs(rel_path),
        req_path=rel_path,
        parent_path=parent,
        stats=stats,
        root_path=ROOT_PATH,
    )


@app.route("/upload", defaults={"req_path": ""}, methods=["POST"])
@app.route("/upload/<path:req_path>", methods=["POST"])
def upload(req_path: str):
    rel_path = clean_subpath(req_path)
    abs_path = safe_path(rel_path)
    if os.path.isfile(abs_path):
        abort(400)
    os.makedirs(abs_path, exist_ok=True)
    files = request.files.getlist("files")
    saved = 0
    for incoming in files:
        filename = secure_filename(incoming.filename)
        if not filename:
            continue
        incoming.save(os.path.join(abs_path, filename))
        saved += 1
    if saved:
        flash(f"Uploaded {saved} file(s).", "success")
    else:
        flash("No files were uploaded.", "error")
    return redirect(url_for("browse", req_path=rel_path))


@app.route("/view/<path:req_path>")
def view(req_path: str):
    rel_path = clean_subpath(req_path)
    abs_path = safe_path(rel_path)
    if not os.path.exists(abs_path) or os.path.isdir(abs_path):
        return redirect(url_for("browse", req_path=rel_path))
    _, ext = os.path.splitext(abs_path)
    ext = ext.lower()
    text_content = ""
    if ext in [".txt", ".log", ".md", ".py", ".json", ".csv"]:
        try:
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as handle:
                text_content = handle.read(8000)
        except OSError:
            text_content = "[Error reading file]"
    parent = "/".join(rel_path.split("/")[:-1]) if rel_path else ""
    return render_template_string(
        VIEW_PAGE,
        fname=os.path.basename(abs_path),
        rel_path=rel_path,
        parent_path=parent,
        ext=ext,
        text_content=text_content,
    )


@app.route("/file/<path:req_path>")
def serve_file(req_path: str):
    rel_path = clean_subpath(req_path)
    abs_path = safe_path(rel_path)
    if not os.path.exists(abs_path) or os.path.isdir(abs_path):
        abort(404)
    return send_file(abs_path, conditional=True)


@app.route("/download/<path:req_path>")
def download(req_path: str):
    rel_path = clean_subpath(req_path)
    abs_path = safe_path(rel_path)
    if not os.path.exists(abs_path):
        abort(404)
    if os.path.isdir(abs_path):
        folder_name = os.path.basename(abs_path.rstrip(os.sep)) or "shared"
        archive = tempfile.SpooledTemporaryFile(max_size=ZIP_SPOOL_THRESHOLD)
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zip_buffer:
            for root, dirs, files in os.walk(abs_path):
                for file_name in files:
                    full = os.path.join(root, file_name)
                    arcname = os.path.join(folder_name, os.path.relpath(full, abs_path))
                    zip_buffer.write(full, arcname)
                if not files and not dirs:
                    relative_root = os.path.relpath(root, abs_path)
                    arcdir = f"{folder_name}/" if relative_root == "." else os.path.join(folder_name, relative_root) + "/"
                    zip_buffer.writestr(arcdir, "")
        archive.seek(0)
        return send_file(
            archive,
            as_attachment=True,
            download_name=f"{folder_name}.zip",
            mimetype="application/zip",
            max_age=0,
        )
    return send_file(
        abs_path,
        as_attachment=True,
        download_name=os.path.basename(abs_path),
        conditional=True,
        max_age=0,
    )


if __name__ == "__main__":
    print("➡ Drop files and folders inside the 'shared/' directory.")
    print("➡ Open http://localhost:5000 on this machine.")
    print("➡ Share http://<your-ip>:5000 with others on the network.")
    app.run(host="0.0.0.0", port=5000, debug=False)
