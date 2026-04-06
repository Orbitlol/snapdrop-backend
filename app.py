from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import yt_dlp
import requests as req
import re
import os
import tempfile

app = Flask(__name__)
CORS(app)

def clean_title(title):
    return re.sub(r'[^\w\s-]', '', title).strip()

YDL_BASE_OPTS = {
    'quiet': True,
    'extractor_args': {
        'youtube': {
            'player_client': ['android'],
        }
    },
    'http_headers': {
        'User-Agent': 'com.google.android.youtube/17.36.4 (Linux; U; Android 12) gzip',
    }
}

FORMAT_MAP = {
    '1080p': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]',
    '720p':  'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]',
    '480p':  'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[height<=480]',
    'audio': 'bestaudio[ext=m4a]/bestaudio',
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
        opts = {**YDL_BASE_OPTS, 'skip_download': True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(url, download=False)

        title = clean_title(data.get('title', 'video'))
        base = request.host_url.rstrip('/')

        return jsonify({
            'title': title,
            'thumbnail': data.get('thumbnail'),
            'formats': {
                '1080p': f"{base}/api/download?url={url}&format=1080p",
                '720p':  f"{base}/api/download?url={url}&format=720p",
                '480p':  f"{base}/api/download?url={url}&format=480p",
                'audio': f"{base}/api/download?url={url}&format=audio",
            }
        })
    except Exception as e:
        return jsonify({ 'error': str(e) }), 500


@app.route('/api/download')
def download():
    url = request.args.get('url')
    fmt = request.args.get('format', '720p')
    if not url:
        return jsonify({ 'error': 'Missing url' }), 400

    ydl_format = FORMAT_MAP.get(fmt, FORMAT_MAP['720p'])
    is_audio = fmt == 'audio'
    ext = 'mp3' if is_audio else 'mp4'
    content_type = 'audio/mpeg' if is_audio else 'video/mp4'

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            outpath = os.path.join(tmpdir, 'video.%(ext)s')

            ydl_opts = {
                **YDL_BASE_OPTS,
                'format': ydl_format,
                'outtmpl': outpath,
                'merge_output_format': 'mp4',
            }

            if is_audio:
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                data = ydl.extract_info(url, download=True)
                title = clean_title(data.get('title', 'video'))

            files = os.listdir(tmpdir)
            if not files:
                raise Exception('Download failed — no file produced.')

            filepath = os.path.join(tmpdir, files[0])
            safe_filename = f"{title}.{ext}"
            filesize = os.path.getsize(filepath)

            def generate():
                with open(filepath, 'rb') as f:
                    while True:
                        chunk = f.read(8192)
                        if not chunk:
                            break
                        yield chunk

            response = Response(generate(), content_type=content_type)
            response.headers['Content-Disposition'] = f'attachment; filename="{safe_filename}"'
            response.headers['Content-Length'] = filesize
            return response

    except Exception as e:
        return jsonify({ 'error': str(e) }), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
