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
            
        with open('cookies.txt', 'w') as f:
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
        return 'cookies.txt'
    except Exception:
        return None

@app.route('/api/download', methods=['POST'])
def download_media():
    data = request.get_json()
    url = data.get('url')
    media_type = data.get('type')

    cookie_file = convert_cookies()

    ydl_opts = {
        'quiet': True,
        'noplaylist': True,
        'socket_timeout': 30,
        # حذفنا player_client: android لأنه كان يسبب مشكلة "Requested format is not available"
        # نعتمد الآن على الكوكيز وملفات تعريف المتصفح القياسية
    }

    if cookie_file:
        ydl_opts['cookiefile'] = cookie_file

    if media_type == 'audio':
        # استخدام m4a يضمن وجود رابط مباشر غالباً
        ydl_opts['format'] = 'bestaudio[ext=m4a]/bestaudio/best'
    else:
        ydl_opts['format'] = 'best[ext=mp4]/best'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # محاولة العثور على رابط مباشر في حال كان الرابط الرئيسي manifest
            download_url = info.get('url')
            if 'formats' in info and not download_url:
                # محاولة يدوية لاستخراج أفضل رابط في حال الفشل
                download_url = info['formats'][-1].get('url')

            return jsonify({
                "status": "success",
                "title": info.get('title'),
                "download_url": download_url,
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration'),
                "extension": info.get('ext')
            })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
