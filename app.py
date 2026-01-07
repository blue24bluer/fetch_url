import os
import json
import time
import logging
from flask import Flask, request, jsonify
import yt_dlp

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

app = Flask(__name__)

def get_cookies_path():
    """تجهيز ملف الكوكيز"""
    json_path = 'youtube.json'
    cookie_path = 'cookies.txt'
    
    if not os.path.exists(json_path):
        return None

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        with open(cookie_path, 'w', encoding='utf-8') as f:
            f.write("# Netscape HTTP Cookie File\n")
            for c in data:
                dom = c.get('domain', '')
                path = c.get('path', '/')
                sec = 'TRUE' if c.get('secure', False) else 'FALSE'
                name = c.get('name', '')
                val = c.get('value', '')
                exp = int(c.get('expirationDate', c.get('expiry', time.time() + 31536000)))
                flag = 'TRUE' if dom.startswith('.') else 'FALSE'
                f.write(f"{dom}\t{flag}\t{path}\t{sec}\t{exp}\t{name}\t{val}\n")
        return cookie_path
    except:
        return None

@app.route('/api/download', methods=['GET', 'POST'])
def download_media():
    url = request.values.get('url')
    if not url: return jsonify({"error": "No URL"}), 400

    cookie_file = get_cookies_path()

    # الإعدادات الحاسمة: عدم تحديد format لتجنب الفلترة والحذف التلقائي
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'source_address': '0.0.0.0',  # إجبار IPv4
        'noplaylist': True,
        'socket_timeout': 30,
        # إزالة قيد best للسماح بأي نتيجة
        # استخدام android لأنه الأكثر تسامحاً مع العناوين المحظورة
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios'],
            }
        }
    }

    if cookie_file:
        ydl_opts['cookiefile'] = cookie_file

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # استخراج كافة البيانات دون تحميل أو فلترة
            info = ydl.extract_info(url, download=False)
            
            # محاولة العثور على رابط مباشر
            final_url = info.get('url')

            # إذا لم يوجد رابط مباشر، البحث يدوياً في قائمة الصيغ
            if not final_url:
                formats = info.get('formats', [])
                # البحث عن صيغة تحتوي على صوت وصورة (mp4) ورابط صالح
                valid_formats = [
                    f for f in formats 
                    if f.get('url') and f.get('ext') == 'mp4'
                ]
                
                if valid_formats:
                    # نأخذ آخر صيغة لأنها الأفضل جودة عادة
                    final_url = valid_formats[-1]['url']
                elif formats:
                    # أي رابط متوفر كحل أخير (حتى لو صوت فقط أو فيديو فقط)
                    available = [f for f in formats if f.get('url')]
                    if available:
                        final_url = available[-1]['url']

            return jsonify({
                "status": "success",
                "title": info.get('title'),
                "url": final_url,
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration')
            })

    except Exception as e:
        error_clean = str(e).split(';')[0].replace('ERROR: ', '')
        logger.error(f"Error: {error_clean}")
        return jsonify({"status": "error", "message": error_clean}), 400

@app.route('/')
def home():
    return "OK"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
