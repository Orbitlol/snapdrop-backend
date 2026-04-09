from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import yt_dlp
import requests as req
import re
import os

app = Flask(__name__)
CORS(app)

def clean_title(title):
    return re.sub(r'[^\w\s-]', '', title).strip()

COOKIES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookies.txt')

def get_ydl_opts(extra={}):
    opts = {
        'quiet': True,
        'nocheckcertificate': True,
        'geo_bypass': True,
    }
    if os.path.exists(COOKIES_PATH):
        opts['cookiefile'] = COOKIES_PATH
    opts.update(extra)
    return opts

def is_instagram(url):
    return 'instagram.com' in url

@app.route('/')
def index():
    cookie_exists = os.path.exists(COOKIES_PATH)
    return jsonify({'status': 'SnapDrop API running', 'cookies_found': cookie_exists})

@app.route('/api/info')
def info():
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'Missing url'}), 400
    try:
        with yt_dlp.YoutubeDL(get_ydl_opts()) as ydl:
            data = ydl.extract_info(url, download=False)
        title = clean_title(data.get('title', 'video') or 'video')
        base = request.host_url.rstrip('/')
        return jsonify({
            'title': title,
            'formats': {
                '1080p': f"{base}/api/download?url={url}&format=1080p",
                '720p':  f"{base}/api/download?url={url}&format=720p",
                '480p':  f"{base}/api/download?url={url}&format=480p",
                'audio': f"{base}/api/download?url={url}&format=audio",
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download')
def download():
    url = request.args.get('url')
    fmt = request.args.get('format', '720p')
    if not url:
        return jsonify({'error': 'Missing url'}), 400

    is_audio = fmt == 'audio'
    ext = 'mp3' if is_audio else 'mp4'
    content_type = 'audio/mpeg' if is_audio else 'video/mp4'

    if is_instagram(url):
        ydl_format = 'bestaudio/best' if is_audio else 'best'
    else:
        format_map = {
            '1080p': 'best[height<=1080]',
            '720p':  'best[height<=720]',
            '480p':  'best[height<=480]',
            'audio': 'bestaudio/best',
        }
        ydl_format = format_map.get(fmt, 'best[height<=720]')

    try:
        opts = get_ydl_opts({'format': ydl_format})
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(url, download=False)
            title = clean_title(data.get('title', 'video') or 'video')

            # Handle all possible URL locations
            direct_url = None
            if 'url' in data:
                direct_url = data['url']
            elif 'requested_formats' in data and data['requested_formats']:
                direct_url = data['requested_formats'][0]['url']
            elif 'formats' in data and data['formats']:
                direct_url = data['formats'][-1]['url']

            if not direct_url:
                raise Exception('Could not get download URL')

        r = req.get(direct_url, stream=True, timeout=60)

        def generate():
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk

        response = Response(generate(), content_type=content_type)
        response.headers['Content-Disposition'] = f'attachment; filename="{title}.{ext}"'
        return response

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
