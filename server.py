from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess
import os
import tempfile
import glob
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

    print(f"[transcribe] 開始: url={url}, method={method}")

    try:
        base_name = f"/tmp/{os.urandom(8).hex()}"
        audio_path = f"{base_name}.mp3"

        if method == 'ffmpeg':
            cmd = ['ffmpeg']
            if referer:
                cmd.extend(['-headers', f'Referer: {referer}\r\n'])
            if cookies:
                cmd.extend(['-headers', f'Cookie: {cookies}\r\n'])
            cmd.extend(['-i', url, '-vn', '-ac', '1', '-ar', '16000',
                '-b:a', '64k', audio_path, '-y'])
            print(f"[transcribe] ffmpegコマンド: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"[transcribe] ffmpegエラー: {result.stderr}")
                return jsonify({'success': False, 'error': f'ffmpeg failed: {result.stderr[:500]}'})
        else:
            # yt-dlp方式
            cmd = ['yt-dlp', '-x', '--audio-format', 'mp3', '--audio-quality', '0']
            if referer:
                cmd.extend(['--referer', referer])
            if cookies:
                cookie_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
                cookie_file.write(cookies)
                cookie_file.close()
                cmd.extend(['--cookies', cookie_file.name])
            cmd.extend(['-o', f'{base_name}.%(ext)s', url])
            print(f"[transcribe] yt-dlpコマンド: {' '.join(cmd)}")

            result = subprocess.run(cmd, capture_output=True, text=True)
            print(f"[transcribe] yt-dlp stdout: {result.stdout[:1000] if result.stdout else 'none'}")
            print(f"[transcribe] yt-dlp stderr: {result.stderr[:1000] if result.stderr else 'none'}")

            if cookies and 'cookie_file' in locals() and os.path.exists(cookie_file.name):
                os.remove(cookie_file.name)

            if result.returncode != 0:
                return jsonify({'success': False, 'error': f'yt-dlp failed: {result.stderr[:500]}'})

        # ファイルを探す（yt-dlpは拡張子を変える場合がある）
        possible_files = glob.glob(f"{base_name}.*")
        print(f"[transcribe] 生成されたファイル: {possible_files}")

        actual_audio_path = None
        for f in possible_files:
            if f.endswith(('.mp3', '.m4a', '.webm', '.opus', '.ogg', '.wav')):
                actual_audio_path = f
                break

        if not actual_audio_path or not os.path.exists(actual_audio_path):
            return jsonify({'success': False, 'error': f'Audio file not found. Generated files: {possible_files}'})

        file_size = os.path.getsize(actual_audio_path)
        print(f"[transcribe] 音声ファイル: {actual_audio_path}, サイズ: {file_size} bytes")

        if file_size < 1000:
            return jsonify({'success': False, 'error': f'Audio file too small: {file_size} bytes'})

        # mp3以外の場合はffmpegで変換
        if not actual_audio_path.endswith('.mp3'):
            print(f"[transcribe] mp3に変換中: {actual_audio_path}")
            convert_result = subprocess.run([
                'ffmpeg', '-i', actual_audio_path,
                '-vn', '-ac', '1', '-ar', '16000', '-b:a', '64k',
                audio_path, '-y'
            ], capture_output=True, text=True)
            os.remove(actual_audio_path)
            if convert_result.returncode != 0:
                return jsonify({'success': False, 'error': f'Audio conversion failed: {convert_result.stderr[:500]}'})
            actual_audio_path = audio_path

        # Whisper APIで文字起こし
        print(f"[transcribe] Whisper API呼び出し開始")
        client = get_openai_client()
        with open(actual_audio_path, 'rb') as f:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="ja",
                response_format="srt"
            )

        os.remove(actual_audio_path)
        print(f"[transcribe] 完了: {len(transcript)} 文字")
        return jsonify({'success': True, 'transcript': transcript})

    except Exception as e:
        import traceback
        print(f"[transcribe] エラー: {str(e)}")
        print(traceback.format_exc())
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
        file_size = os.path.getsize(temp_webm)
        print(f"[transcribe-audio] 受信ファイルサイズ: {file_size} bytes")

        if file_size < 1000:
            os.remove(temp_webm)
            return jsonify({'success': False, 'error': f'Audio file too small: {file_size} bytes'})

        # webmをmp3に変換（Whisper APIは一部のフォーマットのみサポート）
        try:
            result = subprocess.run([
                'ffmpeg', '-i', temp_webm,
                '-vn', '-ac', '1', '-ar', '16000', '-b:a', '64k',
                temp_mp3, '-y'
            ], capture_output=True, text=True)
            if result.returncode != 0:
                os.remove(temp_webm)
                return jsonify({'success': False, 'error': f'Audio conversion failed: {result.stderr[:500]}'})
        except subprocess.CalledProcessError as e:
            os.remove(temp_webm)
            return jsonify({'success': False, 'error': f'Audio conversion failed: {e.stderr}'})

        os.remove(temp_webm)

        # Whisper APIで文字起こし
        print(f"[transcribe-audio] Whisper API呼び出し開始")
        client = get_openai_client()
        with open(temp_mp3, 'rb') as f:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="ja",
                response_format="text"
            )

        os.remove(temp_mp3)
        print(f"[transcribe-audio] 完了: {len(transcript)} 文字")
        return jsonify({'success': True, 'transcript': transcript})

    except Exception as e:
        import traceback
        print(f"[transcribe-audio] エラー: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
