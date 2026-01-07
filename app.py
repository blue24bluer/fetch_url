import os
import json
import time
import logging
from flask import Flask, request, jsonify
import yt_dlp

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

app = Flask(__name__)

def setup_cookies():
    """تحويل الكوكيز بصيغة Netscape"""
    if not os.path.exists('youtube.json'):
        return None
    try:
        with open('youtube.json', 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        cookie_path = 'cookies.txt'
        with open(cookie_path, 'w', encoding='utf-8') as f:
            f.write("# Netscape HTTP Cookie File\n")
            for c in cookies:
                domain = c.get('domain', '')
                path = c.get('path', '/')
                secure = 'TRUE' if c.get('secure') else 'FALSE'
                expires = int(c.get('expirationDate', c.get('expiry', time.time() + 31536000)))
                name = c.get('name', '')
                value = c.get('value', '')
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

    cookie_file = setup_cookies()

    # خيارات YT-DLP لمنع خطأ Requested format is not available
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        # لا نضع صيغة محددة هنا (نتركها فارغة) لتجنب فشل البحث الأولي
        'format': '', 
        'check_formats': False, 
        'extractor_args': {
            'youtube': {
                # استخدام ios فقط لأنه الأفضل حالياً في جلب روابط m3u8 و mp4 جاهزة
                'player_client': ['ios'],
                'skip': ['dash'] # تخطي dash لأنه يتطلب دمج
            }
        },
        'cookiefile': cookie_file if cookie_file else None,
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1'
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # استخراج المعلومات (لن يفشل الآن لأننا لم نحدد format)
            info = ydl.extract_info(url, download=False)
            
            formats = info.get('formats', [])
            final_url = None
            
            # --- البحث اليدوي عن أفضل رابط يعمل ---
            # 1. نبحث أولاً عن mp4 يحتوي صوت وصورة معاً (itag 18 أو 22)
            for f in formats:
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('ext') == 'mp4':
                    final_url = f.get('url')
            
            # 2. إذا لم نجد، نأخذ رابط m3u8 (هذا الرابط يعمل دائماً)
            if not final_url:
                for f in formats:
                    if f.get('protocol') == 'm3u8_native' or '.m3u8' in f.get('url', ''):
                        final_url = f.get('url')
                        break

            # 3. حل أخير: أول رابط متاح
            if not final_url and formats:
                final_url = formats[-1].get('url')

            if not final_url:
                return jsonify({"status": "error", "message": "No streamable URL found"}), 404

            return jsonify({
                "status": "success",
                "title": info.get('title'),
                "url": final_url,
                "thumbnail": info.get('thumbnail'),
                "protocol": "hls/m3u8" if ".m3u8" in final_url else "http/direct"
            })

    except Exception as e:
        error_msg = str(e).split(';')[0]
        if "confirm you're not a bot" in error_msg:
            error_msg = "IP Blocked by YouTube. Update cookies.json"
        
        return jsonify({
            "status": "error",
            "message": error_msg
        }), 400

@app.route('/')
def home(): return "API Running"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
