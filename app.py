import os
import json
from flask import Flask, request, jsonify
import yt_dlp

app = Flask(__name__)

def convert_cookies():
    try:
        if not os.path.exists('youtube.json'):
            return None
        with open('youtube.json', 'r') as f:
            cookies = json.load(f)
        
        cookie_path = '/tmp/cookies.txt'
        with open(cookie_path, 'w') as f:
            f.write("# Netscape HTTP Cookie File\n")
            for c in cookies:
                domain = c.get('domain', '')
                flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                path = c.get('path', '/')
                secure = 'TRUE' if c.get('secure') else 'FALSE'
                expiry = str(int(c.get('expirationDate', c.get('expiry', 0))))
                name = c.get('name', '')
                value = c.get('value', '')
                f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expiry}\t{name}\t{value}\n")
        return cookie_path
    except:
        return None

@app.route('/api/download', methods=['GET', 'POST'])
def download_media():
    # Support both Query Parameters (GET) and JSON Body (POST)
    if request.method == 'POST':
        data = request.get_json() or {}
        url = data.get('url')
        quality = data.get('q', '720')
        m_type = data.get('type', 'mp4')
    else:
        url = request.args.get('url')
        quality = request.args.get('q', '720')
        m_type = request.args.get('type', 'mp4')

    if not url:
        return jsonify({"status": "error", "message": "No URL provided"}), 400

    cookie_file = convert_cookies()

    ydl_opts = {
        'quiet': True,
        'noplaylist': True,
        'socket_timeout': 30,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    }

    if cookie_file:
        ydl_opts['cookiefile'] = cookie_file

    # Handle Formats logic to avoid 'Requested format is not available'
    # Without FFmpeg on server, we must request pre-merged formats 'best' not 'bestvideo+bestaudio'
    if m_type in ['mp3', 'audio']:
        ydl_opts['format'] = 'bestaudio/best'
    else:
        # Try to find a single file with both video and audio up to requested height
        # Fallback to 'best' if specific height fails
        ydl_opts['format'] = f'best[height<={quality}][ext=mp4]/best[ext=mp4]/best'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Smart URL extraction
            download_url = info.get('url')
            if not download_url and 'formats' in info:
                # Find the requested format url manually if automatic extraction missed
                download_url = info['formats'][-1]['url']

            return jsonify({
                "status": "success",
                "title": info.get('title'),
                "download_url": download_url,
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration'),
                "extension": info.get('ext') or ('mp3' if m_type == 'audio' else 'mp4'),
                "requested_quality": quality
            })
            
    except Exception as e:
        error_msg = str(e)
        if "Sign" in error_msg or "challenge" in error_msg:
             return jsonify({
                "status": "error", 
                "message": "Server IP blocked or cookie invalid. Try updating youtube.json",
                "detail": error_msg
            }), 403
        return jsonify({"status": "error", "message": error_msg}), 400

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
