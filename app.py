from flask import Flask, request, jsonify
import yt_dlp
import json
import os
import tempfile

app = Flask(__name__)

def json_cookies_to_netscape(json_path):
    if not os.path.exists(json_path):
        return None
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        netscape_content = "# Netscape HTTP Cookie File\n"
        for cookie in cookies:
            domain = cookie.get('domain', '')
            flag = 'TRUE' if domain.startswith('.') else 'FALSE'
            path = cookie.get('path', '/')
            secure = 'TRUE' if cookie.get('secure', False) else 'FALSE'
            expiration = str(int(cookie.get('expirationDate', cookie.get('expiry', 0))))
            name = cookie.get('name', '')
            value = cookie.get('value', '')
            netscape_content += f"{domain}\t{flag}\t{path}\t{secure}\t{expiration}\t{name}\t{value}\n"
        temp = tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8', suffix='.txt')
        temp.write(netscape_content)
        temp.close()
        return temp.name
    except Exception:
        return None

def get_direct_url(formats, media_type, quality):
    # ترتيب الصيغ للعثور على الأفضل
    # نستبعد m3u8 و manifest ونبحث عن http/https
    valid_formats = [f for f in formats if f.get('protocol') in ['http', 'https', 'https:1']]

    selected_format = None
    
    if media_type == 'audio':
        # بحث عن افضل صوت فقط (vcodec='none')
        audio_formats = [f for f in valid_formats if f.get('vcodec') == 'none']
        # ترتيب حسب حجم الملف (تقديراً للجودة)
        audio_formats.sort(key=lambda x: x.get('filesize') or 0, reverse=True)
        if audio_formats:
            selected_format = audio_formats[0]
            
    else: # Video
        # بحث عن فيديو يحتوي على صوت وصورة معاً (progressive)
        # ملاحظة: يوتيوب يحد هذه الملفات بجودة 720p كحد أقصى
        complete_formats = [
            f for f in valid_formats 
            if f.get('acodec') != 'none' and f.get('vcodec') != 'none'
        ]
        
        # فلترة حسب الجودة المطلوبة (اقل من او يساوي)
        target_height = int(quality)
        filtered = [f for f in complete_formats if f.get('height') and f.get('height') <= target_height]
        
        # ترتيب حسب الجودة من الأعلى للأسفل
        filtered.sort(key=lambda x: x.get('height') or 0, reverse=True)
        
        if filtered:
            selected_format = filtered[0]
        elif complete_formats: # اذا لم نجد الجودة المطلوبة نأخذ الأفضل المتاح
             complete_formats.sort(key=lambda x: x.get('height') or 0, reverse=True)
             selected_format = complete_formats[0]

    return selected_format

@app.route('/api/download', methods=['GET'])
def download_media():
    url = request.args.get('url')
    media_type = request.args.get('type', 'video') # audio or video
    quality = request.args.get('q', '720')
    custom_opts = request.args.get('opts')

    if not url:
        return jsonify({'error': 'URL parameter is required'}), 400

    cookie_file = json_cookies_to_netscape('youtube.json')

    # نطلب من yt-dlp جلب كافة البيانات الخام لنقوم نحن بالفلترة
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'cookiefile': cookie_file,
        'extract_flat': False, # تأكد من استخراج التفاصيل الكاملة
    }

    if custom_opts:
        try:
            ydl_opts.update(json.loads(custom_opts))
        except:
            pass

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # الدالة الخاصة بنا لاستخراج الرابط المباشر الصحيح
            best_format = get_direct_url(info.get('formats', []), media_type, quality)
            
            if cookie_file and os.path.exists(cookie_file):
                os.unlink(cookie_file)

            if not best_format:
                return jsonify({'error': 'No suitable direct download link found (Try strictly audio/video modes)'}), 404

            return jsonify({
                'status': 'success',
                'title': info.get('title'),
                'download_url': best_format.get('url'),
                'ext': best_format.get('ext'),
                'resolution': f"{best_format.get('height')}p" if best_format.get('height') else 'audio',
                'filesize': best_format.get('filesize'),
                'thumbnail': info.get('thumbnail'),
                'duration': info.get('duration')
            })

    except Exception as e:
        if cookie_file and os.path.exists(cookie_file):
            os.unlink(cookie_file)
        return jsonify({'error': str(e)}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
