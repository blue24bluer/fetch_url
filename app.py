import os
import json
import logging
from flask import Flask, request, jsonify
import yt_dlp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

def convert_cookies_to_netscape():
    """تحويل الكوكيز من JSON إلى صيغة Netscape لتفادي خطأ yt-dlp"""
    try:
        json_path = 'youtube.json'
        netscape_path = '/tmp/cookies.txt'

        if not os.path.exists(json_path):
            return None
        
        # قراءة الـ JSON
        with open(json_path, 'r') as f:
            cookies = json.load(f)
        
        # كتابة صيغة Netscape
        with open(netscape_path, 'w') as f:
            f.write("# Netscape HTTP Cookie File\n")
            for c in cookies:
                domain = c.get('domain', '')
                flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                path = c.get('path', '/')
                secure = 'TRUE' if c.get('secure') else 'FALSE'
                # معالجة اختلاف التسميات بين expiry و expirationDate
                expiry = str(int(c.get('expirationDate', c.get('expiry', 0))))
                name = c.get('name', '')
                value = c.get('value', '')
                f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expiry}\t{name}\t{value}\n")
        
        return netscape_path
    except Exception as e:
        logger.error(f"Cookie Conversion Error: {e}")
        return None

@app.route('/api/download', methods=['GET', 'POST'])
def download_media():
    # 1. استقبال البيانات (URL يتحكم بكل شيء)
    url = request.values.get('url')
    m_type = request.values.get('type', 'video')  # 'video' or 'audio'
    quality = request.values.get('q', '')         # '720', '1080', or empty
    ext = request.values.get('ext', '')           # 'mp4', 'm4a', or empty

    if not url:
        return jsonify({"status": "error", "message": "No URL provided"}), 400

    # 2. تجهيز الكوكيز بصيغة صحيحة
    cookie_file = convert_cookies_to_netscape()

    # 3. بناء الفلتر الذكي (Smart Selector)
    if m_type in ['audio', 'mp3']:
        # للصوت: نفضل m4a لأنه مدعوم عالمياً
        target_ext = ext if ext else 'm4a'
        # الترتيب: طلبك المحدد -> أي صوت m4a -> أفضل صوت متوفر
        fmt_ops = f'bestaudio[ext={target_ext}]/bestaudio/best'
    else:
        # للفيديو: 
        req_h = f'[height<={quality}]' if quality else ''
        req_e = f'[ext={ext}]' if ext else '[ext=mp4]'
        
        # الترتيب المنطقي لتفادي الأخطاء:
        # 1. فيديو + صوت بالامتداد والجودة المطلوبة
        f1 = f'best{req_e}{req_h}[acodec!=none][vcodec!=none]'
        # 2. فيديو + صوت بالجودة المطلوبة (أي امتداد)
        f2 = f'best{req_h}[acodec!=none][vcodec!=none]'
        # 3. أي فيديو يحتوي صوت وصورة (الخيار الآمن)
        f3 = 'best[acodec!=none][vcodec!=none]/best'
        
        fmt_ops = f'{f1}/{f2}/{f3}'

    ydl_opts = {
        'quiet': True,
        'noplaylist': True,
        'format': fmt_ops,
        'socket_timeout': 15,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
    }

    if cookie_file:
        ydl_opts['cookiefile'] = cookie_file

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # استخراج المعلومات
            info = ydl.extract_info(url, download=False)
            
            # محاولة جلب الرابط المباشر
            download_url = info.get('url')
            
            # فحص إضافي في حالة كان الرابط مخفياً داخل formats
            if not download_url and 'formats' in info:
                # نستخدم معرف الصيغة المختارة للعثور على رابطها
                chosen_id = info.get('format_id')
                for f in info['formats']:
                    if f.get('format_id') == chosen_id:
                        download_url = f.get('url')
                        break
            
            return jsonify({
                "status": "success",
                "title": info.get('title'),
                "url": download_url,
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration'),
                "uploader": info.get('uploader'),
                "ext": info.get('ext'),
                "details": {
                    "quality_requested": quality or "max",
                    "type": m_type,
                    "cookies_used": bool(cookie_file)
                }
            })

    except Exception as e:
        logger.error(str(e))
        return jsonify({
            "status": "error",
            "message": str(e).split(';')[0].replace('ERROR: ', ''),
            "tip": "Try changing 'type' or removing 'q' parameter."
        }), 400

@app.route('/')
def home():
    return "API Online. Use /api/download"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
