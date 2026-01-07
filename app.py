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

@app.route('/api/download', methods=['GET'])
def download_media():
    url = request.args.get('url')
    media_type = request.args.get('type', 'video')
    quality = request.args.get('q', '720')
    
    if not url:
        return jsonify({'error': 'URL parameter is required'}), 400

    cookie_file = json_cookies_to_netscape('youtube.json')

    # صيغة الطلب لتجاهل m3u8 والتركيز على الملفات المباشرة (HTTP/HTTPS)
    if media_type == 'audio':
        # نطلب أفضل صوت بصيغة m4a لضمان عمل الرابط مباشرة، وإلا أي صوت يعمل
        format_selector = 'bestaudio[ext=m4a]/bestaudio'
    else:
        # 1. best[height<=Q]: أفضل ملف يحتوي (صوت+صورة) ولا يتعدى الجودة المطلوبة
        # 2. [protocol^=http]: يضمن أن البروتوكول http أو https وليس m3u8
        format_selector = f'best[height<={quality}][protocol^=http]/best[protocol^=http]'

    ydl_opts = {
        'format': format_selector,
        'quiet': True,
        'no_warnings': True,
        'cookiefile': cookie_file,
        # هذا الخيار مهم جداً لإخبار yt-dlp بعدم تحميل قوائم التشغيل بل الملف الخام
        'youtube_include_dash_manifest': False, 
        'youtube_include_hls_manifest': False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # نستخرج المعلومات بناءً على الفلتر أعلاه
            info = ydl.extract_info(url, download=False)
            
            # الرابط المباشر
            direct_url = info.get('url')
            
            if not direct_url:
                # محاولة أخيرة في قائمة التنسيقات إذا لم يرجع url مباشر في الجذر
                if 'formats' in info:
                    for f in info['formats']:
                        # نبحث عن الرابط الذي يطابق ما حددناه في الفلتر
                        if f.get('format_id') == info.get('format_id'):
                            direct_url = f.get('url')
                            break

            if cookie_file and os.path.exists(cookie_file):
                os.unlink(cookie_file)
            
            if not direct_url:
                 return jsonify({'error': 'No direct HTTP link found (video likely streams-only or copyrighted)'}), 404

            return jsonify({
                'status': 'success',
                'title': info.get('title'),
                'download_url': direct_url,
                'quality': info.get('format_note') or info.get('height'),
                'ext': info.get('ext'),
                'thumbnail': info.get('thumbnail'),
                'duration': info.get('duration')
            })

    except Exception as e:
        if cookie_file and os.path.exists(cookie_file):
            os.unlink(cookie_file)
        # رسالة خطأ واضحة
        return jsonify({'error': f"Extraction failed: {str(e)}"}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
