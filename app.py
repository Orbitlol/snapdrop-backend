from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import yt_dlp
import requests as req
import re

app = Flask(__name__)
CORS(app)

def clean_title(title):
    return re.sub(r'[^\w\s-]', '', title).strip()

# Android client headers to bypass YouTube bot detection
YDL_BASE_OPTS = {
    'quiet': True,
    'skip_download': True,
    'extractor_args': {
        'youtube': {
            'player_client': ['android'],
        }
    },
    'http_headers': {
        'User-Agent': 'com.google.android.youtube/17.36.4 (Linux; U; Android 12) gzip',
    }
}

@app.route('/')
def index():
    return jsonify({ 'status': 'SnapDrop API running' })

@app.route('/api/info')
def info():
    url = request.args.get('url')
    if not url:
        return jsonify({ 'error': 'Missing url' }), 400

    try:
        with yt_dlp.YoutubeDL(YDL_BASE_OPTS) as ydl:
            data = ydl.extract_info(url, download=False)

        title = clean_title(data.get('title', 'video'))
        base = request.host_url.rstrip('/')

        return jsonify({
            'title': title,
            'thumbnail': data.get('thumbnail'),
            'formats': {
                'video1080': f"{base}/api/download?url={url}&format=video1080",
                'video720':  f"{base}/api/download?url={url}&format=video720",
                'audio':     f"{base}/api/download?url={url}&format=audio",
            }
        })
    except Exception as e:
        return jsonify({ 'error': str(e) }), 500


@app.route('/api/download')
def download():
    url = request.args.get('url')
    fmt = request.args.get('format', 'video720')
    if not url:
        return jsonify({ 'error': 'Missing url' }), 400

    if fmt == 'audio':
        ydl_format = 'bestaudio/best'
        content_type = 'audio/mpeg'
        ext = 'mp3'
    elif fmt == 'video1080':
        ydl_format = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[height<=1080]/best'
        content_type = 'video/mp4'
        ext = 'mp4'
    else:
        ydl_format = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]/best'
        content_type = 'video/mp4'
        ext = 'mp4'

    try:
        ydl_opts = {**YDL_BASE_OPTS, 'format': ydl_format}

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            data = ydl.extract_info(url, download=False)
            title = clean_title(data.get('title', 'video'))

            if 'requested_formats' in data:
                direct_url = data['requested_formats'][0]['url']
            else:
                direct_url = data['url']

        safe_filename = f"{title}.{ext}"
        stream_headers = {
            'User-Agent': 'com.google.android.youtube/17.36.4 (Linux; U; Android 12) gzip'
        }
        r = req.get(direct_url, stream=True, headers=stream_headers, timeout=30)

        def generate():
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk

        response = Response(generate(), content_type=content_type)
        response.headers['Content-Disposition'] = f'attachment; filename="{safe_filename}"'
        if r.headers.get('Content-Length'):
            response.headers['Content-Length'] = r.headers['Content-Length']
        return response

    except Exception as e:
        return jsonify({ 'error': str(e) }), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
