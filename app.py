import os
import json
import logging
from flask import Flask, request, jsonify
import yt_dlp

# إخفاء التحذيرات للتركيز على الأخطاء الحقيقية
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

app = Flask(__name__)

def get_netscape_cookies():
    # تجهيز الكوكيز إذا وجدت
    json_path = 'youtube.json'
    cookie_path = '/tmp/cookies.txt'
    
    if not os.path.exists(json_path):
        return None

    try:
        with open(json_path, 'r') as f:
            cookies = json.load(f)
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
    except Exception:
        return None

@app.route('/api/download', methods=['GET', 'POST'])
def download_media():
    url = request.values.get('url')
    m_type = request.values.get('type', 'video')
    quality = request.values.get('q', '720')  # افتراضي 720
    
    if not url:
        return jsonify({"status": "error", "message": "No URL provided"}), 400

    cookie_file = get_netscape_cookies()

    # === تصميم الفلاتر بحيث لا تفشل أبداً ===
    if m_type in ['audio', 'mp3']:
        # 1. m4a مباشر (تحميل)
        # 2. أي صوت مباشر
        # 3. أي صوت (حتى لو بث)
        format_selector = 'bestaudio[ext=m4a][protocol^=http]/bestaudio[protocol^=http]/bestaudio/best'
    else:
        # VIDEO
        # المشكلة كانت هنا: طلبنا HTTP حصراً، والسيرفر محظور
        # الحل: نطلب HTTP، وإن لم نجد نرضى بالمتاح (m3u8) ليعمل الفيديو في التطبيق
        req_h = f'[height<={quality}]'
        
        format_selector = (
            f'best[ext=mp4]{req_h}[protocol^=http]/' # الأفضل: mp4 مباشر وجودة محددة
            f'best[ext=mp4][protocol^=http]/'        # التالي: mp4 مباشر أي جودة
            f'best[protocol^=http]/'                 # التالي: أي رابط مباشر
            f'best'                                   # الأخير: (المنقذ) أي شيء يعمل حتى لو m3u8
        )

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': format_selector,
        'socket_timeout': 10,
        'noplaylist': True,
        # حذفنا skip hls لأن السيرفرات المحظورة تعتمد عليه
        # نستخدم عميل Web لأنه الأقل تعقيداً مع الكوكيز
        'extractor_args': {
            'youtube': {
                'player_client': ['web', 'android', 'ios'],
            }
        }
    }

    if cookie_file:
        ydl_opts['cookiefile'] = cookie_file

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # نستخرج المعلومات دون تحميل
            info = ydl.extract_info(url, download=False)
            
            final_url = info.get('url')
            
            # إذا فشل العثور على الرابط الرئيسي، ابحث في الصيغ المتاحة
            if not final_url and 'formats' in info:
                # نأخذ الصيغة التي اختارها الفلتر
                sel_id = info.get('format_id')
                for f in info['formats']:
                    if f.get('format_id') == sel_id:
                        final_url = f.get('url')
                        break
            
            # محاولة أخيرة بائسة إذا كان كل شيء فارغاً
            if not final_url:
                if 'formats' in info:
                    # خذ آخر صيغة (عادة الأفضل جودة)
                    final_url = info['formats'][-1].get('url')

            return jsonify({
                "status": "success",
                "title": info.get('title'),
                "url": final_url,
                "ext": info.get('ext'),
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration'),
                "is_stream": '.m3u8' in str(final_url) # علم للمستخدم أن الرابط بث وليس تحميل مباشر
            })

    except Exception as e:
        logger.error(str(e))
        return jsonify({"status": "error", "message": str(e).split(';')[0].replace('ERROR: ', '')}), 500

@app.route('/')
def home():
    return jsonify({"status": "Online"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
