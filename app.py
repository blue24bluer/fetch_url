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
    """تحويل youtube.json إلى صيغة Netscape (cookies.txt) التي يفهمها yt-dlp"""
    if not os.path.exists('youtube.json'):
        return None
    
    try:
        with open('youtube.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        cookie_path = 'cookies.txt'
        with open(cookie_path, 'w', encoding='utf-8') as f:
            f.write("# Netscape HTTP Cookie File\n")
            for cookie in data:
                # معالجة اختلاف أسماء الحقول حسب أداة التصدير
                domain = cookie.get('domain', '')
                path = cookie.get('path', '/')
                secure = 'TRUE' if cookie.get('secure', False) else 'FALSE'
                name = cookie.get('name', '')
                value = cookie.get('value', '')
                
                # وقت انتهاء الصلاحية
                expires = cookie.get('expirationDate', cookie.get('expiry'))
                if not expires:
                    expires = int(time.time()) + 31536000 # سنة للأمام افتراضياً
                
                flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{int(expires)}\t{name}\t{value}\n")
        return cookie_path
    except Exception as e:
        logger.error(f"Cookie Conversion Error: {e}")
        return None

@app.route('/api/download', methods=['GET', 'POST'])
def download_media():
    url = request.values.get('url')
    m_type = request.values.get('type', 'video') # video, audio
    
    if not url:
        return jsonify({"status": "error", "message": "No URL provided"}), 400

    # إعداد صيغة الملف المطلوبة
    format_selector = 'bestaudio/best' if m_type == 'audio' else 'best'

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': format_selector,
        'noplaylist': True,
        # استخدام Android/iOS لتجنب خطأ Format not available في السيرفرات
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios'],
            }
        }
    }

    # معالجة الكوكيز
    cookie_file = convert_cookies()
    if cookie_file:
        ydl_opts['cookiefile'] = cookie_file

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # استخراج المعلومات بدون تحميل
            info = ydl.extract_info(url, download=False)
            
            final_url = info.get('url')
            
            # محاولة احتياطية للحصول على الرابط إذا لم يكن في الجذر
            if not final_url:
                formats = info.get('formats', [])
                if formats:
                    # نختار آخر صيغة متاحة لأنها غالباً الأفضل
                    final_url = formats[-1].get('url')

            return jsonify({
                "status": "success",
                "title": info.get('title'),
                "url": final_url,
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration')
            })

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Download Error: {error_msg}")
        return jsonify({
            "status": "error", 
            "message": error_msg.split(';')[0].replace('ERROR: ', ''),
            "details": "Ensure cookies are fresh and youtube.json is in root"
        }), 400

@app.route('/')
def home():
    return "App is Running"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
