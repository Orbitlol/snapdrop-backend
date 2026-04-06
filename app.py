from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import yt_dlp
import requests as req
import re

app = Flask(__name__)
CORS(app)

def clean_title(title):
    return re.sub(r'[^\w\s-]', '', title).strip()

YDL_BASE_OPTS = {
    'quiet': True,
    'skip_download': True,
    'extractor_args': {'youtube': {'player_client': ['android']}},
    'http_headers': {
        'User-Agent': 'com.google.android.youtube/17.36.4 (Linux; U; Android 12) gzip',
    }
}

@app.route('/')
def index():
    return jsonify({'status': 'SnapDrop API running'})

@app.route('/api/info')
def info():
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'Missing url'}), 400
    try:
        with yt_dlp.YoutubeDL(YDL_BASE_OPTS) as ydl:
            data = ydl.extract_info(url, download=False)
        title = clean_title(data.get('title', 'video'))
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

    format_map = {
        '1080p': 'best[height<=1080]',
        '720p':  'best[height<=720]',
        '480p':  'best[height<=480]',
        'audio': 'bestaudio/best',
    }
    ydl_format = format_map.get(fmt, 'best[height<=720]')
    is_audio = fmt == 'audio'
    ext = 'mp3' if is_audio else 'mp4'
    content_type = 'audio/mpeg' if is_audio else 'video/mp4'

    try:
        opts = {**YDL_BASE_OPTS, 'format': ydl_format}
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(url, download=False)
            title = clean_title(data.get('title', 'video'))
            direct_url = data.get('url') or data['requested_formats'][0]['url']

        r = req.get(direct_url, stream=True, headers={
            'User-Agent': 'com.google.android.youtube/17.36.4 (Linux; U; Android 12) gzip'
        }, timeout=60)

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
    
