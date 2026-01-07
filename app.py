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
    if not os.path.exists(json_path):
        return None
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        temp = tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8', suffix='.txt')
        temp.write("# Netscape HTTP Cookie File\n")
        for cookie in cookies:
            domain = cookie.get('domain', '')
            flag = 'TRUE' if domain.startswith('.') else 'FALSE'
            path = cookie.get('path', '/')
            secure = 'TRUE' if cookie.get('secure', False) else 'FALSE'
            expiration = str(int(cookie.get('expirationDate', cookie.get('expiry', 0))))
            name = cookie.get('name', '')
            value = cookie.get('value', '')
            temp.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expiration}\t{name}\t{value}\n")
        temp.close()
        return temp.name
    except:
        return None

@app.route('/api/download_stream', methods=['GET'])
def download_stream():
    url = request.args.get('url')
    media_type = request.args.get('type', 'video') # audio / video
    quality = request.args.get('q', '720')
    
    if not url:
        return jsonify({'error': 'URL parameter is required'}), 400

    cookie_file = json_cookies_to_netscape('youtube.json')
    
    # 1. الحصول على رابط الـ m3u8 أو الرابط المباشر من yt-dlp
    ydl_opts = {
        'quiet': True, 'no_warnings': True, 'cookiefile': cookie_file,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
        # اختيار أفضل جودة متاحة تناسب الطلب
        target_url = None
        formats = info.get('formats', [])
        
        # منطق بسيط لاختيار الرابط لـ ffmpeg
        if media_type == 'audio':
            # نفضل m4a أو bestaudio
            selected = next((f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none'), None)
        else:
            # نفضل فيديو بجودة مناسبة (m3u8 أو http)
            target_h = int(quality) if quality.isdigit() else 720
            # ترتيب تنازلي للجودة ثم اختيار الأقرب
            formats.sort(key=lambda x: x.get('height') or 0, reverse=True)
            selected = next((f for f in formats if (f.get('height') or 0) <= target_h), formats[0])

        target_url = selected['url'] if selected else info['url']
        file_title = info.get('title', 'video')

    except Exception as e:
        if cookie_file: os.unlink(cookie_file)
        return jsonify({'error': str(e)}), 400

    if cookie_file: os.unlink(cookie_file)

    # 2. تجهيز أوامر FFMPEG للبث المباشر (Pipe)
    cmd = [
        FFMPEG_BIN,
        '-y',
        '-re',
        '-loglevel', 'error',
        '-i', target_url
    ]

    if media_type == 'audio':
        # تحويل إلى MP3 للبث
        cmd += ['-vn', '-acodec', 'libmp3lame', '-f', 'mp3', '-']
        mimetype = 'audio/mpeg'
        filename = f"{file_title}.mp3"
    else:
        # تحويل إلى MP4 قابل للبث (Fragmented MP4)
        # movflags ضروري جداً لأننا نكتب إلى pipe ولا يمكن العودة للخلف لكتابة الهيدر
        cmd += ['-c:v', 'copy', '-c:a', 'aac', '-movflags', 'frag_keyframe+empty_moov', '-f', 'mp4', '-']
        mimetype = 'video/mp4'
        filename = f"{file_title}.mp4"

    # دالة البث
    def generate_stream():
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            while True:
                # قراءة قطع صغيرة من البيانات
                data = process.stdout.read(4096)
                if not data:
                    break
                yield data
        except Exception:
            process.kill()
        finally:
            process.stdout.close()
            process.stderr.close()
            process.terminate()

    # ترميز اسم الملف لـ Header
    try:
        filename.encode('latin-1')
    except UnicodeEncodeError:
        filename = "downloaded_media"

    return Response(
        stream_with_context(generate_stream()),
        mimetype=mimetype,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.route('/api/info', methods=['GET'])
def get_info():
    """ نقطة مساعدة لجلب العنوان فقط للعميل إذا أراد """
    url = request.args.get('url')
    if not url: return jsonify({'error': 'No URL'}), 400
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            return jsonify({'title': info.get('title', 'download')})
    except:
        return jsonify({'title': 'download'})

if __name__ == '__main__':
    # يجب تثبيت ffmpeg على سيرفر الرندر
    app.run(host='0.0.0.0', port=5000)
