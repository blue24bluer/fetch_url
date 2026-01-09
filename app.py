from flask import Flask, request, jsonify
import yt_dlp
import json
import os
import tempfile
import subprocess
import shutil
import base64
import requests
import sys

app = Flask(__name__)

FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"

# التوكن المشفر الذي وضعته (تأكد أن صلاحيته لم تنته)
API_ENCODED = "Z2hwX3ExQVpVaXhRZTBOSzFLZXpIVjZhaTVmQWNxVHpsUzRIeDFiVwo=" 
GITHUB_REPO = "blue24bluer/fetch_url"
GITHUB_BRANCH = "main"
GITHUB_FOLDER = "download"

def log(msg):
    """دالة لطباعة معلومات التتبع في اللوجات"""
    print(f"[DEBUG] {msg}", file=sys.stderr)

def get_github_token():
    """فك تشفير التوكن وتنظيفه من أي رموز زائدة"""
    try:
        decoded_bytes = base64.b64decode(API_ENCODED)
        token = decoded_bytes.decode('utf-8').strip() # إزالة المسافات والأسطر الجديدة
        return token
    except Exception as e:
        log(f"Error decoding token: {e}")
        return None

def json_cookies_to_netscape(json_path):
    if not os.path.exists(json_path): return None
    try:
        with open(json_path, 'r', encoding='utf-8') as f: cookies = json.load(f)
        fd, temp_path = tempfile.mkstemp(suffix='.txt', text=True)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write("# Netscape HTTP Cookie File\n")
            for c in cookies:
                if 'domain' not in c or 'name' not in c: continue
                f.write(f"{c['domain']}\tTRUE\t{c.get('path','/')}\t{'TRUE' if c.get('secure') else 'FALSE'}\t{int(c.get('expiry', 0))}\t{c['name']}\t{c.get('value','')}\n")
        return temp_path
    except: return None

@app.route('/api/download', methods=['GET', 'HEAD'])
def download_factory():
    # منع الخطأ عند فحص الاتصال فقط
    if request.method == 'HEAD':
        return jsonify({'status': 'ready'}), 200

    url = request.args.get('url')
    if not url: return jsonify({'error': 'URL missing'}), 400

    log(f"Received request for URL: {url}")

    media_type = request.args.get('type', 'video')
    quality_req = request.args.get('q', '720')
    out_format = request.args.get('fmt', 'mp4')

    # تحضير الكوكيز
    cookie_file = json_cookies_to_netscape('youtube.json')
    
    # الحصول على رابط البث
    ydl_opts = {
        'quiet': True, 'no_warnings': True, 'cookiefile': cookie_file,
        'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    }
    
    if media_type == 'audio':
        ydl_opts['format'] = "bestaudio/best"
        final_ext = 'mp3' if out_format not in ['wav', 'aac'] else out_format
    else:
        final_ext = 'mp4'
        try: h = int(quality_req)
        except: h = 720
        ydl_opts['format'] = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best"

    try:
        log("Extracting video info...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            target_raw_url = info.get('url')
            title = "".join([c for c in info.get('title', 'media') if c.isalnum() or c in (' ','-','_')]).strip().replace(" ", "_")
            if len(title) > 50: title = title[:50] # تقصير الاسم لتجنب مشاكل الطول
            
    except Exception as e:
        if cookie_file: os.remove(cookie_file)
        log(f"yt-dlp Error: {e}")
        return jsonify({'error': f"Extraction Error: {str(e)}"}), 400

    if cookie_file: os.remove(cookie_file)

    # التجهيز للتحميل
    filename_on_server = f"{title}.{final_ext}"
    local_path = os.path.join(tempfile.gettempdir(), filename_on_server)
    
    log(f"Starting FFMPEG download to: {local_path}")

    # أمر FFMPEG مع optimization للسرعة
    cmd = [
        FFMPEG_BIN, '-y', '-hide_banner', '-loglevel', 'error',
        '-headers', 'User-Agent: Mozilla/5.0',
        '-i', target_raw_url
    ]

    if media_type == 'audio':
        cmd += ['-vn']
        if final_ext == 'mp3': cmd += ['-acodec', 'libmp3lame', '-q:a', '4'] # جودة متوسطة لسرعة أعلى
        else: cmd += ['-acodec', 'copy']
    else:
        # استخدام preset ultrafast لتسريع العملية قدر الإمكان
        cmd += ['-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', '-c:a', 'aac']

    cmd.append(local_path)

    try:
        subprocess.run(cmd, check=True)
        log("FFMPEG download completed.")
    except subprocess.CalledProcessError as e:
        log(f"FFMPEG Failed: {e}")
        return jsonify({'error': 'Conversion Failed'}), 500

    # التأكد من حجم الملف (GitHub لا يقبل أكبر من 100 ميجا عبر API)
    file_size_mb = os.path.getsize(local_path) / (1024 * 1024)
    log(f"File size: {file_size_mb:.2f} MB")
    
    if file_size_mb > 95: # هامش أمان
        os.remove(local_path)
        return jsonify({'error': 'File too large (>95MB) for GitHub API upload. Try a shorter video.'}), 413

    # مرحلة الرفع
    try:
        log("Encoding file to Base64 for GitHub...")
        with open(local_path, "rb") as f:
            encoded_content = base64.b64encode(f.read()).decode("utf-8")
        
        token = get_github_token()
        if not token:
            os.remove(local_path)
            return jsonify({'error': 'Invalid API Configuration'}), 500

        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FOLDER}/{filename_on_server}"
        
        # التحقق مما إذا كان الملف موجوداً لتحديثه (sha) أو إنشاء جديد
        log("Checking remote file existence...")
        check_resp = requests.get(api_url, headers=headers)
        data = {
            "message": f"Upload {filename_on_server}",
            "content": encoded_content,
            "branch": GITHUB_BRANCH
        }
        
        if check_resp.status_code == 200:
            data["sha"] = check_resp.json()['sha'] # تحديث الملف الموجود

        log("Uploading to GitHub...")
        upload_resp = requests.put(api_url, headers=headers, json=data)
        
        os.remove(local_path) # حذف الملف المحلي لتوفير المساحة

        if upload_resp.status_code in [200, 201]:
            # ملاحظة: رابط التحميل المباشر الخام (raw)
            raw_url = upload_resp.json()['content']['download_url']
            log("Upload SUCCESS!")
            return jsonify({
                "status": "success",
                "filename": filename_on_server,
                "direct_url": raw_url,
                "size_mb": f"{file_size_mb:.2f}"
            })
        else:
            log(f"GitHub Error: {upload_resp.text}")
            return jsonify({"error": "Github Refused Upload", "details": upload_resp.text}), 400

    except Exception as e:
        if os.path.exists(local_path): os.remove(local_path)
        log(f"General Error: {str(e)}")
        return jsonify({'error': f"Processing Error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
