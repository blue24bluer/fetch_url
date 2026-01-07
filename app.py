from flask import Flask, request, jsonify, Response, stream_with_context
import yt_dlp
import json
import os
import tempfile
import subprocess
import shutil

app = Flask(__name__)

FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"

def json_cookies_to_netscape(json_path):
    """تحويل دقيق جداً من JSON إلى Netscape format ليعمل مع yt-dlp"""
    if not os.path.exists(json_path): return None
    try:
        with open(json_path, 'r', encoding='utf-8') as f: cookies = json.load(f)
        
        fd, temp_path = tempfile.mkstemp(suffix='.txt', text=True)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write("# This is a generated file!  Do not edit.\n\n")
            
            for c in cookies:
                # التأكد من وجود القيم الأساسية
                if 'domain' not in c or 'name' not in c: continue
                
                domain = c['domain']
                flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                path = c.get('path', '/')
                secure = 'TRUE' if c.get('secure', False) else 'FALSE'
                
                # التعامل مع وقت الانتهاء
                expiry = c.get('expirationDate', c.get('expiry', 0))
                expiry = int(expiry) if expiry else 0
                
                name = c['name']
                value = c.get('value', '')
                
                f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expiry}\t{name}\t{value}\n")
        
        return temp_path
    except Exception as e:
        print(f"Cookie Conversion Error: {e}")
        return None

@app.route('/api/download', methods=['GET'])
def download_factory():
    # --- استلام الطلبات ---
    url = request.args.get('url')
    media_type = request.args.get('type', 'video')   # audio / video
    quality_req = request.args.get('q', '720')       # 1080, 720, 360, best
    out_format = request.args.get('fmt', 'mp4')      # mp4, mp3, mkv, wav...
    
    if not url: return jsonify({'error': 'URL missing'}), 400

    # 1. تحضير الكوكيز (الجوهر لتخطي حظر البوت)
    cookie_file = json_cookies_to_netscape('youtube.json')

    # 2. إعداد yt-dlp لاستخراج الرابط الخام (في السيرفر)
    # استخدام user agent لمتصفح حقيقي خداع يوتيوب
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'cookiefile': cookie_file,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        }
    }
    
    # تحديد صيغة السحب من يوتيوب بناء على طلبك
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
    file_title = "downloaded_media"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # محاولة سحب المعلومات
            info = ydl.extract_info(url, download=False)
            target_raw_url = info.get('url') # الرابط المباشر من سيرفر جوجل
            file_title = info.get('title', 'media')

    except Exception as e:
        if cookie_file and os.path.exists(cookie_file): os.unlink(cookie_file)
        # إرجاع الخطأ كما هو للعميل ليعرف السبب
        return jsonify({'error': f"Server Extraction Error: {str(e)}"}), 400

    if cookie_file and os.path.exists(cookie_file): os.unlink(cookie_file)

    # 3. إعداد FFMPEG (في السيرفر) للتحويل والبث
    cmd = [
        FFMPEG_BIN, '-y',
        '-re',
        '-headers', 'User-Agent: Mozilla/5.0',
        '-i', target_raw_url
    ]

    mimetype = 'application/octet-stream'

    # معالجة الصوت/الفيديو حسب المطلوب وتحديد الحاويات (Containers) المناسبة للـ PIPE
    if media_type == 'audio':
        cmd.append('-vn')
        if out_format == 'mp3':
            cmd += ['-acodec', 'libmp3lame', '-q:a', '2', '-f', 'mp3']
            mimetype = 'audio/mpeg'
        elif out_format == 'wav':
            cmd += ['-acodec', 'pcm_s16le', '-f', 'wav']
            mimetype = 'audio/wav'
        else: # aac/m4a
            cmd += ['-acodec', 'aac', '-f', 'adts']
            mimetype = 'audio/aac'
            out_format = 'aac' # pipe friendly for m4a content
    else:
        # فيديو
        if out_format == 'mp4':
            # أهم سطر: frag_keyframe+empty_moov يسمح بإنشاء ملف MP4 متدفق (Streamable)
            cmd += ['-c:v', 'copy', '-c:a', 'aac', '-movflags', 'frag_keyframe+empty_moov', '-f', 'mp4']
            mimetype = 'video/mp4'
        elif out_format == 'mkv':
            cmd += ['-c', 'copy', '-f', 'matroska']
            mimetype = 'video/x-matroska'
        else:
            # fallback
            cmd += ['-c:v', 'copy', '-c:a', 'aac', '-movflags', 'frag_keyframe+empty_moov', '-f', 'mp4']
            mimetype = 'video/mp4'

    cmd.append('-') # الإخراج للـ Stdout

    # دالة البث
    def generate_stream():
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            while True:
                chunk = process.stdout.read(16384) # 16KB
                if not chunk: break
                yield chunk
        except Exception:
            process.kill()
        finally:
            if process.poll() is None: process.terminate()
            process.stdout.close()
            process.stderr.close()

    final_name = f"{file_title}.{out_format}"
    # تنظيف الاسم للـ Header
    try: final_name.encode('latin-1')
    except: final_name = f"download.{out_format}"

    return Response(
        stream_with_context(generate_stream()),
        mimetype=mimetype,
        headers={"Content-Disposition": f"attachment; filename={final_name}"}
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
