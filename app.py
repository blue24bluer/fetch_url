from flask import Flask, request, jsonify, Response, stream_with_context
import yt_dlp
import json
import os
import tempfile
import subprocess
import shutil
import base64
import requests 

app = Flask(__name__)

FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"

# مفتاح API المشفر بـ Base64
API_ENCODED = "Z2hwX3ExQVpVaXhRZTBOSzFLZXpIVjZhaTVmQWNxVHpsUzRIeDFiVwo="
GITHUB_REPO = "blue24bluer/fetch_url"
GITHUB_BRANCH = "main"
GITHUB_FOLDER = "download"

def json_cookies_to_netscape(json_path):
    if not os.path.exists(json_path): return None
    try:
        with open(json_path, 'r', encoding='utf-8') as f: cookies = json.load(f)
        fd, temp_path = tempfile.mkstemp(suffix='.txt', text=True)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write("# This is a generated file!  Do not edit.\n\n")
            for c in cookies:
                if 'domain' not in c or 'name' not in c: continue
                domain = c['domain']
                flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                path = c.get('path', '/')
                secure = 'TRUE' if c.get('secure', False) else 'FALSE'
                expiry = c.get('expirationDate', c.get('expiry', 0))
                expiry = int(expiry) if expiry else 0
                name = c['name']
                value = c.get('value', '')
                f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expiry}\t{name}\t{value}\n")
        return temp_path
    except Exception as e:
        return None

@app.route('/api/search', methods=['GET'])
def search_youtube():
    query = request.args.get('q')
    limit = request.args.get('limit', '10')

    if not query:
        return jsonify({'error': 'Search query missing'}), 400

    cookie_file = json_cookies_to_netscape('youtube.json')

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'cookiefile': cookie_file,
        'extract_flat': 'in_playlist',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        }
    }

    results = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_query = f"ytsearch{limit}:{query}"
            info = ydl.extract_info(search_query, download=False)

            if 'entries' in info:
                for entry in info['entries']:
                    thumbnails = entry.get('thumbnails', [])
                    results.append({
                        'id': entry.get('id'),
                        'title': entry.get('title'),
                        'uploader': entry.get('uploader'),
                        'duration': entry.get('duration'),
                        'view_count': entry.get('view_count'),
                        'thumbnail': thumbnails[-1]['url'] if thumbnails else None
                    })
    except Exception as e:
        if cookie_file: os.unlink(cookie_file)
        return jsonify({'error': f"Search Error: {str(e)}"}), 500

    if cookie_file: os.unlink(cookie_file)
    return jsonify({'count': len(results), 'results': results})

@app.route('/api/download', methods=['GET'])
def download_factory():
    # --- استلام الطلبات ---
    url = request.args.get('url')
    media_type = request.args.get('type', 'video')   
    quality_req = request.args.get('q', '720')       
    out_format = request.args.get('fmt', 'mp4')      
    
    if not url: return jsonify({'error': 'URL missing'}), 400

    cookie_file = json_cookies_to_netscape('youtube.json')
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'cookiefile': cookie_file,
        'http_headers': {'User-Agent': 'Mozilla/5.0'}
    }
    
    format_selector = ""
    if media_type == 'audio':
        format_selector = "bestaudio/best"
    else:
        try: h = int(quality_req)
        except: h = 720
        format_selector = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best"
    
    ydl_opts['format'] = format_selector
    file_title = "media"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            target_raw_url = info.get('url')
            raw_title = info.get('title', 'media')
            file_title = "".join([c for c in raw_title if c.isalnum() or c in (' ', '-', '_')]).strip().replace(" ", "_")
    except Exception as e:
        if cookie_file: os.unlink(cookie_file)
        return jsonify({'error': f"Extraction Error: {str(e)}"}), 400

    if cookie_file: os.unlink(cookie_file)

    temp_dir = tempfile.gettempdir()
    if media_type == 'audio' and out_format not in ['mp3', 'wav', 'aac']: out_format = 'mp3'
    if media_type == 'video' and out_format not in ['mp4', 'mkv']: out_format = 'mp4'

    filename_on_server = f"{file_title}.{out_format}"
    local_file_path = os.path.join(temp_dir, filename_on_server)

    # تحميل FFMPEG
    cmd = [FFMPEG_BIN, '-y', '-headers', 'User-Agent: Mozilla/5.0', '-i', target_raw_url]
    if media_type == 'audio':
        cmd.append('-vn')
        if out_format == 'mp3': cmd += ['-acodec', 'libmp3lame', '-q:a', '2']
        elif out_format == 'wav': cmd += ['-acodec', 'pcm_s16le']
        else: cmd += ['-acodec', 'aac']
    else:
        if out_format == 'mp4': cmd += ['-c:v', 'copy', '-c:a', 'aac', '-movflags', '+faststart']
        else: cmd += ['-c:v', 'copy', '-c:a', 'aac']
    
    cmd.append(local_file_path)

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        return jsonify({'error': 'FFmpeg Download Failed', 'details': str(e)}), 500

    # 5. رفع الملف إلى GITHUB
    try:
        github_api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FOLDER}/{filename_on_server}"
        
        # --- [جديد] فك تشفير مفتاح الـ API ---
        # نقوم بفك التشفير، وتحويله لنص، وحذف المسافات الزائدة مثل السطر الجديد
        try:
            GITHUB_TOKEN = base64.b64decode(API_ENCODED).decode('utf-8').strip()
        except Exception as e:
             os.remove(local_file_path)
             return jsonify({'error': f"Failed to decode API Token: {str(e)}"}), 500

        with open(local_file_path, "rb") as f:
            file_content = f.read()
        
        encoded_content = base64.b64encode(file_content).decode("utf-8")

        # استخدام التوكن المفكوك (GITHUB_TOKEN)
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }

        check_resp = requests.get(github_api_url, headers=headers)
        data = {
            "message": f"Upload {filename_on_server}",
            "content": encoded_content,
            "branch": GITHUB_BRANCH
        }
        
        if check_resp.status_code == 200:
            data["sha"] = check_resp.json()['sha']

        upload_resp = requests.put(github_api_url, headers=headers, json=data)
        
        # تنظيف الملف
        if os.path.exists(local_file_path):
            os.remove(local_file_path)

        if upload_resp.status_code in [200, 201]:
            direct_link = upload_resp.json()['content']['download_url']
            return jsonify({
                "status": "success", 
                "filename": filename_on_server,
                "download_url": direct_link
            })
        else:
            return jsonify({
                "error": "Github Upload Failed",
                "code": upload_resp.status_code,
                "message": upload_resp.text
            }), 400

    except Exception as e:
        if os.path.exists(local_file_path):
            os.remove(local_file_path)
        return jsonify({'error': f"Upload Error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
