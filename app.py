import os
import json
import time
import logging
from flask import Flask, request, jsonify
import yt_dlp

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

app = Flask(__name__)

def get_cookies():
    """تحويل الكوكيز من JSON إلى Netscape"""
    if not os.path.exists('youtube.json'):
        return None
    try:
        cookie_path = 'cookies.txt'
        with open('youtube.json', 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        with open(cookie_path, 'w', encoding='utf-8') as f:
            f.write("# Netscape HTTP Cookie File\n")
            for c in cookies:
                domain = c.get('domain', '')
                flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                path = c.get('path', '/')
                secure = 'TRUE' if c.get('secure') else 'FALSE'
                expires = int(c.get('expirationDate', c.get('expiry', time.time() + 31536000)))
                f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{c.get('name')}\t{c.get('value')}\n")
        return cookie_path
    except:
        return None

@app.route('/api/download', methods=['GET', 'POST'])
def download():
    url = request.values.get('url')
    if not url:
        return jsonify({"status": "error", "message": "URL is missing"}), 400

    cookie_file = get_cookies()

    # الإعدادات السحرية لتجاوز خطأ "Format not available"
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        # 'best[ext=mp4]' تطلب ملفاً واحداً يحتوي على صوت وصورة معاً بصيغة mp4 
        # هذا الملف غالباً يكون بجودة 360p أو 720p وهو الوحيد الذي يعمل على السيرفرات المحظورة
        'format': 'best[ext=mp4]/best', 
        'noplaylist': True,
        'nocheckcertificate': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android'],
                # منع البحث عن الروابط المعقدة التي تسبب حظر IP
                'skip': ['dash', 'hls'] 
            }
        },
        # إضافة User-Agent حقيقي لتقليل احتمالية الحظر
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1'
    }

    if cookie_file:
        ydl_opts['cookiefile'] = cookie_file

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # استخراج المعلومات
            info = ydl.extract_info(url, download=False)
            
            # محاولة الحصول على الرابط المباشر
            video_url = info.get('url')
            
            # إذا لم يوجد، نبحث يدوياً في قائمة التنسيقات عن أي فيديو mp4
            if not video_url:
                formats = info.get('formats', [])
                for f in formats:
                    if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('ext') == 'mp4':
                        video_url = f.get('url')
                        break

            if not video_url:
                return jsonify({"status": "error", "message": "No direct MP4 link found"}), 404

            return jsonify({
                "status": "success",
                "title": info.get('title'),
                "url": video_url,
                "thumbnail": info.get('thumbnail'),
                "ext": "mp4"
            })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e).split(';')[0]
        }), 400

@app.route('/')
def home():
    return "Fetcher Active"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
