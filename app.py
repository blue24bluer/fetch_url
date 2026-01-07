import os
import json
import logging
from flask import Flask, request, jsonify
import yt_dlp

# إعداد السجلات (Logging) لتظهر بشكل أوضح
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

def get_cookies_path():
    """تجهيز ملف الكوكيز وتحويله إذا لزم الأمر"""
    try:
        # نبحث عن ملف الكوكيز في المجلد الرئيسي
        if not os.path.exists('youtube.json'):
            logger.warning("youtube.json not found - proceeding without cookies")
            return None
        
        with open('youtube.json', 'r') as f:
            cookies_json = json.load(f)
        
        # حفظ الكوكيز بصيغة Netscape في المجلد المؤقت (ضروري للسيرفرات)
        cookie_path = '/tmp/cookies.txt'
        with open(cookie_path, 'w') as f:
            f.write("# Netscape HTTP Cookie File\n")
            for c in cookies_json:
                domain = c.get('domain', '')
                flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                path = c.get('path', '/')
                secure = 'TRUE' if c.get('secure') else 'FALSE'
                expiry = str(int(c.get('expirationDate', c.get('expiry', 0))))
                name = c.get('name', '')
                value = c.get('value', '')
                f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expiry}\t{name}\t{value}\n")
        
        logger.info(f"Cookies loaded successfully to {cookie_path}")
        return cookie_path
    except Exception as e:
        logger.error(f"Cookie conversion error: {e}")
        return None

@app.route('/')
def home():
    """مسار رئيسي للتحقق من أن التطبيق يعمل"""
    return jsonify({
        "status": "online",
        "message": "YouTube Downloader API is running",
        "usage": "/api/download?url=YOUR_VIDEO_URL&q=720&type=video"
    })

@app.route('/api/download', methods=['GET', 'POST'])
def download_media():
    # استخدام request.values للبحث في GET Params و POST Data معاً
    target_url = request.values.get('url')
    quality = request.values.get('q', '720')  # الجودة الافتراضية 720
    media_type = request.values.get('type', 'video') # video or audio

    if not target_url:
        return jsonify({"status": "error", "message": "No URL provided"}), 400

    cookie_file = get_cookies_path()

    # صيغة الطلب
    # نفضل MP4 برابط مباشر (http) يحتوي على صوت وصورة
    if media_type in ['mp3', 'audio']:
        fmt_string = 'bestaudio[ext=m4a]/bestaudio'
    else:
        # يحاول إيجاد فيديو MP4 بروتوكول http (رابط واحد مباشر)
        # إذا لم يجد، يأخذ أفضل المتوفر
        fmt_string = f'best[ext=mp4][height<={quality}][protocol^=http]/best[ext=mp4][height<={quality}]/best'

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'format': fmt_string,
        'socket_timeout': 30,
        # إزالة extractor_args الخاصة بالأندرويد لأنها تسبب مشاكل مع الكوكيز
        # استخدام User-Agent قوي لمحاكاة متصفح سطح مكتب
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    if cookie_file:
        ydl_opts['cookiefile'] = cookie_file

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(target_url, download=False)
            
            # استخراج الرابط المباشر
            final_url = info.get('url')
            
            # في بعض الحالات، الرابط يكون داخل قائمة formats
            if not final_url and 'formats' in info:
                 # نختار الرابط الذي تم اختياره بواسطة محدد التنسيق
                 # yt-dlp usually marks the selected format clearly, but extracting just the url is safer via info.get('url')
                 # If top level URL is missing, assume the requested format logic already filtered formats
                 # and iterate to find the one matching criteria if needed. 
                 # For simplicity in direct API:
                 final_url = info['formats'][-1].get('url')

            return jsonify({
                "status": "success",
                "title": info.get('title'),
                "url": final_url,
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration'),
                "uploader": info.get('uploader'),
                "requested_type": media_type,
                "quality": quality
            })

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Download Error: {error_msg}")
        # تنظيف رسالة الخطأ للمستخدم
        clean_msg = error_msg.split(';')[0].replace('ERROR: [youtube] ', '')
        return jsonify({"status": "error", "message": clean_msg}), 400

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
