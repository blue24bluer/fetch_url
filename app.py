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
    if not os.path.exists(json_path): return None
    try:
        with open(json_path, 'r', encoding='utf-8') as f: cookies = json.load(f)
        temp = tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8', suffix='.txt')
        temp.write("# Netscape HTTP Cookie File\n")
        for cookie in cookies:
            d, f_flag, p, s, e, n, v = (cookie.get(k, '') for k in ['domain', 'path', 'secure', 'expiry', 'expirationDate', 'name', 'value'])
            temp.write(f"{d}\t{'TRUE' if d.startswith('.') else 'FALSE'}\t{p}\t{'TRUE' if s else 'FALSE'}\t{e or 0}\t{n}\t{v}\n")
        temp.close()
        return temp.name
    except: return None

@app.route('/api/download_stream', methods=['GET'])
def download_stream():
    # --- استقبال البراميترات ---
    url = request.args.get('url')
    media_type = request.args.get('type', 'video')   # audio / video
    quality_req = request.args.get('q', '720')       # 1080, 720, 360, best
    out_format = request.args.get('fmt', 'mp4')      # mp4, mp3, mkv, wav
    
    if not url: return jsonify({'error': 'URL required'}), 400

    cookie_file = json_cookies_to_netscape('youtube.json')
    
    # --- 1. إعداد خيارات yt-dlp بناءً على الطلب ---
    # الهدف: الحصول على أفضل رابط خام يناسب المعايير قبل إعطائه لـ ffmpeg
    ydl_opts = {'quiet': True, 'no_warnings': True, 'cookiefile': cookie_file}
    
    # صياغة String اختيار الجودة لـ yt-dlp
    format_string = ""
    if media_type == 'audio':
        format_string = "bestaudio/best"
    else:
        # إذا طلب 'best' نتركه، وإلا نحدد الارتفاع
        if quality_req == 'best':
            format_string = f"bestvideo+bestaudio/best"
        else:
            try:
                h = int(quality_req)
                # نحاول جلب أفضل فيديو لا يتعدى الجودة المطلوبة مع الصوت
                format_string = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best"
            except:
                format_string = f"bestvideo[height<=720]+bestaudio/best[height<=720]/best"
    
    ydl_opts['format'] = format_string

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # في حالة كان الرابط مباشر ولم نحتاج لدمج (редкая ситуация مع yt-dlp format selectors القوية)
            # ولكن للتأكيد، نأخذ الرابط من المعلومات المستخرجة
            target_url = info.get('url') # للروابط المباشرة أو m3u8 النهائي المختار
            file_title = info.get('title', 'video')

    except Exception as e:
        if cookie_file: os.unlink(cookie_file)
        return jsonify({'error': f"Yt-dlp Error: {str(e)}"}), 400

    if cookie_file: os.unlink(cookie_file)

    # --- 2. بناء أمر FFMPEG الذكي ---
    # يقرأ من الرابط (أياً كان نوعه: مباشر، m3u8, dash)
    cmd = [
        FFMPEG_BIN, '-y', 
        '-re',                  # يحاول القراءة بسرعة الفيديو الحقيقية (اختياري للتدفق المستقر)
        '-headers', 'User-Agent: Mozilla/5.0', # بعض السيرفرات تحتاج هذا
        '-i', target_url
    ]

    mimetype = 'application/octet-stream'

    # إعدادات المخرجات حسب الصيغة المطلوبة
    if media_type == 'audio':
        # --- معالجة الصوت ---
        cmd += ['-vn'] # حذف الفيديو
        
        if out_format == 'mp3':
            cmd += ['-acodec', 'libmp3lame', '-q:a', '2', '-f', 'mp3']
            mimetype = 'audio/mpeg'
        elif out_format in ['m4a', 'aac']:
            # aac raw stream
            cmd += ['-acodec', 'aac', '-f', 'adts']
            mimetype = 'audio/aac'
        elif out_format == 'wav':
            cmd += ['-acodec', 'pcm_s16le', '-f', 'wav']
            mimetype = 'audio/wav'
        else:
            # افتراضي mp3
            cmd += ['-acodec', 'libmp3lame', '-f', 'mp3']
            mimetype = 'audio/mpeg'
            out_format = 'mp3'

    else:
        # --- معالجة الفيديو ---
        # استخدام -c copy قدر الإمكان لتخفيف الحمل على السيرفر
        # إلا إذا كانت الصيغة تتطلب حاوية مختلفة (Container) لا تدعم الكوديك الأصلي
        
        # عادة يوتيوب يعطي h264 (mp4) أو vp9 (webm)
        
        if out_format == 'mp4':
            # الـ MP4 يحتاج flag خاص ليعمل عبر الـ Pipe (Stream)
            # نستخدم aac للصوت لضمان التوافق
            cmd += ['-c:v', 'copy', '-c:a', 'aac', '-movflags', 'frag_keyframe+empty_moov', '-f', 'mp4']
            mimetype = 'video/mp4'
        elif out_format == 'mkv':
            # MKV يقبل كل شيء ويمر بسهولة عبر الـ pipe
            cmd += ['-c', 'copy', '-f', 'matroska']
            mimetype = 'video/x-matroska'
        elif out_format == 'webm':
            # webm يحتاج ترميز vp9 أو vp8 (ثقيل، لذا سنحاول النسخ إذا كان المصدر webm)
            # ولكن لضمان العمل سنضع copy، وإذا فشل FFMPEG سيتوقف
            cmd += ['-c', 'copy', '-f', 'webm'] 
            mimetype = 'video/webm'
        elif out_format == 'ts':
            cmd += ['-c', 'copy', '-f', 'mpegts']
            mimetype = 'video/mp2t'
        else:
            # افتراضي mp4
            cmd += ['-c:v', 'copy', '-c:a', 'aac', '-movflags', 'frag_keyframe+empty_moov', '-f', 'mp4']
            mimetype = 'video/mp4'
            out_format = 'mp4'

    # نهاية الأمر: الخروج للـ Pipe
    cmd.append('-')

    def generate_stream():
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            # القراءة chunk-by-chunk لإرسالها للعميل
            while True:
                data = process.stdout.read(8192) # 8KB chunks
                if not data:
                    break
                yield data
        except Exception:
            process.kill()
        finally:
            if process.poll() is None:
                process.terminate()
            process.stdout.close()
            process.stderr.close()

    final_filename = f"{file_title}.{out_format}"
    # تنظيف اسم الملف للهيدر
    try: final_filename.encode('latin-1')
    except: final_filename = f"download.{out_format}"

    return Response(
        stream_with_context(generate_stream()),
        mimetype=mimetype,
        headers={"Content-Disposition": f"attachment; filename={final_filename}"}
    )

@app.route('/api/info', methods=['GET'])
def get_info():
    url = request.args.get('url')
    if not url: return jsonify({'error': 'No URL'}), 400
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            return jsonify({'title': info.get('title', 'download')})
    except:
        return jsonify({'title': 'download'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
