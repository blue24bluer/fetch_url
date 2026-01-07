import os
import json
import logging
from flask import Flask, request, jsonify
import yt_dlp

# تقليل ضجيج السجلات
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

app = Flask(__name__)

def get_cookie_file():
    """تحويل الكوكيز لنتسكيب إذا وجدت"""
    json_path = 'youtube.json'
    netscape_path = '/tmp/cookies.txt'
    
    if not os.path.exists(json_path):
        return None

    try:
        with open(json_path, 'r') as f:
            cookies = json.load(f)
        
        with open(netscape_path, 'w') as f:
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
        return netscape_path
    except Exception:
        return None

@app.route('/')
def home():
    """Health check route"""
    return jsonify({"status": "running", "msg": "API is online"})

@app.route('/api/download', methods=['GET', 'POST'])
def download_media():
    url = request.values.get('url')
    m_type = request.values.get('type', 'video')
    quality = request.values.get('q') # Optional
    
    if not url:
        return jsonify({"status": "error", "message": "No URL provided"}), 400

    cookie_file = get_cookie_file()

    # === بناء فلتر الصيغ (الأهم لتفادي الأخطاء) ===
    # 1. نحاول نجيب رابط مباشر (http)
    # 2. لو فشل، نجيب أي رابط شغال حتى لو m3u8 (عشان الأداة ما توقف)
    
    if m_type in ['audio', 'mp3']:
        # محاولة m4a مباشر -> m4a أي نوع -> أي صوت
        format_str = 'bestaudio[ext=m4a][protocol^=http]/bestaudio[ext=m4a]/bestaudio/best'
    else:
        # فيديو:
        # 1. mp4 مباشر بالجودة المطلوبة
        # 2. mp4 مباشر بأي جودة
        # 3. أي رابط مباشر
        # 4. (الطوارئ) أي شيء يعمل
        req_q = f'[height<={quality}]' if quality else ''
        format_str = (
            f'best[ext=mp4]{req_q}[protocol^=http]/'
            f'best[ext=mp4][protocol^=http]/'
            f'best[protocol^=http]/'
            f'best' 
        )

    # إعدادات مخصصة لفك التشفير وتجاوز الحظر
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': format_str,
        'socket_timeout': 10,
        'noplaylist': True,
        # هذا الخيار السحري لتجاوز الـ Signature verification failed
        # نجبره يستخدم واجهة الأندرويد والويب المضمن لتقليل التعقيد
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web_embedded', 'ios', 'web'],
                'skip': ['dash', 'hls'] 
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        }
    }

    # إضافة الكوكيز فقط إذا كان العميل ويب (الأندرويد يتعارض مع الكوكيز أحياناً)
    if cookie_file:
        ydl_opts['cookiefile'] = cookie_file

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # استخدام download=False وجلب المعلومات
            try:
                info = ydl.extract_info(url, download=False)
            except yt_dlp.utils.DownloadError as de:
                # إذا فشل التمويه القوي، نحاول بتمويه أبسط
                if "Signature" in str(de):
                    ydl_opts.pop('extractor_args', None) 
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl2:
                        info = ydl2.extract_info(url, download=False)
                else:
                    raise de

            final_url = info.get('url')
            
            # إذا لم نجد رابطاً مباشراً في info، نبحث في القائمة
            if not final_url and 'formats' in info:
                # بما أننا رتبنا format_str بالأولوية، فإن الخيار المختار هو الأنسب
                chosen_format_id = info.get('format_id')
                for f in info['formats']:
                    if f.get('format_id') == chosen_format_id:
                        final_url = f.get('url')
                        break
                
                # فشل أخير: خذ أي رابط متاح
                if not final_url:
                     final_url = info['formats'][-1].get('url')

            return jsonify({
                "status": "success",
                "title": info.get('title'),
                "url": final_url,
                "ext": info.get('ext'),
                "protocol": "direct" if final_url and "googlevideo" in final_url and ".m3u8" not in final_url else "stream",
                "duration": info.get('duration'),
                "thumbnail": info.get('thumbnail'),
                "type": m_type
            })

    except Exception as e:
        logger.error(f"FAIL: {str(e)}")
        # تنظيف الرسالة
        clean_msg = str(e).split(';')[0].replace('ERROR: ', '')
        return jsonify({"status": "error", "message": clean_msg}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
