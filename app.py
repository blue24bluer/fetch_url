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
        print(f"Cookie Conversion Error: {e}")
        return None

# ==========================================================
#  SEARCH API
# ==========================================================
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
                    vid_id = entry.get('id')
                    thumbnails = entry.get('thumbnails', [])
                    thumbnail_url = thumbnails[-1]['url'] if thumbnails else None
                    video_data = {
                        'id': vid_id,
                        'title': entry.get('title'),
                        'url': f"https://www.youtube.com/watch?v={vid_id}",
                        'uploader': entry.get('uploader'),
                        'duration': entry.get('duration'),
                        'view_count': entry.get('view_count'),
                        'thumbnail': thumbnail_url
                    }
                    results.append(video_data)
    except Exception as e:
        if cookie_file and os.path.exists(cookie_file): os.unlink(cookie_file)
        return jsonify({'error': f"Search Error: {str(e)}"}), 500

    if cookie_file and os.path.exists(cookie_file): os.unlink(cookie_file)
    return jsonify({'count': len(results), 'results': results})


# ==========================================================
#  DOWNLOAD API (Fix Applied Here)
# ==========================================================
@app.route('/api/download', methods=['GET'])
def download_factory():
    url = request.args.get('url')
    media_type = request.args.get('type', 'video')   # audio / video
    chatid = request.args.get('chatid')
    
    # [FIX 1] تحديد الصيغة الافتراضية بذكاء بناءً على النوع
    default_fmt = 'mp3' if media_type == 'audio' else 'mp4'
    out_format = request.args.get('fmt', default_fmt)
    
    quality_req = request.args.get('q', '720')

    if not url: return jsonify({'error': 'URL missing'}), 400
    if not chatid: return jsonify({'error': 'chatid is mandatory'}), 400

    # 1. تحضير الكوكيز
    cookie_file = json_cookies_to_netscape('youtube.json')

    # 2. YT-DLP Setup
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'cookiefile': cookie_file,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        }
    }
    
    format_selector = ""
    if media_type == 'audio':
        format_selector = "bestaudio/best"
    else: # Video
        if quality_req == 'best':
            format_selector = "bestvideo+bestaudio/best"
        else:
            try:
                h = int(quality_req)
                format_selector = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best"
            except:
                format_selector = f"bestvideo[height<=720]+bestaudio/best[height<=720]/best"
    
    ydl_opts['format'] = format_selector
    target_raw_url = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            target_raw_url = info.get('url')
    except Exception as e:
        if cookie_file and os.path.exists(cookie_file): os.unlink(cookie_file)
        return jsonify({'error': f"Extraction Error: {str(e)}"}), 400
    if cookie_file and os.path.exists(cookie_file): os.unlink(cookie_file)

    # 3. FFMPEG Processing
    temp_dir = tempfile.gettempdir()
    
    # [FIX 2] منع تكرار الامتداد في الاسم (مثلاً: اذا كان chatid ينتهي ب .mp3 لا نضيفها مرة أخرى)
    if chatid.lower().endswith(f".{out_format}"):
        clean_name = chatid # الاسم يحتوي على الصيغة بالفعل
    else:
        # إذا كان الاسم فيه صيغة أخرى (مثلا اسمه video.xyz والمطلوب mp4)
        root, ext = os.path.splitext(chatid)
        if ext: # يوجد امتداد، نقوم باستبداله
             clean_name = f"{root}.{out_format}"
        else:   # لا يوجد امتداد، نضيفه
             clean_name = f"{chatid}.{out_format}"
    
    local_filename = clean_name
    local_file_path = os.path.join(temp_dir, local_filename)

    if os.path.exists(local_file_path):
        os.remove(local_file_path)

    cmd = [
        FFMPEG_BIN, '-y',
        '-headers', 'User-Agent: Mozilla/5.0',
        '-i', target_raw_url
    ]

    # ضبط خيارات ffmpeg حسب النوع
    if media_type == 'audio':
        cmd.append('-vn')
        if out_format == 'mp3':
            cmd += ['-acodec', 'libmp3lame', '-q:a', '2', '-f', 'mp3']
        elif out_format == 'wav':
            cmd += ['-acodec', 'pcm_s16le', '-f', 'wav']
        else: 
            cmd += ['-acodec', 'aac', '-f', 'adts']
            if out_format == 'm4a': cmd[-2] = 'ipod'
    else:
        # فيديو
        if out_format == 'mp4':
            cmd += ['-c:v', 'copy', '-c:a', 'aac', '-movflags', 'frag_keyframe+empty_moov', '-f', 'mp4']
        elif out_format == 'mkv':
            cmd += ['-c', 'copy', '-f', 'matroska']
        else:
            cmd += ['-c:v', 'copy', '-c:a', 'aac', '-movflags', 'frag_keyframe+empty_moov', '-f', 'mp4']

    cmd.append(local_file_path)

    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except subprocess.CalledProcessError as e:
         return jsonify({'error': 'FFmpeg processing failed', 'details': str(e)}), 500

    # 4. Upload to Github
    encrypted_token = "Z2hwX3ExQVpVaXhRZTBOSzFLZXpIVjZhaTVmQWNxVHpsUzRIeDFiVwo="
    try:
        github_token = base64.b64decode(encrypted_token).decode('utf-8').strip()
        
        with open(local_file_path, "rb") as f:
            encoded_content = base64.b64encode(f.read()).decode("utf-8")
        
        repo_owner = "blue24bluer"
        repo_name = "fetch_url"

        # تحديد المجلد بناءً على النوع
        sub_folder = "files"
        if media_type == 'video':
            sub_folder = "video"
        elif media_type == 'audio':
            sub_folder = "music"
            
        github_path = f"download/{sub_folder}/{local_filename}"
        api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{github_path}"
        
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "FlaskServer-Uploader"
        }
        
        data = {
            "message": f"Upload {media_type}: {chatid}",
            "content": encoded_content
        }
        
        response = requests.put(api_url, headers=headers, json=data)
        
        if os.path.exists(local_file_path):
            os.remove(local_file_path)

        if response.status_code in [200, 201]:
            direct_link = f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/main/{github_path}"
            return jsonify({
                "status": "success", 
                "download_url": direct_link,
                "folder": sub_folder,
                "filename": local_filename
            })
        else:
            # (اختياري) محاولة تحديث الملف إذا كان موجوداً، لكن لنسهل الأمر نعيد الخطأ حالياً
            return jsonify({
                "error": "Github Upload Failed (Maybe file exists?)", 
                "github_status": response.status_code,
                "github_msg": response.json()
            }), 502

    except Exception as e:
        if os.path.exists(local_file_path): os.remove(local_file_path)
        return jsonify({'error': f"Upload Error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
