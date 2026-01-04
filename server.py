from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess
import os
import tempfile
import glob

app = Flask(__name__)
CORS(app)

# Whisper APIのファイルサイズ制限（25MB）
MAX_FILE_SIZE = 25 * 1024 * 1024
# 分割時のセグメント長（秒）- 10分ごとに分割
SEGMENT_DURATION = 600

def get_whisper_client():
    """Groq優先、なければOpenAIを使用"""
    groq_key = os.environ.get('GROQ_API_KEY')
    if groq_key:
        from groq import Groq
        print("[client] Groq API を使用（高速モード）")
        return Groq(api_key=groq_key), 'groq'
    
    openai_key = os.environ.get('OPENAI_API_KEY')
    if openai_key:
        from openai import OpenAI
        print("[client] OpenAI API を使用")
        return OpenAI(api_key=openai_key), 'openai'
    
    raise ValueError("GROQ_API_KEY または OPENAI_API_KEY が必要です")

def cleanup_files(*paths):
    """一時ファイルを安全に削除"""
    for path in paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception as e:
            print(f"[cleanup] ファイル削除失敗: {path}, error: {e}")

def cleanup_glob_files(pattern):
    """globパターンに一致するファイルを削除"""
    for f in glob.glob(pattern):
        cleanup_files(f)

def get_audio_duration(audio_path):
    """ffprobeで音声の長さを取得（秒）"""
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', audio_path
        ], capture_output=True, text=True)
        if result.returncode == 0:
            return float(result.stdout.strip())
    except Exception as e:
        print(f"[get_audio_duration] エラー: {e}")
    return None

def split_audio_for_whisper(audio_path, base_name):
    """長い音声ファイルを分割してWhisper APIの制限に対応"""
    file_size = os.path.getsize(audio_path)

    # 25MB以下ならそのまま返す
    if file_size <= MAX_FILE_SIZE:
        return [audio_path]

    print(f"[split_audio] ファイルサイズ {file_size} bytes > {MAX_FILE_SIZE} bytes、分割します")

    duration = get_audio_duration(audio_path)
    if not duration:
        print("[split_audio] 音声長さ取得失敗、そのまま試行")
        return [audio_path]

    # 分割数を計算
    num_segments = int(duration / SEGMENT_DURATION) + 1
    segments = []

    for i in range(num_segments):
        start_time = i * SEGMENT_DURATION
        segment_path = f"{base_name}_segment_{i:03d}.mp3"

        result = subprocess.run([
            'ffmpeg', '-i', audio_path,
            '-ss', str(start_time), '-t', str(SEGMENT_DURATION),
            '-vn', '-ac', '1', '-ar', '16000', '-b:a', '64k',
            segment_path, '-y'
        ], capture_output=True, text=True)

        if result.returncode == 0 and os.path.exists(segment_path):
            seg_size = os.path.getsize(segment_path)
            if seg_size > 1000:  # 空でないことを確認
                segments.append(segment_path)
                print(f"[split_audio] セグメント {i}: {seg_size} bytes")
        else:
            print(f"[split_audio] セグメント {i} 作成失敗")

    return segments if segments else [audio_path]

def transcribe_with_whisper(audio_paths, client, client_type, response_format="srt"):
    """複数の音声ファイルを文字起こしして結合"""
    all_transcripts = []

    # Groqはwhisper-large-v3、OpenAIはwhisper-1
    model = "whisper-large-v3" if client_type == 'groq' else "whisper-1"

    # Groqはsrt/vttをサポートしていないのでtextを使用
    actual_format = response_format
    if client_type == 'groq' and response_format in ['srt', 'vtt']:
        actual_format = 'text'
        print(f"[transcribe_with_whisper] Groqはsrt非対応のためtextフォーマットを使用")

    for i, path in enumerate(audio_paths):
        print(f"[transcribe_with_whisper] セグメント {i+1}/{len(audio_paths)}: {path} ({client_type}, {model}, {actual_format})")
        with open(path, 'rb') as f:
            transcript = client.audio.transcriptions.create(
                model=model,
                file=f,
                language="ja",
                response_format=actual_format
            )
        all_transcripts.append(transcript)

    # 結合
    return "\n\n".join(all_transcripts)

