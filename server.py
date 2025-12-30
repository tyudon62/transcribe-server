from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess
import os
from openai import OpenAI

app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

@app.route('/transcribe', methods=['POST'])
def transcribe():
    data = request.json
    url = data.get('url')
    method = data.get('method', 'yt-dlp')
    
    try:
        audio_path = f"/tmp/{os.urandom(8).hex()}.mp3"
        
        if method == 'ffmpeg':
            subprocess.run([
                'ffmpeg', '-i', url, '-q:a', '0', '-map', 'a', audio_path
            ], check=True)
        else:
            subprocess.run([
                'yt-dlp', '-x', '--audio-format', 'mp3',
                '-o', audio_path, url
            ], check=True)
        
        with open(audio_path, 'rb') as f:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="ja",
                response_format="srt"
            )
        
        os.remove(audio_path)
        return jsonify({'success': True, 'transcript': transcript})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
EOF\
# server.py
cat << 'EOF' > server.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess
import os
from openai import OpenAI

app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

@app.route('/transcribe', methods=['POST'])
def transcribe():
    data = request.json
    url = data.get('url')
    method = data.get('method', 'yt-dlp')
    
    try:
        audio_path = f"/tmp/{os.urandom(8).hex()}.mp3"
        
        if method == 'ffmpeg':
            subprocess.run([
                'ffmpeg', '-i', url, '-q:a', '0', '-map', 'a', audio_path
            ], check=True)
        else:
            subprocess.run([
                'yt-dlp', '-x', '--audio-format', 'mp3',
                '-o', audio_path, url
            ], check=True)
        
        with open(audio_path, 'rb') as f:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="ja",
                response_format="srt"
            )
        
        os.remove(audio_path)
        return jsonify({'success': True, 'transcript': transcript})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
