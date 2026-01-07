from flask import Flask, request, jsonify, send_from_directory
import yt_dlp
import os
import uuid

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

@app.route("/api/download")
def download():
    url = request.args.get("url")
    dtype = request.args.get("type", "video")
    q = request.args.get("q", "720")
    if not url:
        return jsonify({"error": "missing url"}), 400
    try:
        uid = str(uuid.uuid4())
        outtmpl = os.path.join(DOWNLOAD_DIR, f"{uid}.%(ext)s")
        ydl_opts = {
            "outtmpl": outtmpl,
            "quiet": True,
            "noplaylist": True
        }
        if dtype == "audio":
            ydl_opts["format"] = "bestaudio/best"
        else:
            ydl_opts["format"] = f"bestvideo[height<={q}]+bestaudio/best/best"
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