@app.route('/transcribe', methods=['POST'])
def transcribe():
    data = request.json
    url = data.get('url')
    method = data.get('method', 'yt-dlp')
    referer = data.get('referer', '')
    cookies = data.get('cookies', '')

    print(f"[transcribe] 開始: url={url}, method={method}")

    base_name = f"/tmp/{os.urandom(8).hex()}"
    audio_path = f"{base_name}.mp3"
    cookie_file_path = None
    temp_files = []  # クリーンアップ対象のファイルリスト

    try:
        if method == 'ffmpeg':
            cmd = ['ffmpeg']
            if referer:
                cmd.extend(['-headers', f'Referer: {referer}\r\n'])
            if cookies:
                cmd.extend(['-headers', f'Cookie: {cookies}\r\n'])
            cmd.extend(['-i', url, '-vn', '-ac', '1', '-ar', '16000',
                '-b:a', '64k', audio_path, '-y'])
            print(f"[transcribe] ffmpegコマンド: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                print(f"[transcribe] ffmpegエラー: {result.stderr}")
                return jsonify({'success': False, 'error': f'ffmpeg failed: {result.stderr[:500]}'})
            temp_files.append(audio_path)
        else:
            # yt-dlp方式
            cmd = ['yt-dlp', '-x', '--audio-format', 'mp3', '--audio-quality', '0']
            if referer:
                cmd.extend(['--referer', referer])
            if cookies:
                cookie_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
                cookie_file.write(cookies)
                cookie_file.close()
                cookie_file_path = cookie_file.name
                cmd.extend(['--cookies', cookie_file_path])
            cmd.extend(['-o', f'{base_name}.%(ext)s', url])
            print(f"[transcribe] yt-dlpコマンド: {' '.join(cmd)}")

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            print(f"[transcribe] yt-dlp stdout: {result.stdout[:1000] if result.stdout else 'none'}")
            print(f"[transcribe] yt-dlp stderr: {result.stderr[:1000] if result.stderr else 'none'}")

            if result.returncode != 0:
                return jsonify({'success': False, 'error': f'yt-dlp failed: {result.stderr[:500]}'})

        # ファイルを探す（yt-dlpは拡張子を変える場合がある）
        possible_files = glob.glob(f"{base_name}.*")
        temp_files.extend(possible_files)
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
            ], capture_output=True, text=True, timeout=300)
            if convert_result.returncode != 0:
                return jsonify({'success': False, 'error': f'Audio conversion failed: {convert_result.stderr[:500]}'})
            actual_audio_path = audio_path
            temp_files.append(audio_path)

        # 長い音声ファイルの場合は分割
        audio_segments = split_audio_for_whisper(actual_audio_path, base_name)
        if len(audio_segments) > 1:
            temp_files.extend(audio_segments)

        # Whisper APIで文字起こし（Groq優先）
        print(f"[transcribe] Whisper API呼び出し開始 ({len(audio_segments)}セグメント)")
        client, client_type = get_whisper_client()
        transcript = transcribe_with_whisper(audio_segments, client, client_type, "srt")

        print(f"[transcribe] 完了: {len(transcript)} 文字 (使用: {client_type})")
        return jsonify({'success': True, 'transcript': transcript, 'provider': client_type})

    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Operation timed out (10 min limit)'})
    except Exception as e:
        import traceback
        print(f"[transcribe] エラー: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)})
    finally:
        # 一時ファイルのクリーンアップ
        if cookie_file_path:
            cleanup_files(cookie_file_path)
        for f in temp_files:
            cleanup_files(f)
        # セグメントファイルもクリーンアップ
        cleanup_glob_files(f"{base_name}_segment_*")

@app.route('/transcribe-audio', methods=['POST'])
def transcribe_audio():
    """音声ファイルを受信して文字起こしを実行（録音機能からの利用向け）"""
    temp_webm = None
    temp_mp3 = None

    try:
        if 'audio' not in request.files:
            return jsonify({'success': False, 'error': 'No audio file provided'}), 400

        audio_file = request.files['audio']
        if audio_file.filename == '':
            return jsonify({'success': False, 'error': 'No audio file selected'}), 400

        # 一時ファイルとして保存
        base_name = f"/tmp/{os.urandom(8).hex()}"
        temp_webm = f"{base_name}.webm"
        temp_mp3 = f"{base_name}.mp3"

        audio_file.save(temp_webm)
        file_size = os.path.getsize(temp_webm)
        print(f"[transcribe-audio] 受信ファイルサイズ: {file_size} bytes")

        if file_size < 1000:
            return jsonify({'success': False, 'error': f'Audio file too small: {file_size} bytes'})

        # webmをmp3に変換（Whisper APIは一部のフォーマットのみサポート）
        result = subprocess.run([
            'ffmpeg', '-i', temp_webm,
            '-vn', '-ac', '1', '-ar', '16000', '-b:a', '64k',
            temp_mp3, '-y'
        ], capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            return jsonify({'success': False, 'error': f'Audio conversion failed: {result.stderr[:500]}'})

        # 長い録音の場合は分割
        audio_segments = split_audio_for_whisper(temp_mp3, base_name)

        # Whisper APIで文字起こし（Groq優先）
        print(f"[transcribe-audio] Whisper API呼び出し開始 ({len(audio_segments)}セグメント)")
        client, client_type = get_whisper_client()
        transcript = transcribe_with_whisper(audio_segments, client, client_type, "text")

        print(f"[transcribe-audio] 完了: {len(transcript)} 文字 (使用: {client_type})")
        return jsonify({'success': True, 'transcript': transcript, 'provider': client_type})

    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Operation timed out (5 min limit)'})
    except Exception as e:
        import traceback
        print(f"[transcribe-audio] エラー: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)})
    finally:
        cleanup_files(temp_webm, temp_mp3)
        if 'base_name' in locals():
            cleanup_glob_files(f"{base_name}_segment_*")

@app.route('/health', methods=['GET'])
def health():
    """ヘルスチェック + 使用中のプロバイダーを返す"""
    try:
        client, client_type = get_whisper_client()
        return jsonify({'status': 'ok', 'provider': client_type})
    except Exception as e:
        return jsonify({'status': 'ok', 'provider': 'none', 'error': str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
