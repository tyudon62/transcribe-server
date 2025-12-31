from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess
import os
from openai import OpenAI

app = Flask(__name__)
CORS(app)

def get_openai_client():
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    return OpenAI(api_key=api_key)

@app.route('/transcribe', methods=['POST'])
def transcribe():
    data = request.json
    url = data.get('url')
    method = data.get('method', 'yt-dlp')

    try:
        audio_path = f"/tmp/{os.urandom(8).hex()}.mp3"

        if method == 'ffmpeg':
            # 25MB制限対策: 64kbps mono で圧縮
            subprocess.run([
                'ffmpeg', '-i', url, '-vn', '-ac', '1', '-ar', '16000',
                '-b:a', '64k', audio_path, '-y'
            ], check=True, capture_output=True)
        else:
            output_template = audio_path.replace('.mp3', '')
            subprocess.run([
                'yt-dlp', '-x', '--audio-format', 'mp3',
                '-o', f'{output_template}.%(ext)s', url
            ], check=True, capture_output=True)

        client = get_openai_client()
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
