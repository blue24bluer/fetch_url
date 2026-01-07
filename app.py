from flask import Flask, request, jsonify, send_file
import yt_dlp
import json
import os
import tempfile
import requests
from urllib.parse import urlparse, urljoin
import subprocess

app = Flask(__name__)
DOWNLOAD_DIR = os.path.join(tempfile.gettempdir(), "media_downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

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
    valid_urls = []
    try:
        target_h = int(target_quality)
    except:
        target_h = 720

    for f in formats:
        if not f.get('url'):
            continue
        proto = f.get('protocol', '')
        vcodec = f.get('vcodec', 'none')
        acodec = f.get('acodec', 'none')
        height = f.get('height', 0)
        is_direct = 'https' in proto or 'http' in proto
        is_m3u8 = 'm3u8' in proto

        if media_type == 'audio':
            if vcodec == 'none' and acodec != 'none':
                score = f.get('abr', 0) or 0
                if is_direct: score += 1000
                valid_urls.append({'data': f, 'score': score})
        else:
            if vcodec != 'none' and acodec != 'none':
                current_h = height or 0
                score = current_h
                if current_h > target_h:
                    score = -1000
                if is_direct and not is_m3u8:
                    score += 5000
                valid_urls.append({'data': f, 'score': score})

    valid_urls.sort(key=lambda x: x['score'], reverse=True)
    if not valid_urls:
        return None
    return valid_urls[0]['data']

def sanitize_filename(name):
    return "".join(c for c in name if c.isalnum() or c in " _-").rstrip()

def download_hls_to_file(url, output_path, media_type="video"):
    tmp_m3u8 = tempfile.NamedTemporaryFile(delete=False, suffix=".m3u8").name
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    content = r.text
    with open(tmp_m3u8, "w", encoding="utf-8") as f:
        f.write(content)
    cmd = [
        "ffmpeg",
        "-protocol_whitelist", "file,crypto,data,https,http,tcp,tls",
        "-i", tmp_m3u8,
        "-y",
    ]
    if media_type == "audio":
        cmd += ["-vn", "-acodec", "libmp3lame", "-ab", "192k"]
    else:
        cmd += ["-c", "copy"]
    cmd.append(output_path)
    subprocess.run(cmd, check=True)
    os.unlink(tmp_m3u8)

@app.route('/api/download', methods=['GET'])
def download_media():
    url = request.args.get('url')
    media_type = request.args.get('type', 'video')
    quality = request.args.get('q', '720')

    if not url:
        return jsonify({'error': 'URL parameter is required'}), 400

    cookie_file = json_cookies_to_netscape('youtube.json')
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'cookiefile': cookie_file,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            chosen_format = filter_best_direct_url(info.get('formats', []), media_type, quality)
            if cookie_file and os.path.exists(cookie_file):
                os.unlink(cookie_file)

            if not chosen_format:
                final_url = info.get('url')
                if not final_url:
                    return jsonify({'error': 'No downloadable URL found'}), 404
                ext = "mp4" if media_type == "video" else "mp3"
            else:
                final_url = chosen_format['url']
                ext = chosen_format.get('ext') if chosen_format.get('ext') else ("mp4" if media_type=="video" else "mp3")

            filename = sanitize_filename(info.get('title', 'output')) + "." + ext
            output_path = os.path.join(DOWNLOAD_DIR, filename)

            if "m3u8" in final_url:
                download_hls_to_file(final_url, output_path, media_type)
            elif "http" in final_url or "https" in final_url:
                with requests.get(final_url, stream=True, timeout=120) as r:
                    r.raise_for_status()
                    with open(output_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)

            return jsonify({
                'status': 'success',
                'title': info.get('title'),
                'download_url': f"/media/{filename}",
                'type_detected': 'audio' if media_type == 'audio' else 'video',
                'quality': chosen_format.get('height') if chosen_format else 'unknown',
                'format': ext,
                'thumbnail': info.get('thumbnail'),
                'duration': info.get('duration')
            })

    except Exception as e:
        if cookie_file and os.path.exists(cookie_file):
            os.unlink(cookie_file)
        return jsonify({'error': str(e)}), 400

@app.route('/media/<path:filename>', methods=['GET'])
def serve_file(filename):
    path = os.path.join(DOWNLOAD_DIR, filename)
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    return jsonify({'error': 'File not found'}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
