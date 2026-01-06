import os
from flask import Flask, request, jsonify
import yt_dlp

app = Flask(__name__)

@app.route('/api/download', methods=['POST'])
def download_media():
    data = request.get_json()
    url = data.get('url')
    media_type = data.get('type')

    ydl_opts = {
        'cookiefile': 'youtube.json',
        'quiet': True,
        'noplaylist': True,
        'socket_timeout': 10
    }

    if media_type == 'audio':
        ydl_opts['format'] = 'bestaudio/best'
    else:
        ydl_opts['format'] = 'best'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return jsonify({
                "status": "success",
                "title": info.get('title'),
                "download_url": info.get('url'),
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration'),
                "extension": info.get('ext')
            })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
