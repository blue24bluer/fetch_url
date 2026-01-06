import os
import uuid
import json
import requests
import mimetypes
from flask import Flask, request, jsonify
import yt_dlp

app = Flask(__name__)

DOWNLOAD_FOLDER = 'downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

class SmartDownloader:
    
    @staticmethod
    def _prepare_cookies():
        """تحويل ملف json إلى txt يفهمه yt-dlp"""
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
                        path = c.get('path', '/')
                        secure = 'TRUE' if c.get('secure', False) else 'FALSE'
                        expires = str(int(c.get('expirationDate', 0))) if c.get('expirationDate') else '0'
                        name = c.get('name', '')
                        value = c.get('value', '')
                        flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                        f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n")
                return txt_file
            except Exception as e:
                print(f"Cookie Conversion Error: {e}")
                return None
        elif os.path.exists(txt_file):
            return txt_file
        return None

    @staticmethod
    def identify_and_download(url):
        try:
            try:
                response = requests.head(url, allow_redirects=True, timeout=5)
                content_type = response.headers.get('Content-Type', '').lower()
            except:
                content_type = ''
            
            video_platforms = ['youtube.com', 'youtu.be', 'tiktok.com', 'instagram.com', 'twitter.com', 'x.com', 'facebook.com']
            is_video_platform = any(platform in url for platform in video_platforms)

            if is_video_platform:
                return SmartDownloader.download_video(url)
            elif 'text/html' not in content_type and content_type != '':
                return SmartDownloader.download_direct_file(url, response)
            else:
                return SmartDownloader.download_video(url)

        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    @staticmethod
    def download_video(url):
        file_id = str(uuid.uuid4())[:8]
        output_template = os.path.join(DOWNLOAD_FOLDER, f'%(title)s_{file_id}.%(ext)s')
        
        cookie_path = SmartDownloader._prepare_cookies()

        ydl_opts = {
            'outtmpl': output_template,
            'format': 'best',
            'quiet': True,
            'no_warnings': True,
            'restrictfilenames': True,
            'cookiefile': cookie_path,
            
            # --- التعديلات الجديدة لإصلاح خطأ قوائم التشغيل ---
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web']
                },
                'youtubetab': {
                    'skip': ['authcheck'] # <--- هذا السطر هو الحل للمشكلة الجديدة
                }
            },
            # -----------------------------------------------
            
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
            },
            'nocheckcertificate': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                # التعامل مع قائمة التشغيل (تنزيل أول فيديو فقط أو المعلومات العامة)
                if 'entries' in info:
                    # إذا كان الرابط قائمة تشغيل، نأخذ أول فيديو فقط لتجنب التحميل اللانهائي
                    # يمكنك تغيير هذا السلوك حسب حاجتك
                    video_info = list(info['entries'])[0] 
                    filename = ydl.prepare_filename(video_info)
                    return {
                        'status': 'success',
                        'method': 'video_engine (playlist_item)',
                        'title': video_info.get('title', 'Unknown'),
                        'duration': video_info.get('duration'),
                        'filename': os.path.basename(filename),
                        'path': filename
                    }
                else:
                    # فيديو مفرد
                    filename = ydl.prepare_filename(info)
                    return {
                        'status': 'success',
                        'method': 'video_engine',
                        'title': info.get('title', 'Unknown'),
                        'duration': info.get('duration'),
                        'filename': os.path.basename(filename),
                        'path': filename
                    }

        except Exception as e:
            print(f"YT-DLP ERROR: {e}") # طباعة الخطأ في الكونسول للتوضيح
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
            
            file_size = os.path.getsize(save_path)
            
            return {
                'status': 'success',
                'method': 'direct_link',
                'filename': filename,
                'size_bytes': file_size,
                'path': save_path
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

@app.route('/')
def home():
    return jsonify({
        "message": "Welcome to Smart Downloader API",
        "usage": "Send POST request to /api/download"
    })

@app.route('/api/download', methods=['POST'])
def process_download():
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'error': 'URL is required'}), 400
    
    url = data['url']
    result = SmartDownloader.identify_and_download(url)
    
    status_code = 200 if result.get('status') == 'success' else 500
    return jsonify(result), status_code

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
