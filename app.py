import os
import json
import logging
from flask import Flask, request, jsonify
import yt_dlp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

def convert_cookies_to_netscape():
    try:
        json_path = 'youtube.json'
        netscape_path = '/tmp/cookies.txt'

        if not os.path.exists(json_path):
            return None
        
        with open(json_path, 'r') as f:
            cookies = json.load(f)
        
        with open(netscape_path, 'w') as f:
            f.write("# Netscape HTTP Cookie File\n")
            for c in cookies:
                domain = c.get('domain', '')
                flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                path = c.get('path', '/')
                secure = 'TRUE' if c.get('secure') else 'FALSE'
                expiry = str(int(c.get('expirationDate', c.get('expiry', 0))))
                name = c.get('name', '')
                value = c.get('value', '')
                f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expiry}\t{name}\t{value}\n")
        return netscape_path
    except Exception:
        return None

@app.route('/api/download', methods=['GET', 'POST'])
def download_media():
    url = request.values.get('url')
    m_type = request.values.get('type', 'video')
    quality = request.values.get('q', '')
    ext = request.values.get('ext', '')

    if not url:
        return jsonify({"status": "error", "message": "No URL provided"}), 400

    cookie_file = convert_cookies_to_netscape()

    # === التعديل الجوهري هنا: إجبار البروتوكول على HTTP مباشر ===
    # هذا يمنع ظهور روابط m3u8
    direct_link_filter = "[protocol^=http]"
    
    if m_type in ['audio', 'mp3']:
        # نريد ملف صوتي m4a برابط مباشر حصراً
        target_ext = ext if ext else 'm4a'
        fmt_ops = f'bestaudio[ext={target_ext}]{direct_link_filter}/bestaudio{direct_link_filter}/bestaudio'
    else:
        req_h = f'[height<={quality}]' if quality else ''
        # شرط وجود صوت وصورة + بروتوكول http مباشر
        req_video = f'[acodec!=none][vcodec!=none]{direct_link_filter}'
        
        # 1. طلبك المحدد (صوت+صورة + امتداد + جودة + رابط مباشر)
        f1 = f'best[ext={ext if ext else "mp4"}]{req_h}{req_video}'
        # 2. جودة محددة (صوت+صورة + رابط مباشر)
        f2 = f'best{req_h}{req_video}'
        # 3. أي فيديو (صوت+صورة + رابط مباشر) - عادة جودة 720 أو 360
        f3 = f'best{req_video}'
        
        fmt_ops = f'{f1}/{f2}/{f3}'

    ydl_opts = {
        'quiet': True,
        'noplaylist': True,
        'format': fmt_ops,
        'socket_timeout': 15,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
    }

    if cookie_file:
        ydl_opts['cookiefile'] = cookie_file

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            download_url = info.get('url')
            
            # محاولة احتياطية للبحث عن الرابط
            if not download_url and 'formats' in info:
                # بما أننا أجبرنا الصيغة على http، الرابط الموجود سيكون مباشراً
                download_url = info['formats'][-1]['url']
            
            return jsonify({
                "status": "success",
                "title": info.get('title'),
                "url": download_url, # سيكون الآن رابط تحميل مباشر وليس m3u8
                "ext": info.get('ext'),
                "details": {
                    "type": m_type,
                    "protocol": "direct_http_link" 
                }
            })

    except Exception as e:
        logger.error(str(e))
        return jsonify({"status": "error", "message": str(e).split(';')[0]}), 400

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
