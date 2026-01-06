import os
import uuid
import json
import requests
import mimetypes
from flask import Flask, request, jsonify
import yt_dlp

# abc update 

app = Flask(__name__)

# إعداد المجلدات
DOWNLOAD_FOLDER = 'downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# ==========================================
# منطقة الكوكيز المدمجة (تم نسخ بياناتك هنا)
# ==========================================
RAW_COOKIES_JSON = [
    {
        "name": "VISITOR_PRIVACY_METADATA",
        "value": "CgJZRRIEGgAgTA%3D%3D",
        "domain": ".youtube.com",
        "path": "/",
        "secure": True,
        "expirationDate": 1783257203.287
    },
    {
        "name": "GPS",
        "value": "1",
        "domain": ".youtube.com",
        "path": "/",
        "secure": True,
        "expirationDate": 1767706979.117
    },
    {
        "name": "YSC",
        "value": "WOTyCz8q9h4",
        "domain": ".youtube.com",
        "path": "/",
        "secure": True,
        "session": True
    },
    {
        "name": "VISITOR_INFO1_LIVE",
        "value": "qN86XWvWqEo",
        "domain": ".youtube.com",
        "path": "/",
        "secure": True,
        "expirationDate": 1783257203.287
    },
    {
        "name": "LOGIN_INFO",
        "value": "AFmmF2swRAIgfcvcXvvzZvg_fLbvAEgLyPwV_KA9H-fmMfdt_Xo0VwYCICAn_gjGIQS-8sVcauvcMRIOQAkCS1DqD3RPYLBGLHN5:QUQ3MjNmemM2OEpYRF9xdzRvcmZUcl9uZ1J1VWJjZG9qclg0eTVSYVgyM2ZsclU0WGpQYmh1ZW50bGxiWVRyVWVXakJfa3BsRER1WWgwZGswSGxKcDdQWDVqTzZMZEVHN19GOVM0RUNxcW95SmFnWUlsMGVzRXNnWXR2ZjNhT0F0Wm04QTBmb3VXcFZYVGZjYmZoOTEwVU82Z0VEdm1zV1p3",
        "domain": ".youtube.com",
        "path": "/",
        "secure": True,
        "expirationDate": 1802265201.405
    },
    {
        "name": "__Secure-1PSID",
        "value": "g.a0004ggCdOelG8Yk9zvazwRd1rIEwWp8_Y7lUeIJbHl7bwZH7INhktUBm6LZ4aJraTm7xYkwjAACgYKAT0SARUSFQHGX2MiXjl15zUNeFtvlmet0v6HEBoVAUF8yKruM8E7-dgwvCv-q5N4ELfP0076",
        "domain": ".youtube.com",
        "path": "/",
        "secure": True,
        "expirationDate": 1802265201.007
    },
    {
        "name": "__Secure-3PSID",
        "value": "g.a0004ggCdOelG8Yk9zvazwRd1rIEwWp8_Y7lUeIJbHl7bwZH7INhE-ID4bH5AygJNMG2EftelgACgYKAf4SARUSFQHGX2MidY2K2PeUsM_vzE6MdcgE0BoVAUF8yKpgNuJtQ6Gj8lfyDGDtgsjI0076",
        "domain": ".youtube.com",
        "path": "/",
        "secure": True,
        "expirationDate": 1802265201.007
    }
]

class SmartDownloader:
    
    @staticmethod
    def _create_cookie_file():
        """يكتب ملف الكوكيز مباشرة على سيرفر Render"""
        txt_file = '/tmp/cookies.txt' # استخدام tmp لأنه مجلد مضمون الكتابة فيه
        
        try:
            with open(txt_file, 'w') as f:
                f.write("# Netscape HTTP Cookie File\n")
                # كتابة أهم الكوكيز من القائمة المدمجة
                for c in RAW_COOKIES_JSON:
                    domain = c.get('domain', '.youtube.com')
                    flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                    path = c.get('path', '/')
                    secure = 'TRUE' if c.get('secure', False) else 'FALSE'
                    expires = str(int(c.get('expirationDate', 0))) if c.get('expirationDate') else '0'
                    name = c.get('name', '')
                    value = c.get('value', '')
                    f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n")
            print("[+] Cookies written successfully to disk.")
            return txt_file
        except Exception as e:
            print(f"[-] Error writing cookies: {e}")
            return None

    @staticmethod
    def _get_format_string(req_type, quality):
        if req_type == 'audio':
            return 'bestaudio[ext=m4a]/bestaudio/best'
        else:
            if not quality or quality == 'best':
                return 'best[ext=mp4]/best'
            else:
                return f'best[height<={quality}][ext=mp4]/best[ext=mp4]/best'

    @staticmethod
    def identify_and_download(url, req_type='video', quality='best'):
        try:
            video_platforms = ['youtube.com', 'youtu.be', 'tiktok.com', 'instagram.com', 'facebook.com', 'twitch.tv']
            is_video_platform = any(platform in url for platform in video_platforms)

            if is_video_platform:
                return SmartDownloader.download_media(url, req_type, quality)
            else:
                try:
                    response = requests.head(url, allow_redirects=True, timeout=5)
                    content_type = response.headers.get('Content-Type', '').lower()
                except:
                    content_type = ''

                if 'text/html' not in content_type and content_type != '':
                    return SmartDownloader.download_direct_file(url, response)
                else:
                    return SmartDownloader.download_media(url, req_type, quality)

        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    @staticmethod
    def download_media(url, req_type, quality):
        file_id = str(uuid.uuid4())[:8]
        output_template = os.path.join(DOWNLOAD_FOLDER, f'%(title)s_{file_id}.%(ext)s')
        
        # إنشاء ملف الكوكيز من المتغير المدمج
        cookie_path = SmartDownloader._create_cookie_file()
        
        format_selector = SmartDownloader._get_format_string(req_type, quality)
        
        print(f"[*] Processing {req_type} -> {url}")

        ydl_opts = {
            'outtmpl': output_template,
            'format': format_selector,
            'quiet': True,
            'no_warnings': True,
            'restrictfilenames': True,
            
            # --- استخدام ملف الكوكيز الذي تم إنشاؤه ---
            'cookiefile': cookie_path,
            # ------------------------------------------

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
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
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
                
                return {
                    'status': 'success',
                    'method': 'media_engine',
                    'type': req_type,
                    'title': video_info.get('title', 'Unknown'),
                    'duration': video_info.get('duration'),
                    'filename': os.path.basename(filename),
                    'path': filename
                }
        except Exception as e:
            print(f"DL Error: {str(e)}")
            return {'status': 'error', 'message': str(e)}

    @staticmethod
    def download_direct_file(url, head_response):
        try:
            filename = url.split('/')[-1].split('?')[0]
            if not filename: filename = f"file_{str(uuid.uuid4())[:8]}"
            save_path = os.path.join(DOWNLOAD_FOLDER, filename)
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(save_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            return {'status': 'success', 'filename': filename, 'path': save_path}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

@app.route('/')
def home():
    return jsonify({"status": "running"})

@app.route('/api/download', methods=['POST'])
def process_download():
    data = request.get_json()
    if not data or 'url' not in data: return jsonify({'error': 'URL missing'}), 400
    return jsonify(SmartDownloader.identify_and_download(data['url'], data.get('type', 'video'), data.get('quality', 'best')))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
