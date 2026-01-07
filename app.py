import os
import json
import logging
from flask import Flask, request, jsonify
import yt_dlp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

def get_cookies():
    """تحميل الكوكيز إذا وجدت لتفادي الحظر"""
    if os.path.exists('youtube.json'):
        return 'youtube.json'  # yt-dlp يدعم قراءة json مباشرة في النسخ الحديثة أو يمكن تركه للمسار
    return None

@app.route('/')
def home():
    return jsonify({
        "status": "ready",
        "example": "/api/download?url=YOUR_URL&q=720&type=video&ext=mp4"
    })

@app.route('/api/download', methods=['GET', 'POST'])
def download_media():
    # 1. استقبال جميع البارامترات الممكنة
    url = request.values.get('url')
    m_type = request.values.get('type', 'video')  # video or audio
    quality = request.values.get('q')             # e.g., 720, 1080
    extension = request.values.get('ext')         # e.g., mp4, m4a
    
    if not url:
        return jsonify({"status": "error", "message": "No URL provided"}), 400

    # 2. بناء "Format Selector" ذكي بناءً على طلباتك
    format_selection = ""

    if m_type in ['audio', 'mp3']:
        # في الصوت، الأفضل عادة m4a لأنه مدعوم عالمياً
        # يوتيوب لا يبث MP3 أصلاً، لذا نطلب m4a (aac)
        target_ext = extension if extension else 'm4a'
        format_selection = f'bestaudio[ext={target_ext}]/bestaudio/best'
    
    else: # VIDEO
        # هنا الحل لمشكلة "Format not available"
        # الشرط [acodec!=none][vcodec!=none] يضمن وجود صوت وصورة معاً في ملف واحد
        
        req_ext = f'[ext={extension}]' if extension else ''
        req_quality = f'[height<={quality}]' if quality else ''
        
        # الأولوية 1: فيديو بالامتداد والجودة المطلوبة يحتوي صوت وصورة
        f1 = f'best{req_ext}{req_quality}[acodec!=none][vcodec!=none]'
        
        # الأولوية 2: فيديو بالجودة المطلوبة (أي امتداد) يحتوي صوت وصورة
        f2 = f'best{req_quality}[acodec!=none][vcodec!=none]'
        
        # الأولوية 3: أفضل ملف متاح (لتجنب الخطأ بأي ثمن)
        f3 = 'best[acodec!=none][vcodec!=none]/best'
        
        format_selection = f'{f1}/{f2}/{f3}'

    logger.info(f"Requested: {url} | Type: {m_type} | Selector: {format_selection}")

    opts = {
        'quiet': True,
        'noplaylist': True,
        'format': format_selection,
        'cookiefile': get_cookies(),
        # محاكاة متصفح سطح مكتب لتجنب قيود الهاتف
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'socket_timeout': 15,
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            # استخراج المعلومات بدون تحميل
            info = ydl.extract_info(url, download=False)
            
            download_url = info.get('url')
            
            # بحث يدوي عن الرابط إذا لم تنجح extract_info المباشرة
            if not download_url and 'formats' in info:
                # نختار الصيغة التي اختارها السكريبت
                format_id = info.get('format_id')
                for f in info['formats']:
                    if f.get('format_id') == format_id:
                        download_url = f.get('url')
                        break
            
            # تنظيف البيانات الزائدة
            title = info.get('title')
            thumb = info.get('thumbnail')
            duration = info.get('duration')
            file_ext = info.get('ext')
            
            return jsonify({
                "status": "success",
                "title": title,
                "url": download_url,  # هذا هو رابط التحميل المباشر
                "ext": file_ext,
                "thumbnail": thumb,
                "duration": duration,
                "params_used": {
                    "type": m_type,
                    "quality_limit": quality or "max",
                    "extension_req": extension or "auto"
                }
            })

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        # تحسين رسالة الخطأ
        return jsonify({
            "status": "error", 
            "message": str(e).split(';')[0].replace('ERROR: ', ''),
            "tip": "Try removing specific quality restrictions or try a different video type."
        }), 400

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
