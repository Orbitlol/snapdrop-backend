from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import yt_dlp
import requests as req
import re

app = Flask(__name__)
CORS(app)

def clean_title(title):
    # Removes special characters to prevent filename errors
    return re.sub(r'[^\w\s-]', '', title).strip()

def get_ydl_opts(extra={}):
    opts = {
        'quiet': True,
        'skip_download': True,
        # Uses the cookie file you uploaded to bypass YouTube bot detection
        'cookiefile': 'cookies.txt', 
        'extractor_args': {
            'youtube': {
                'player_client': ['tv_embedded', 'web'],
                'player_skip': ['webpage', 'config'],
            }
        },
    }
    opts.update(extra)
    return opts

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
            'thumbnail': data.get('thumbnail'),
            'duration': data.get('duration'),
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
        opts = get_ydl_opts({'format': ydl_format})
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(url, download=False)
            title = clean_title(data.get('title', 'video'))
            
            # Determine the direct URL from the metadata
            if 'url' in data:
                direct_url = data['url']
            elif 'requested_formats' in data:
                direct_url = data['requested_formats'][0]['url']
            else:
                raise Exception('Could not get download URL')

        # Connect to the direct video link as a stream
        r = req.get(direct_url, stream=True, timeout=60)

        # The Generator: Pipes the video data directly to the user's browser
        def generate():
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk

        return Response(
            generate(),
            content_type=content_type,
            headers={"Content-Disposition": f"attachment; filename={title}.{ext}"}
        )

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Default Flask port
    app.run(host='0.0.0.0', port=5000)
    
