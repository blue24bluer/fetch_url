import os
import uuid
import requests
import mimetypes
from flask import Flask, request, jsonify
import yt_dlp

app = Flask(__name__)

# مجلد حفظ الملفات
DOWNLOAD_FOLDER = 'downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

class SmartDownloader:
    """
    كلاس مسؤول عن توجيه الرابط للتقنية المناسبة
    """
    
    @staticmethod
    def identify_and_download(url):
        """
        المنطق الذكي:
        1. يحاول معرفة نوع المحتوى عبر الرأس (HEAD request).
        2. إذا كان فيديو من منصة معروفة، يستخدم yt-dlp.
        3. إذا كان ملف مباشر، يستخدم requests.
        """
        try:
            # الخطوة 1: فحص نوع الرابط مبدئياً
            try:
                response = requests.head(url, allow_redirects=True, timeout=5)
                content_type = response.headers.get('Content-Type', '').lower()
                content_length = response.headers.get('Content-Length', 0)
            except:
                content_type = ''
            
            # قائمة المنصات التي يفضل استخدام yt-dlp معها حتى لو كان الرابط يبدو مباشراً
            video_platforms = ['youtube.com', 'youtu.be', 'tiktok.com', 'instagram.com', 'twitter.com', 'x.com', 'facebook.com']
            is_video_platform = any(platform in url for platform in video_platforms)

            # القرار الذكي
            if is_video_platform:
                return SmartDownloader.download_video(url)
            elif 'text/html' not in content_type and content_type != '':
                # غالباً رابط مباشر لملف (صورة، مضغوط، pdf)
                return SmartDownloader.download_direct_file(url, response)
            else:
                # محاولة أخيرة كفيديو (للمواقع التي لا تظهر في القائمة أعلاه)
                return SmartDownloader.download_video(url)

        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    @staticmethod
    def download_video(url):
        """تنزيل الفيديوهات باستخدام yt-dlp"""
        print(f"[*] Detected Video Platform. Processing: {url}")
        
        # إعدادات فريدة لكل عملية تنزيل
        file_id = str(uuid.uuid4())[:8]
        output_template = os.path.join(DOWNLOAD_FOLDER, f'%(title)s_{file_id}.%(ext)s')
        
        ydl_opts = {
            'outtmpl': output_template,
            'format': 'best', # أفضل جودة
            'quiet': True,
            'no_warnings': True,
            'restrictfilenames': True, # تنظيف اسم الملف
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                return {
                    'status': 'success',
                    'method': 'video_engine (yt-dlp)',
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration'),
                    'filename': os.path.basename(filename),
                    'path': filename
                }
        except Exception as e:
            return {'status': 'error', 'message': f"Video download failed: {str(e)}"}

    @staticmethod
    def download_direct_file(url, head_response):
        """تنزيل الملفات المباشرة باستخدام Requests"""
        print(f"[*] Detected Direct File. Processing: {url}")
        
        try:
            # استخراج اسم الملف من الرابط أو إنشاء اسم عشوائي
            filename = url.split('/')[-1].split('?')[0]
            if not filename or len(filename) > 100:
                ext = mimetypes.guess_extension(head_response.headers.get('Content-Type')) or '.bin'
                filename = f"file_{str(uuid.uuid4())[:8]}{ext}"
            
            save_path = os.path.join(DOWNLOAD_FOLDER, filename)
            
            # التحميل بنظام الـ Stream للملفات الكبيرة
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(save_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            
            file_size = os.path.getsize(save_path)
            
            return {
                'status': 'success',
                'method': 'direct_link (requests)',
                'filename': filename,
                'size_bytes': file_size,
                'path': save_path
            }
        except Exception as e:
            return {'status': 'error', 'message': f"Direct download failed: {str(e)}"}

@app.route('/')
def home():
    return jsonify({
        "message": "Welcome to Smart Downloader API",
        "usage": "Send POST request to /api/download with JSON {'url': '...'}"
    })

@app.route('/api/download', methods=['POST'])
def process_download():
    data = request.get_json()
    
    if not data or 'url' not in data:
        return jsonify({'error': 'URL is required'}), 400
    
    url = data['url']
    
    # استدعاء المحرك الذكي
    result = SmartDownloader.identify_and_download(url)
    
    status_code = 200 if result.get('status') == 'success' else 500
    return jsonify(result), status_code

if __name__ == '__main__':
    # الحصول على المنفذ من متغيرات البيئة في السيرفر أو استخدام 5000 كاحتياط
    port = int(os.environ.get('PORT', 5000))
    # التشغيل على 0.0.0.0 أمر ضروري للمنصات السحابية
    app.run(host='0.0.0.0', port=port)
