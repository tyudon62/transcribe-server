from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess
import os
import tempfile
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
    referer = data.get('referer', '')
    cookies = data.get('cookies', '')

    try:
        audio_path = f"/tmp/{os.urandom(8).hex()}.mp3"

        if method == 'ffmpeg':
            cmd = ['ffmpeg']
            if referer:
                cmd.extend(['-headers', f'Referer: {referer}\r\n'])
            if cookies:
                cmd.extend(['-headers', f'Cookie: {cookies}\r\n'])
            cmd.extend(['-i', url, '-vn', '-ac', '1', '-ar', '16000',
                '-b:a', '64k', audio_path, '-y'])
            subprocess.run(cmd, check=True, capture_output=True)
        else:
            output_template = audio_path.replace('.mp3', '')
            cmd = ['yt-dlp', '-x', '--audio-format', 'mp3']
            if referer:
                cmd.extend(['--referer', referer])
            if cookies:
                cookie_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
                cookie_file.write(cookies)
                cookie_file.close()
                cmd.extend(['--cookies', cookie_file.name])
            cmd.extend(['-o', f'{output_template}.%(ext)s', url])
            subprocess.run(cmd, check=True, capture_output=True)
            if cookies and os.path.exists(cookie_file.name):
                os.remove(cookie_file.name)

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

@app.route('/transcribe-audio', methods=['POST'])
def transcribe_audio():
    """音声ファイルを受信して文字起こしを実行"""
    try:
        if 'audio' not in request.files:
            return jsonify({'success': False, 'error': 'No audio file provided'}), 400

        audio_file = request.files['audio']
        if audio_file.filename == '':
            return jsonify({'success': False, 'error': 'No audio file selected'}), 400

        # 一時ファイルとして保存
        temp_webm = f"/tmp/{os.urandom(8).hex()}.webm"
        temp_mp3 = f"/tmp/{os.urandom(8).hex()}.mp3"

        audio_file.save(temp_webm)

        # webmをmp3に変換（Whisper APIは一部のフォーマットのみサポート）
        try:
            subprocess.run([
                'ffmpeg', '-i', temp_webm,
                '-vn', '-ac', '1', '-ar', '16000', '-b:a', '64k',
                temp_mp3, '-y'
            ], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            os.remove(temp_webm)
            return jsonify({'success': False, 'error': f'Audio conversion failed: {e.stderr.decode()}'})

        os.remove(temp_webm)

        # Whisper APIで文字起こし
        client = get_openai_client()
        with open(temp_mp3, 'rb') as f:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="ja",
                response_format="text"
            )

        os.remove(temp_mp3)
        return jsonify({'success': True, 'transcript': transcript})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
