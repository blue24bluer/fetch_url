import os
import json
import time
import logging
from flask import Flask, request, jsonify
import yt_dlp

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

app = Flask(__name__)

def convert_cookies():
    """تحويل youtube.json إلى cookies.txt بصيغة Netscape"""
    if not os.path.exists('youtube.json'):
        return None
    try:
        with open('youtube.json', 'r', encoding='utf-8') as f:
            cookies_data = json.load(f)
        
        cookie_path = 'cookies.txt'
        with open(cookie_path, 'w', encoding='utf-8') as f:
            f.write("# Netscape HTTP Cookie File\n")
            for c in cookies_data:
                domain = c.get('domain', '')
                path = c.get('path', '/')
                secure = 'TRUE' if c.get('secure') else 'FALSE'
                name = c.get('name', '')
                value = c.get('value', '')
                expires = int(c.get('expirationDate', c.get('expiry', time.time() + 31536000)))
                flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n")
        return cookie_path
    except:
        return None

@app.route('/api/download', methods=['GET', 'POST'])
def download():
    url = request.values.get('url')
    if not url:
        return jsonify({"status": "error", "message": "Missing URL"}), 400

    cookie_file = convert_cookies()

    # خيارات مرنة جداً لتجنب الحظر
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'check_formats': False, # لا تتحقق من الصيغ، فقط اجلب البيانات
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'web'],
                'skip': ['dash', 'hls'] # تقليل الضغط على السيرفر
            }
        }
    }

    if cookie_file:
        ydl_opts['cookiefile'] = cookie_file

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # استخراج المعلومات (بدون تحديد جودة مسبقاً لتجنب الخطأ)
            info = ydl.extract_info(url, download=False)
            
            if not info:
                return jsonify({"status": "error", "message": "Could not extract info"}), 500

            # مصفوفة لتخزين الروابط المباشرة المتاحة
            formats = info.get('formats', [])
            
            # محاولة البحث عن رابط مباشر (فيديو + صوت) - عادة itag 18 أو 22
            # نبحث عن صيغة mp4 تحتوي على فيديو وصوت معاً
            direct_url = None
            
            # الفلترة اليدوية: نبحث عن الروابط التي لا تحتاج دمج (Single File)
            # هذه هي الطريقة الوحيدة التي تعمل بثبات على Render بدون FFmpeg
            for f in reversed(formats):
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('url'):
                    direct_url = f.get('url')
                    break
            
            # إذا لم نجد، نأخذ أي رابط متوفر (حتى لو HLS)
            if not direct_url and formats:
                for f in reversed(formats):
                    if f.get('url'):
                        direct_url = f.get('url')
                        break

            if not direct_url:
                return jsonify({"status": "error", "message": "No direct URL found"}), 404

            return jsonify({
                "status": "success",
                "title": info.get('title'),
                "url": direct_url,
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration'),
                "msg": "Format found by manual fallback"
            })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e).split(';')[0]
        }), 500

@app.route('/')
def index():
    return "Fetcher is Online"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
