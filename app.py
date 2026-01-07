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
    # التعامل مع كل من طلبات GET و POST
    if request.method == 'POST':
        data = request.get_json() or {}
        url = data.get('url')
        quality = data.get('q', '720')
        m_type = data.get('type', 'video') # default video
    else:
        # مثال: ?url=...&q=720&type=mp3
        url = request.args.get('url')
        quality = request.args.get('q', '720')
        m_type = request.args.get('type', 'video')

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

    # [protocol^=http] هي الأهم، فهي تمنع ظهور روابط m3u8 وتجبر النظام على الرابط المباشر
    if m_type in ['mp3', 'audio']:
        # نحاول الحصول على m4a مباشر (جودة صوت أفضل ورابط واحد)
        ydl_opts['format'] = 'bestaudio[ext=m4a][protocol^=http]/bestaudio[protocol^=http]'
    else:
        # نحاول الحصول على فيديو mp4 جاهز (صوت وصورة مدمجين) برابط مباشر
        # Render لا يدعم الدمج، لذا يجب طلب الملف المدمج من المصدر
        ydl_opts['format'] = f'best[ext=mp4][height<={quality}][protocol^=http]/best[ext=mp4][protocol^=http]/best[protocol^=http]'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            final_url = info.get('url')
            
            # تأكيد إضافي: إذا كان الرابط لا يزال m3u8 (نادر الحدوث مع الإعدادات أعلاه) نبحث يدوياً
            if not final_url or '.m3u8' in final_url:
                for f in info.get('formats', []):
                    if f.get('protocol', '').startswith('http') and f.get('ext') == 'mp4':
                         final_url = f.get('url')
                         break

            return jsonify({
                "status": "success",
                "title": info.get('title'),
                "download_url": final_url,
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration'),
                "extension": info.get('ext') or ('mp3' if m_type == 'audio' else 'mp4'),
                "quality": quality,
                "type": m_type
            })
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
