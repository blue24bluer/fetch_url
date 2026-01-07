import os
import json
from flask import Flask, request, jsonify
import yt_dlp

app = Flask(__name__)

def convert_cookies():
    # تحويل ملف الكوكيز من JSON إلى صيغة Netscape
    try:
        if not os.path.exists('youtube.json'):
            print("WARNING: youtube.json not found")
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
    except Exception as e:
        print(f"Cookie Error: {e}")
        return None

@app.route('/api/download', methods=['GET', 'POST'])
def download_media():
    # 1. استقبال البيانات سواء عبر الرابط أو JSON
    if request.method == 'POST':
        data = request.get_json() or {}
        url = data.get('url')
        quality = str(data.get('q', '720'))
        m_type = data.get('type', 'video')
    else:
        url = request.args.get('url')
        quality = str(request.args.get('q', '720'))
        m_type = request.args.get('type', 'video')

    if not url:
        return jsonify({"status": "error", "message": "No URL provided"}), 400

    cookie_file = convert_cookies()

    # 2. إعدادات yt-dlp للتمويه كتطبيق أندرويد
    ydl_opts = {
        'quiet': True,
        'noplaylist': True,
        'socket_timeout': 30,
        # هذا هو السطر السحري لحل مشكلة التشفير في السيرفرات:
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios'],
                'skip': ['hls', 'dash'] # محاولة تجنب ملفات البث المجزأة
            }
        },
        'http_headers': {
             # تظاهر بأننا هاتف محمول
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36'
        }
    }

    if cookie_file:
        ydl_opts['cookiefile'] = cookie_file

    # 3. اختيار الصيغة (تجنب webm إذا أمكن لأن المستخدم يريد التحميل المباشر)
    if m_type in ['mp3', 'audio']:
        # صيغة m4a مدعومة في كل مكان وصوتها نقي ورابطها مباشر غالباً
        ydl_opts['format'] = 'bestaudio[ext=m4a]/bestaudio'
    else:
        # طلب فيديو MP4 بحد أقصى للجودة المطلوبة
        # نطلب [protocol^=http] لنتأكد أنه رابط تحميل مباشر وليس m3u8
        ydl_opts['format'] = f'best[ext=mp4][height<={quality}][protocol^=http]/best[ext=mp4][height<={quality}]/best[ext=mp4]/best'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # عدم تحميل الفيديو، فقط جلب المعلومات
            info = ydl.extract_info(url, download=False)
            
            # محاولة استخراج الرابط النهائي
            download_url = info.get('url')
            
            # إذا فشل العثور على رابط مباشر في الخاصية الرئيسية، نبحث في القائمة
            if not download_url:
                if 'formats' in info:
                    # نختار آخر صيغة (عادة الأفضل)
                    download_url = info['formats'][-1]['url']

            return jsonify({
                "status": "success",
                "title": info.get('title'),
                "download_url": download_url,
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration'),
                "extension": info.get('ext') or ('mp3' if m_type == 'audio' else 'mp4'),
                "requested_quality": quality,
                "uploader": info.get('uploader')
            })
            
    except Exception as e:
        # إرجاع تفاصيل الخطأ لتسهيل التصحيح
        return jsonify({"status": "error", "message": str(e).split(';')[0]}), 400

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
