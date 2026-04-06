from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import yt_dlp
import requests as req
import re
import os

app = Flask(__name__)
CORS(app)

# Path to cookies file (sits alongside app.py in the repo)
COOKIES_FILE = os.path.join(os.path.dirname(__file__), 'cookies.txt')

def clean_title(title):
    return re.sub(r'[^\w\s-]', '', title).strip()

def get_ydl_opts(extra={}):
    opts = {
        'quiet': True,
        'skip_download': True,
        # Use cookies for authenticated requests (avoids YouTube bot blocks)
        'cookiefile': COOKIES_FILE if os.path.exists(COOKIES_FILE) else None,
        'http_headers': {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
        },
        'extractor_args': {
            'youtube': {
                # Improved player client order for better compatibility
                'player_client': ['android', 'web'],  # Changed from tv_embedded
                'player_skip': ['javascript', 'configs'],
            }
        },
        # Add retries for transient failures
        'socket_timeout': 30,
        'retries': 3,
    }
    opts.update(extra)
    return opts

def get_best_single_url(data):
    """
    Return a single streamable URL + its real content-type.
    Prefers a progressive (combined video+audio) MP4.
    Falls back to best available single stream.
    """
    # Direct URL on the top-level info dict (progressive stream)
    if 'url' in data:
        return data['url'], data.get('ext', 'mp4')

    # Walk the formats list looking for a progressive (has both vcodec & acodec) MP4
    formats = data.get('formats', [])
    for f in reversed(formats):  # reversed = highest quality first
        if (f.get('vcodec') not in (None, 'none')
                and f.get('acodec') not in (None, 'none')
                and f.get('url')):
            return f['url'], f.get('ext', 'mp4')

    # Last resort: any format with a URL
    for f in reversed(formats):
        if f.get('url'):
            return f['url'], f.get('ext', 'mp4')

    raise Exception('Could not resolve a single streamable URL for this video')

@app.route('/')
def index():
    return jsonify({'status': 'SnapDrop API running'})

@app.route('/api/info')
def info():
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'Missing url'}), 400
    try:
        with yt_dlp.YoutubeDL(get_ydl_opts()) as ydl:
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
        error_msg = str(e)
        # Provide helpful YouTube-specific error messages
        if 'Sign in to confirm you\'re not a bot' in error_msg or 'bot' in error_msg.lower():
            return jsonify({'error': 'YouTube detected bot activity. Please update cookies or try later.'}), 403
        return jsonify({'error': error_msg}), 500

@app.route('/api/download')
def download():
    url = request.args.get('url')
    fmt = request.args.get('format', '720p')
    if not url:
        return jsonify({'error': 'Missing url'}), 400

    # Use progressive (combined) format strings — avoids DASH-only streams
    # that have no single URL to proxy.
    format_map = {
        '1080p': 'best[height<=1080][ext=mp4]/best[height<=1080]/best',
        '720p':  'best[height<=720][ext=mp4]/best[height<=720]/best',
        '480p':  'best[height<=480][ext=mp4]/best[height<=480]/best',
        'audio': 'bestaudio[ext=m4a]/bestaudio/best',
    }
    ydl_format = format_map.get(fmt, 'best[height<=720][ext=mp4]/best[height<=720]/best')
    is_audio = fmt == 'audio'
    ext = 'm4a' if is_audio else 'mp4'
    content_type = 'audio/mp4' if is_audio else 'video/mp4'

    try:
        opts = get_ydl_opts({'format': ydl_format})
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(url, download=False)
            title = clean_title(data.get('title', 'video'))
            direct_url, resolved_ext = get_best_single_url(data)

        # Stream the file back to the client
        # Pass through YouTube's headers so the request looks legitimate
        headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            'Referer': 'https://www.youtube.com/',
        }
        r = req.get(direct_url, stream=True, timeout=60, headers=headers)
        r.raise_for_status()

        def generate():
            for chunk in r.iter_content(chunk_size=65536):  # 64 KB chunks
                if chunk:
                    yield chunk

        response = Response(generate(), content_type=content_type)
        response.headers['Content-Disposition'] = (
            f'attachment; filename="{title}.{ext}"'
        )
        # Forward Content-Length so browsers show download progress
        cl = r.headers.get('Content-Length')
        if cl:
            response.headers['Content-Length'] = cl
        return response

    except Exception as e:
        error_msg = str(e)
        if 'Sign in to confirm you\'re not a bot' in error_msg or 'bot' in error_msg.lower():
            return jsonify({'error': 'YouTube detected bot activity. Please update cookies or try later.'}), 403
        return jsonify({'error': error_msg}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
