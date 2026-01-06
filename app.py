import os
import uuid
import json
import requests
import mimetypes
from flask import Flask, request, jsonify
import yt_dlp

app = Flask(__name__)

# إعداد المجلدات
DOWNLOAD_FOLDER = 'downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

class SmartDownloader:
    
    @staticmethod
    def _prepare_cookies():
        """تحويل cookies.json إلى cookies.txt"""
        json_file = 'cookies.json'
        txt_file = 'cookies.txt'
        
        if os.path.exists(json_file):
            try:
                with open(json_file, 'r') as f:
                    cookies = json.load(f)
                
                with open(txt_file, 'w') as f:
                    f.write("# Netscape HTTP Cookie File\n")
                    for c in cookies:
                        domain = c.get('domain', '')
                        flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                        path = c.get('path', '/')
                        secure = 'TRUE' if c.get('secure', False) else 'FALSE'
                        expires = str(int(c.get('expirationDate', 0))) if c.get('expirationDate') else '0'
                        name = c.get('name', '')
                        value = c.get('value', '')
                        f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n")
                return txt_file
            except Exception:
                return None
        elif os.path.exists(txt_file):
            return txt_file
        return None

    @staticmethod
    def _get_format_string(req_type, quality):
        """
        إنشاء معادلة التنزيل بناءً على طلب المستخدم
        مع مراعاة عدم وجود FFmpeg في السيرفر
        """
        # إذا طلب صوت فقط (mp3/m4a)
        if req_type == 'audio':
            # أفضل صوت متوفر لا يحتاج دمج
            return 'bestaudio[ext=m4a]/bestaudio/best'
        
        # إذا طلب فيديو
        else:
            if not quality or quality == 'best':
                # أفضل فيديو mp4 بملف واحد
                return 'best[ext=mp4]/best'
            else:
                # محاولة الحصول على دقة محددة، إذا لم توجد ينزل الأقل منها، بشرط يكون mp4 جاهز
                # مثال: best[height<=720][ext=mp4]
                return f'best[height<={quality}][ext=mp4]/best[ext=mp4]/best'

    @staticmethod
    def identify_and_download(url, req_type='video', quality='best'):
        try:
            # هل هو منصة فيديو؟
            video_platforms = ['youtube.com', 'youtu.be', 'tiktok.com', 'instagram.com', 'twitter.com', 'x.com', 'facebook.com', 'twitch.tv']
            is_video_platform = any(platform in url for platform in video_platforms)

            # إذا الرابط فيديو أو المستخدم طلب تحديداً (صوت/فيديو) من منصة مدعومة
            if is_video_platform:
                return SmartDownloader.download_media(url, req_type, quality)
            else:
                # فحص سريع للروابط المباشرة
                try:
                    response = requests.head(url, allow_redirects=True, timeout=5)
                    content_type = response.headers.get('Content-Type', '').lower()
                except:
                    content_type = ''

                if 'text/html' not in content_type and content_type != '':
                    return SmartDownloader.download_direct_file(url, response)
                else:
                    # العودة لمحرك الفيديو كخيار أخير
                    return SmartDownloader.download_media(url, req_type, quality)

        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    @staticmethod
    def download_media(url, req_type, quality):
        """المحرك الرئيسي لتنزيل الفيديو والصوت"""
        file_id = str(uuid.uuid4())[:8]
        
        # اختيار القالب المناسب بناء على النوع
        ext_tmpl = '%(ext)s'
        if req_type == 'audio':
             # سيحاول yt-dlp التخمين، غالباً m4a
             pass 

        output_template = os.path.join(DOWNLOAD_FOLDER, f'%(title)s_{file_id}.{ext_tmpl}')
        
        cookie_path = SmartDownloader._prepare_cookies()
        
        # استدعاء دالة تحديد الصيغة الذكية
        format_selector = SmartDownloader._get_format_string(req_type, quality)
        
        print(f"[*] Downloading {req_type} with format: {format_selector}")

        ydl_opts = {
            'outtmpl': output_template,
            'format': format_selector,
            'quiet': True,
            'no_warnings': True,
            'restrictfilenames': True,
            'cookiefile': cookie_path,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web'],
                    'skip': ['hls', 'dash']
                },
                'youtubetab': {
                    'skip': ['authcheck']
                }
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            },
            'nocheckcertificate': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                if 'entries' in info:
                    video_info = list(info['entries'])[0]
                else:
                    video_info = info

                filename = ydl.prepare_filename(video_info)
                
                # إرجاع تفاصيل الملف
                return {
                    'status': 'success',
                    'method': 'media_engine',
                    'type': req_type,
                    'requested_quality': quality,
                    'title': video_info.get('title', 'Unknown'),
                    'duration': video_info.get('duration'),
                    'filename': os.path.basename(filename),
                    'path': filename
                }
        except Exception as e:
            print(f"Error: {e}")
            return {'status': 'error', 'message': str(e)}

    @staticmethod
    def download_direct_file(url, head_response):
        try:
            filename = url.split('/')[-1].split('?')[0]
            if not filename or len(filename) > 100:
                ext = mimetypes.guess_extension(head_response.headers.get('Content-Type')) or '.bin'
                filename = f"file_{str(uuid.uuid4())[:8]}{ext}"
            
            save_path = os.path.join(DOWNLOAD_FOLDER, filename)
            
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(save_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            
            return {
                'status': 'success',
                'method': 'direct_link',
                'filename': filename,
                'path': save_path
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

@app.route('/')
def home():
    return jsonify({
        "message": "Advanced Downloader API Ready",
        "options": {
            "type": ["video", "audio"],
            "quality": ["1080", "720", "480", "360"]
        }
    })

@app.route('/api/download', methods=['POST'])
def process_download():
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'error': 'URL is required'}), 400
    
    url = data['url']
    # قراءة الخيارات الجديدة مع وضع قيم افتراضية
    req_type = data.get('type', 'video') # video or audio
    quality = data.get('quality', 'best') # 720, 360, etc..
    
    result = SmartDownloader.identify_and_download(url, req_type, quality)
    
    status_code = 200 if result.get('status') == 'success' else 500
    return jsonify(result), status_code

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
