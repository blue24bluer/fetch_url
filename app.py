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
    """تحويل youtube.json إلى صيغة Netscape للتوافق مع yt-dlp"""
    json_path = 'youtube.json'
    cookie_path = 'cookies.txt'
    
    if not os.path.exists(json_path):
        return None

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        with open(cookie_path, 'w', encoding='utf-8') as f:
            f.write("# Netscape HTTP Cookie File\n")
            for cookie in data:
                domain = cookie.get('domain', '')
                path = cookie.get('path', '/')
                secure = 'TRUE' if cookie.get('secure', False) else 'FALSE'
                name = cookie.get('name', '')
                value = cookie.get('value', '')
                expires = cookie.get('expirationDate', cookie.get('expiry'))
                if not expires:
                    expires = int(time.time()) + 31536000
                
                flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{int(expires)}\t{name}\t{value}\n")
        return cookie_path
    except Exception as e:
        logger.error(f"Cookie setup failed: {e}")
        return None

@app.route('/api/download', methods=['GET', 'POST'])
def download_media():
    url = request.values.get('url')
    m_type = request.values.get('type', 'video')
    
    if not url:
        return jsonify({"status": "error", "message": "No URL provided"}), 400

    cookie_file = setup_cookies()

    # خيارات لاستخراج رابط واحد يعمل مهما كانت الظروف
    # 1. إجبار IPv4 لحل مشاكل الحظر على سيرفرات ريندر
    # 2. توسيع نطاق الصيغ المقبولة
    # 3. استخدام iOS كمحاكاة
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 30,
        'source_address': '0.0.0.0', # Force IPv4
        'noplaylist': True,
        # نحاول الحصول على الأفضل، إذا فشل نأخذ المتاح
        'format': 'best' if m_type == 'video' else 'bestaudio/best',
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android'], # iOS غالبًا يوفر روابط M3U8 ثابتة
            }
        }
    }

    if cookie_file:
        ydl_opts['cookiefile'] = cookie_file

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # نستخرج كل البيانات أولاً
            info = ydl.extract_info(url, download=False)
            
            # محاولة التقاط الرابط
            final_url = info.get('url')
            
            # إذا لم يُرجع رابطاً مباشراً، نبحث في قائمة formats يدوياً
            if not final_url:
                formats = info.get('formats', [])
                # تصفية الصيغ التي تملك رابطاً
                valid_formats = [f for f in formats if f.get('url')]
                if valid_formats:
                    # نأخذ الأخير (عادة الجودة الأعلى)
                    final_url = valid_formats[-1]['url']

            return jsonify({
                "status": "success",
                "title": info.get('title'),
                "url": final_url,
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration'),
                "protocol": info.get('protocol', 'http')
            })

    except Exception as e:
        error_msg = str(e)
        # إذا كان الخطأ بسبب عدم توفر الصيغة، نحاول مرة أخيرة بأي صيغة متاحة
        if "Requested format is not available" in error_msg:
             return fallback_extraction(url, ydl_opts)
             
        logger.error(f"Extraction failed: {error_msg}")
        return jsonify({
            "status": "error", 
            "message": error_msg.split(';')[0].replace('ERROR: ', ''),
        }), 400

def fallback_extraction(url, base_opts):
    """محاولة أخيرة بجلب أسوأ جودة أو أي شيء يعمل لتجنب الخطأ"""
    base_opts['format'] = 'worst' # قبول أي جودة لضمان وجود رابط
    try:
        with yt_dlp.YoutubeDL(base_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            final_url = info.get('url')
            if not final_url and info.get('formats'):
                final_url = info['formats'][-1].get('url')
                
            return jsonify({
                "status": "success_fallback",
                "title": info.get('title'),
                "url": final_url,
                "note": "Returned backup format because 'best' was blocked."
            })
    except Exception as e:
         return jsonify({"status": "fatal_error", "message": str(e)}), 400

@app.route('/')
def home():
    return "Service Active - IPv4 Forced"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
