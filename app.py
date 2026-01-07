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
    custom_opts = request.args.get('opts')

    if not url:
        return jsonify({'error': 'URL parameter is required'}), 400

    cookie_file = json_cookies_to_netscape('youtube.json')

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'cookiefile': cookie_file,
    }

    if media_type == 'audio':
        ydl_opts['format'] = 'bestaudio/best'
    else:
        ydl_opts['format'] = f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best'

    if custom_opts:
        try:
            ydl_opts.update(json.loads(custom_opts))
        except:
            pass

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            direct_url = info.get('url')
            if not direct_url: 
                formats = info.get('formats', [])
                if formats:
                    direct_url = formats[-1].get('url')
            
            if cookie_file:
                os.unlink(cookie_file)

            if not direct_url:
                return jsonify({'error': 'Could not extract direct URL'}), 500

            return jsonify({
                'status': 'success',
                'title': info.get('title'),
                'download_url': direct_url,
                'thumbnail': info.get('thumbnail'),
                'duration': info.get('duration')
            })

    except Exception as e:
        if cookie_file and os.path.exists(cookie_file):
            os.unlink(cookie_file)
        return jsonify({'error': str(e)}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
