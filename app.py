import os
import json
import time
import logging
from flask import Flask, request, jsonify
import yt_dlp

# إعداد السجلات لتوضيح الخطأ دون حشو
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

app = Flask(__name__)

def get_cookie_file():
    """تحويل الكوكيز بصمت وبسرعة"""
    if not os.path.exists('youtube.json'):
        return None
    try:
        # التأكد من عدم إعادة الكتابة في كل طلب لتقليل العمليات
        if os.path.exists('cookies.txt') and os.path.getmtime('cookies.txt') > os.path.getmtime('youtube.json'):
            return 'cookies.txt'
            
        with open('youtube.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        with open('cookies.txt', 'w', encoding='utf-8') as f:
            f.write("# Netscape HTTP Cookie File\n")
            for c in data:
                f.write(f"{c.get('domain')}\tTRUE\t{c.get('path')}\t"
                        f"{'TRUE' if c.get('secure') else 'FALSE'}\t"
                        f"{int(c.get('expirationDate', time.time() + 9999999))}\t"
                        f"{c.get('name')}\t{c.get('value')}\n")
        return 'cookies.txt'
    except:
        return None

@app.route('/api/download', methods=['GET', 'POST'])
def download_media():
    url = request.values.get('url')
    if not url:
        return jsonify({"status": "error", "message": "Url missing"}), 400

    cookie_path = get_cookie_file()

    # --- الإعدادات المنقذة ---
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        
        # 1. عدم تحديد format صارم لتجنب الخطأ
        # نسمح بأي جودة متوفرة (غالباً 360p في حالة الحظر)
        'format': 'best', 
        
        # 2. هذا هو المفتاح في بيئة Render: عدم التحقق مما إذا كانت الصيغة تعمل
        'check_formats': False, 
        
        # 3. تجاهل الأخطاء للمتابعة حتى لو كان الفيديو محظوراً جزئياً
        'ignoreerrors': True,
        
        # 4. محاولة خداع السيرفر باستخدام واجهة الموبايل القديمة (بدون جافا سكربت معقد)
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios'], # iOS يوفر m3u8، android يوفر 3gp/mp4 قديم
                'skip': ['hls', 'dash'] # محاولة جلب رابط http مباشر إن وجد
            }
        },
        
        # 5. إلغاء قائمة التشغيل لتسريع الطلب
        'noplaylist': True,
    }

    if cookie_path:
        ydl_opts['cookiefile'] = cookie_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # تنظيف الكاش قد يحل مشكلة البيانات القديمة
            # ydl.cache.remove() # (موقوف للسرعة، فعله إذا استمرت المشكلة)

            info = ydl.extract_info(url, download=False)
            
            # في حال فشل الاستخراج تماماً وعاد بـ None بسبب ignoreerrors
            if not info:
                 return jsonify({"status": "fatal", "message": "Blocked IP/Geo"}), 500

            final_url = info.get('url')
            
            # البحث اليدوي العنيف عن أي رابط حي
            if not final_url and 'formats' in info:
                # نختار الصيغة التي تملك URL وتملك Video Codec (ليست صوت فقط)
                # وإذا لم نجد، نقبل أي رابط
                all_urls = [f for f in info['formats'] if f.get('url')]
                
                # ترتيب: mp4 > others
                mp4_urls = [u for u in all_urls if u.get('ext') == 'mp4']
                
                if mp4_urls:
                    final_url = mp4_urls[-1]['url'] # الأخير عادة أفضل جودة
                elif all_urls:
                    final_url = all_urls[-1]['url'] # أي شيء أفضل من لا شيء

            protocol = "http"
            if final_url and ".m3u8" in final_url:
                protocol = "hls"

            return jsonify({
                "status": "success",
                "title": info.get('title', 'Unknown'),
                "url": final_url,
                "protocol": protocol,
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration')
            })

    except Exception as e:
        err = str(e)
        if "Sign in" in err:
            return jsonify({"status": "auth_error", "message": "Cookies Invalid/Expired"}), 403
        
        # محاولة أخيرة بائسة: إذا فشل كل شيء، نرسل رسالة خطأ صريحة
        logger.error(f"FAIL: {err}")
        return jsonify({
            "status": "error", 
            "message": err.split(';')[0].replace('ERROR: ', '')
        }), 400

@app.route('/')
def home():
    return "Ready"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
