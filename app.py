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

# التوكن بعد فك التشفير مباشرة لتجنب الأخطاء (ضعه كنص عادي هنا للأمان أثناء التجربة)
# أو اتركه كما هو مشفر إذا كنت متأكداً منه
GITHUB_TOKEN_RAW = "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"  # ⚠️ تأكد أن التوكن فعال
API_ENCODED = "Z2hwX3ExQVpVaXhRZTBOSzFLZXpIVjZhaTVmQWNxVHpsUzRIeDFiVwo="

GITHUB_REPO = "blue24bluer/fetch_url"
GITHUB_BRANCH = "main"
GITHUB_FOLDER = "download"

def log(msg):
    print(f"[DEBUG] {msg}", file=sys.stderr)

def get_token():
    # الأولوية للتوكن الخام إذا وضعته
    if GITHUB_TOKEN_RAW and not GITHUB_TOKEN_RAW.startswith("ضع"):
        return GITHUB_TOKEN_RAW.strip()
    try:
        return base64.b64decode(API_ENCODED).decode('utf-8').strip()
    except:
        return None

@app.route('/api/download', methods=['GET', 'HEAD'])
def download_factory():
    if request.method == 'HEAD':
        return jsonify({'status': 'ready'}), 200

    url = request.args.get('url')
    if not url: return jsonify({'error': 'URL missing'}), 400

    log(f"Processing URL: {url}")

    media_type = request.args.get('type', 'video')
    quality_req = request.args.get('q', '720')
    out_format = request.args.get('fmt', 'mp4')

    # --- [تصحيح الخطأ 413] ---
    # تم إزالة الكوكيز لأنها السبب في تضخم الطلب ورفض يوتيوب له
    # يفضل الاعتماد على User-Agent قوي بدلاً من الكوكيز التالفة
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'cookiefile': None, # تم التعطيل عمداً
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    }
    
    # إعداد صيغة التحميل
    if media_type == 'audio':
        ydl_opts['format'] = "bestaudio/best"
        final_ext = 'mp3' if out_format not in ['wav', 'aac'] else out_format
    else:
        final_ext = 'mp4'
        try: h = int(quality_req)
        except: h = 720
        # نطلب أفضل فيديو بأقل من أو يساوي الجودة المطلوبة لتسريع العملية
        ydl_opts['format'] = f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]/best[height<={h}][ext=mp4]/best"

    try:
        log("Getting Video Link from YouTube...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            target_raw_url = info.get('url')
            # تنظيف الاسم
            title = "".join([c for c in info.get('title', 'video') if c.isalnum() or c in (' ','-','_')]).strip().replace(" ", "_")[:50]
            if not target_raw_url: raise Exception("No direct URL found")

    except Exception as e:
        log(f"Extraction Failed: {e}")
        return jsonify({'error': f"Extraction Error: {str(e)}"}), 400

    # مسار الملف المحلي
    temp_dir = tempfile.gettempdir()
    filename_on_server = f"{title}.{final_ext}"
    local_path = os.path.join(temp_dir, filename_on_server)
    
    log(f"Downloading content via FFMPEG to: {local_path}")

    # استخدام أوامر FFMPEG سريعة جداً (Ultrafast) لتجنب انقطاع الاتصال (Timeout)
    cmd = [
        FFMPEG_BIN, '-y', '-hide_banner', '-loglevel', 'error',
        '-headers', 'User-Agent: Mozilla/5.0',
        '-i', target_raw_url
    ]

    if media_type == 'audio':
        cmd += ['-vn', '-c:a', 'libmp3lame', '-q:a', '5'] # جودة صوت متوسطة للسرعة
    else:
        # نسخ المحتوى كما هو دون إعادة ضغط (Video Passthrough) إذا كان ذلك ممكناً، ليكون الرفع سريعاً جداً
        # إذا كان الرابط m3u8، سنستخدم libx264 ولكن بسرعة فائقة
        if 'm3u8' in target_raw_url:
             cmd += ['-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', '-c:a', 'copy']
        else:
             cmd += ['-c', 'copy'] # أسرع طريقة على الإطلاق

    cmd.append(local_path)

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        if os.path.exists(local_path): os.remove(local_path)
        return jsonify({'error': 'Download/Conversion Failed', 'details': str(e)}), 500

    # التأكد من الحجم قبل الرفع (Github API Max: 100MB)
    filesize_mb = os.path.getsize(local_path) / (1024 * 1024)
    if filesize_mb > 98:
        os.remove(local_path)
        return jsonify({'error': f'File size ({filesize_mb:.1f}MB) exceeds GitHub API limit (100MB)'}), 413

    # الرفع
    try:
        log(f"Uploading {filesize_mb:.1f}MB to GitHub...")
        
        with open(local_path, "rb") as f:
            encoded_content = base64.b64encode(f.read()).decode("utf-8")
        
        token = get_token()
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FOLDER}/{filename_on_server}"
        
        # فحص وجود الملف (لتحديث الـ SHA)
        sha = None
        try:
            check = requests.get(api_url, headers=headers)
            if check.status_code == 200:
                sha = check.json()['sha']
        except: pass

        data = {
            "message": f"Add {filename_on_server}",
            "content": encoded_content,
            "branch": GITHUB_BRANCH
        }
        if sha: data["sha"] = sha

        upload_resp = requests.put(api_url, headers=headers, json=data)
        os.remove(local_path) # تنظيف

        if upload_resp.status_code in [200, 201]:
            dl_url = upload_resp.json().get('content', {}).get('download_url')
            # fallback url creator
            if not dl_url:
                dl_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{GITHUB_FOLDER}/{filename_on_server}"
            
            return jsonify({
                "status": "success",
                "direct_link": dl_url,
                "file": filename_on_server
            })
        else:
            return jsonify({"error": "GitHub Upload Error", "msg": upload_resp.text}), 400

    except Exception as e:
        if os.path.exists(local_path): os.remove(local_path)
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
