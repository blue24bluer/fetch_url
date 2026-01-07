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

def filter_best_direct_url(formats, media_type, target_quality):
    """
    دالة يدوية لتصفية الروابط بدلاً من الاعتماد على yt-dlp
    لتجنب خطأ Format Not Available
    """
    valid_urls = []
    
    # تحويل الجودة لرقم للمقارنة
    try:
        target_h = int(target_quality)
    except:
        target_h = 720

    for f in formats:
        # استبعاد الفيديوهات بدون روابط
        if not f.get('url'):
            continue
            
        proto = f.get('protocol', '')
        vcodec = f.get('vcodec', 'none')
        acodec = f.get('acodec', 'none')
        height = f.get('height', 0)
        
        # تصنيف الروابط
        is_direct = 'https' in proto or 'http' in proto
        is_m3u8 = 'm3u8' in proto
        
        # Audio logic
        if media_type == 'audio':
            # نبحث عن ملف صوتي فقط، ويفضل أن يكون direct
            if vcodec == 'none' and acodec != 'none':
                score = f.get('abr', 0) or 0
                if is_direct: score += 1000 # نعطي أولوية للرابط المباشر
                valid_urls.append({'data': f, 'score': score})

        # Video logic
        else:
            # نريد ملفاً يحتوي على صوت وصورة معاً (ملف كامل)
            if vcodec != 'none' and acodec != 'none':
                current_h = height or 0
                score = current_h
                
                # خصم نقاط إذا كانت الجودة أعلى من المطلوب (لنحترم رغبة المستخدم)
                if current_h > target_h:
                    score = -1000 
                
                # نعطي أولوية قصوى للملفات المباشرة MP4
                if is_direct and not is_m3u8:
                    score += 5000
                
                valid_urls.append({'data': f, 'score': score})

    # ترتيب النتائج حسب الـ Score
    valid_urls.sort(key=lambda x: x['score'], reverse=True)

    if not valid_urls:
        return None
    
    return valid_urls[0]['data']

@app.route('/api/download', methods=['GET'])
def download_media():
    url = request.args.get('url')
    media_type = request.args.get('type', 'video')
    quality = request.args.get('q', '720')
    
    if not url:
        return jsonify({'error': 'URL parameter is required'}), 400

    cookie_file = json_cookies_to_netscape('youtube.json')

    # نطلب من yt-dlp كل الصيغ دون قيود لنتجنب الخطأ
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'cookiefile': cookie_file,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # نجلب المعلومات الخام
            info = ydl.extract_info(url, download=False)
            
            # نستخدم دالتنا الخاصة لاختيار الرابط
            chosen_format = filter_best_direct_url(info.get('formats', []), media_type, quality)
            
            # تنظيف الكوكيز
            if cookie_file and os.path.exists(cookie_file):
                os.unlink(cookie_file)

            if not chosen_format:
                # حل أخير: نرسل أي رابط موجود في الجذر
                final_url = info.get('url')
                if not final_url:
                     return jsonify({'error': 'No downloadable URL found'}), 404
            else:
                final_url = chosen_format['url']
                
            return jsonify({
                'status': 'success',
                'title': info.get('title'),
                'download_url': final_url,
                'type_detected': 'audio' if media_type == 'audio' else 'video',
                'quality': chosen_format.get('height') if chosen_format else 'unknown',
                'format': chosen_format.get('ext') if chosen_format else 'unknown',
                'thumbnail': info.get('thumbnail'),
                'duration': info.get('duration')
            })

    except Exception as e:
        if cookie_file and os.path.exists(cookie_file):
            os.unlink(cookie_file)
        return jsonify({'error': str(e)}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
