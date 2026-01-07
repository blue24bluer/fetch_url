import os
import json
import logging
from flask import Flask, request, jsonify
import yt_dlp

# تقليل ضجيج السجلات
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/api/download', methods=['GET', 'POST'])
def download_media():
    url = request.values.get('url')
    m_type = request.values.get('type', 'video') # video, audio
    
    if not url:
        return jsonify({"status": "error", "message": "No URL provided"}), 400

    # === الإعدادات (بدون أي شروط مسبقة تسبب الفشل) ===
    # نطلب 'best' فقط، ونترك للمكتبة مهمة جلب المتاح مهما كان نوعه
    if m_type == 'audio':
        format_selector = 'bestaudio/best'
    else:
        format_selector = 'best' 

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': format_selector,
        'socket_timeout': 10,
        # هذا يمنع البحث عن القوائم لتسريع العمل
        'noplaylist': True,
        # نستخدم عميل Web لأنه الأقل تعرضاً لمشاكل التشفير المعقدة حالياً
        'extractor_args': {
            'youtube': {
                'player_client': ['web', 'android'],
            }
        },
        # منع التحميل الفعلي، فقط جلب الرابط
        'forceurl': True, 
        'dump_single_json': True
    }

    # إذا وجد ملف كوكيز، نستخدمه
    if os.path.exists('youtube.json'):
         # في النسخ الجديدة، يمكن تمرير اسم ملف json مباشرة دون تحويل لـ Netscape
         # (yt-dlp supports internal JSON cookies recently, but strictly netscape is safer. 
         # Assuming previous conversion logic worked, use the simpler method first for raw connection)
         # للسرعة ولتجنب أخطاء التحويل، سنجرب بدونه أولاً أو نعتمد على المتصفح
         pass 

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # نستخرج المعلومات دون تحميل
            info = ydl.extract_info(url, download=False)
            
            # 1. المحاولة الأولى: الحصول على الرابط الرئيسي
            final_url = info.get('url')
            
            # 2. إذا كان فارغاً (يحدث في فيديوهات الموسيقى المحظورة)
            if not final_url:
                # نبحث يدوياً في قائمة formats عن أي رابط يعمل
                formats = info.get('formats', [])
                # نرتبها لنأخذ الأفضل (الأخيرة عادة)
                if formats:
                    final_url = formats[-1].get('url')
            
            protocol_type = "direct"
            if final_url and (".m3u8" in final_url or "manifest" in final_url):
                protocol_type = "stream_manifest"

            return jsonify({
                "status": "success",
                "title": info.get('title'),
                "url": final_url, # قد يكون رابط مباشر أو رابط بث
                "type": m_type,
                "protocol": protocol_type,
                "thumbnail": info.get('thumbnail'),
                "msg": "If protocol is stream_manifest, this means Render IPs are blocked from direct download."
            })

    except Exception as e:
        error_msg = str(e).split(';')[0].replace('ERROR: ', '')
        logger.error(f"Failed: {error_msg}")
        return jsonify({
            "status": "error", 
            "message": error_msg,
            "tip": "Server IP might be blocked by YouTube."
        }), 400

@app.route('/')
def home():
    return "Service Running"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
