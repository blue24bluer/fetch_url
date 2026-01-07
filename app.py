```python
from flask import Flask, request, jsonify, send_from_directory
import yt_dlp
import json
import os
import uuid

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
COOKIE_TXT = os.path.join(BASE_DIR, "cookies.txt")
YOUTUBE_JSON = os.path.join(BASE_DIR, "youtube.json")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def json_to_cookies(json_path, txt_path):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    cookies = []
    if isinstance(data, list):
        for c in data:
            domain = c.get("domain", "")
            path = c.get("path", "/")
            secure = "TRUE" if c.get("secure", False) else "FALSE"
            expires = str(int(c.get("expirationDate", 0)))
            name = c.get("name", "")
            value = c.get("value", "")
            http_only = "FALSE"
            cookies.append("\t".join([domain, http_only, path, secure, expires, name, value]))
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(cookies))

@app.route("/api/download")
def download():
    url = request.args.get("url")
    dtype = request.args.get("type", "video")
    q = request.args.get("q", "720")
    if not url:
        return jsonify({"error": "missing url"}), 400
    try:
        if os.path.exists(YOUTUBE_JSON):
            json_to_cookies(YOUTUBE_JSON, COOKIE_TXT)
        uid = str(uuid.uuid4())
        outtmpl = os.path.join(DOWNLOAD_DIR, f"{uid}.%(ext)s")
        ydl_opts = {
            "outtmpl": outtmpl,
            "cookiefile": COOKIE_TXT if os.path.exists(COOKIE_TXT) else None,
            "quiet": True,
            "noplaylist": True
        }
        if dtype == "audio":
            ydl_opts.update({
                "format": "bestaudio/best"
            })
        else:
            ydl_opts.update({
                "format": f"bestvideo[height<={q}]+bestaudio/best/best"
            })
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
        return jsonify({
            "status": "ok",
            "download": request.host_url + "file/" + os.path.basename(filename)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/file/<name>")
def file(name):
    return send_from_directory(DOWNLOAD_DIR, name, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
```
