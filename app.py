from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import yt_dlp
import re

app = Flask(__name__)
CORS(app)

def clean_title(title):
    return re.sub(r'[^\w\s-]', '', title).strip()

@app.route('/')
def index():
    return jsonify({ 'status': 'SnapDrop API running' })

@app.route('/api/info')
def info():
    url = request.args.get('url')
    if not url:
        return jsonify({ 'error': 'Missing url' }), 400

    try:
        ydl_opts = { 'quiet': True, 'skip_download': True }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        title = clean_title(info.get('title', 'video'))
        base = request.host_url.rstrip('/')

        return jsonify({
            'title': title,
            'thumbnail': info.get('thumbnail'),
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
        filename = 'audio.mp3'
        content_type = 'audio/mpeg'
        postprocessors = [{ 'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3' }]
    elif fmt == 'video1080':
        ydl_format = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[height<=1080]/best'
        filename = 'video-1080p.mp4'
        content_type = 'video/mp4'
        postprocessors = []
    else:
        ydl_format = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]/best'
        filename = 'video-720p.mp4'
        content_type = 'video/mp4'
        postprocessors = []

    try:
        # Get the direct URL from yt-dlp without downloading
        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'format': ydl_format,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = clean_title(info.get('title', 'video'))

            # Get the best direct URL
            if 'url' in info:
                direct_url = info['url']
            elif 'requested_formats' in info:
                # Merge streams - use the video one and redirect
                direct_url = info['requested_formats'][0]['url']
            else:
                direct_url = info['url']

        # Stream the file through our server
        import requests as req
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        r = req.get(direct_url, stream=True, headers=headers, timeout=30)

        ext = 'mp3' if fmt == 'audio' else 'mp4'
        safe_filename = f"{title}.{ext}"

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
