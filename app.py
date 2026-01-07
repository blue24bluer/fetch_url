import os
import json
import time
import logging
from flask import Flask, request, jsonify
import yt_dlp

logging.basicConfig(level=logging.WARNING)
app = Flask(__name__)

def get_cookie_file():
    if not os.path.exists('youtube.json'):
        return None
    try:
        if os.path.exists('cookies.txt') and os.path.getmtime('cookies.txt') > os.path.getmtime('youtube.json'):
            return 'cookies.txt'
        with open('youtube.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        with open('cookies.txt', 'w', encoding='utf-8') as f:
            f.write("# Netscape HTTP Cookie File\n")
            for c in data:
                f.write(
                    f"{c.get('domain')}\tTRUE\t{c.get('path')}\t"
                    f"{'TRUE' if c.get('secure') else 'FALSE'}\t"
                    f"{int(c.get('expirationDate', time.time() + 9999999))}\t"
                    f"{c.get('name')}\t{c.get('value')}\n"
                )
        return 'cookies.txt'
    except:
        return None

@app.route('/api/download', methods=['GET', 'POST'])
def download_media():
    url = request.values.get('url')
    media_type = request.values.get('type', 'video')

    if not url:
        return jsonify({"status": "error", "message": "Url missing"}), 400

    if media_type == 'audio':
        fmt = 'bestaudio/best'
    else:
        fmt = 'bestvideo+bestaudio/best'

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': fmt,
        'noplaylist': True,
        'simulate': True,
        'forceurl': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web']
            }
        }
    }

    cookie_path = get_cookie_file()
    if cookie_path:
        ydl_opts['cookiefile'] = cookie_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return jsonify({"status": "error", "message": "Extraction failed"}), 400

            final_url = info.get('url')
            if not final_url and info.get('formats'):
                for f in reversed(info['formats']):
                    if f.get('url'):
                        final_url = f['url']
                        break

            protocol = "http"
            if final_url and ".m3u8" in final_url:
                protocol = "hls"

            return jsonify({
                "status": "success",
                "title": info.get('title'),
                "url": final_url,
                "protocol": protocol,
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration')
            })

    except Exception as e:
        err = str(e)
        if "Sign in" in err:
            return jsonify({"status": "auth_error", "message": "Cookies Invalid"}), 403
        return jsonify({"status": "error", "message": err}), 400

@app.route('/')
def home():
    return "Ready"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
