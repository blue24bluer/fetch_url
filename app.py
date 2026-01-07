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
    """تحويل الكوكيز بصيغة Netscape المتوافقة"""
    if not os.path.exists('youtube.json'): return None
    try:
        with open('youtube.json', 'r') as f: data = json.load(f)
        cookie_file = 'cookies.txt'
        with open(cookie_file, 'w') as f:
            f.write("# Netscape HTTP Cookie File\n")
            for c in data:
                domain = c.get('domain', '')
                f.write(f"{domain}\t{'TRUE' if domain.startswith('.') else 'FALSE'}\t"
                        f"{c.get('path', '/')}\t{'TRUE' if c.get('secure') else 'FALSE'}\t"
                        f"{int(c.get('expirationDate', time.time()+31536000))}\t"
                        f"{c.get('name')}\t{c.get('value')}\n")
        return cookie_file
    except: return None

@app.route('/api/download', methods=['GET', 'POST'])
def download():
    url = request.values.get('url')
    if not url: return jsonify({"status": "error", "message": "No URL"}), 400

    cookie_path = convert_cookies()

    # خيارات إجبارية لتجاوز قيود الريندر والحظر
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        # لا نحدد صيغة هنا لنتجنب خطأ Requested format is not available
        'format': None, 
        'check_formats': False, # لا تفحص الرابط على السيرفر (Render محظور)
        'cookiefile': cookie_path,
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android'], # أفضل العملاء لتجاوز الحظر
                'skip': ['dash', 'hls'] 
            }
        },
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # استخراج الخام لكل البيانات
            info = ydl.extract_info(url, download=False)
            
            # البحث عن الروابط المباشرة في مصفوفة التنسيقات
            formats = info.get('formats', [])
            final_url = None
            
            # أولاً: نبحث عن mp4 متكامل (صوت وصورة معاً) - الأفضل للتحميل المباشر
            for f in reversed(formats):
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('ext') == 'mp4' and f.get('url'):
                    final_url = f.get('url')
                    break
            
            # ثانياً: إذا لم نجد mp4، نأخذ رابط m3u8 (يعمل للبث)
            if not final_url:
                for f in formats:
                    if ('.m3u8' in f.get('url', '') or f.get('protocol') == 'm3u8_native') and f.get('url'):
                        final_url = f.get('url')
                        break

            # ثالثاً: حل بائس أخير
            if not final_url and formats:
                final_url = formats[-1].get('url')

            if not final_url:
                return jsonify({"status": "error", "message": "No streamable URL found"}), 404

            return jsonify({
                "status": "success",
                "title": info.get('title'),
                "url": final_url,
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration')
            })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e).split(';')[0]}), 400

@app.route('/')
def home(): return "OK"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
