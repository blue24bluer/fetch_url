from flask import Flask, request, Response, stream_with_context
import subprocess
import shutil
import urllib.parse

app = Flask(__name__)

FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"

@app.route('/api/process_stream', methods=['GET'])
def process_stream():
    # نستلم الرابط الخام الطويل الذي استخرجه جهازك
    direct_url = request.args.get('url')
    file_title = request.args.get('title', 'downloaded_media')
    media_type = request.args.get('type', 'video')   # audio / video
    out_format = request.args.get('fmt', 'mp4')      # mp4, mp3, wav...

    if not direct_url:
        return "No URL provided", 400

    # فك تشفير الرابط في حال وصل مشفراً
    if "googlevideo" not in direct_url and "m3u8" not in direct_url and "http" in direct_url:
         # افتراض بسيط: ربما الرابط مشفر مرتين، لكن عادة flask يفك التشفير الأساسي
         pass

    # --- بناء أمر FFMPEG ---
    cmd = [
        FFMPEG_BIN, '-y',
        '-re',
        '-headers', 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 
        '-i', direct_url # الرابط المباشر
    ]

    mimetype = 'application/octet-stream'

    if media_type == 'audio':
        cmd += ['-vn'] 
        if out_format == 'mp3':
            cmd += ['-acodec', 'libmp3lame', '-q:a', '2', '-f', 'mp3']
            mimetype = 'audio/mpeg'
        elif out_format == 'wav':
            cmd += ['-acodec', 'pcm_s16le', '-f', 'wav']
            mimetype = 'audio/wav'
        elif out_format in ['m4a', 'aac']:
             cmd += ['-acodec', 'aac', '-f', 'adts']
             mimetype = 'audio/aac'
        else:
             cmd += ['-acodec', 'libmp3lame', '-f', 'mp3'] # Default
             out_format = 'mp3'
             mimetype = 'audio/mpeg'

    else:
        # VIDEO processing
        # نستخدم التحويل لضمان العمل لأن الـ Container الأصلي قد لا يكون مناسباً
        if out_format == 'mp4':
            cmd += ['-c:v', 'copy', '-c:a', 'aac', '-movflags', 'frag_keyframe+empty_moov', '-f', 'mp4']
            mimetype = 'video/mp4'
        elif out_format == 'mkv':
            cmd += ['-c', 'copy', '-f', 'matroska']
            mimetype = 'video/x-matroska'
        else:
            cmd += ['-c:v', 'copy', '-c:a', 'aac', '-movflags', 'frag_keyframe+empty_moov', '-f', 'mp4']
            mimetype = 'video/mp4'

    cmd.append('-') # Output to Pipe

    def generate():
        # بدء عملية FFMPEG
        # stderr نوجهه للـ PIPE لنتمكن من قراءة الأخطاء لو حدثت، ولكن لا نرسلها للعميل مباشرة
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            while True:
                data = process.stdout.read(16384) # 16KB chunks
                if not data:
                    break
                yield data
        except Exception as e:
            process.kill()
        finally:
            if process.poll() is None:
                process.terminate()
            process.stdout.close()
            process.stderr.close()

    final_filename = f"{file_title}.{out_format}"
    # تنظيف الاسم من أحرف UTF-8 المعقدة لتفادي أخطاء الهيدر
    try: 
        final_filename.encode('latin-1')
    except: 
        final_filename = f"media_file.{out_format}"

    return Response(
        stream_with_context(generate()),
        mimetype=mimetype,
        headers={"Content-Disposition": f"attachment; filename={final_filename}"}
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
