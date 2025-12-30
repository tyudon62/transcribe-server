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
            result = subprocess.run([
                'ffmpeg', '-i', url, '-q:a', '0', '-map', 'a', audio_path
            ], capture_output=True, text=True)
        else:
            result = subprocess.run([
                'yt-dlp', 
                '--no-check-certificates',
                '--extract-audio', 
                '--audio-format', 'mp3',
                '--audio-quality', '0',
                '-o', audio_path.replace('.mp3', '.%(ext)s'),
                url
            ], capture_output=True, text=True)
            
            # yt-dlpは拡張子を自動で付けることがある
            if not os.path.exists(audio_path):
                # .mp3ファイルを探す
                for f in os.listdir('/tmp'):
                    if f.endswith('.mp3') and os.urandom(8).hex()[:8] in f:
                        audio_path = f'/tmp/{f}'
                        break
        
        if result.returncode != 0:
            return jsonify({
                'success': False, 
                'error': result.stderr,
                'stdout': result.stdout
            })
        
        # ファイル存在確認
        if not os.path.exists(audio_path):
            return jsonify({
                'success': False,
                'error': 'Audio file not created',
                'stderr': result.stderr,
                'stdout': result.stdout
            })
        
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
