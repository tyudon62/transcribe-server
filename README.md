# Transcribe Server

動画URLから音声を抽出してWhisperで文字起こしするAPIサーバー

## エンドポイント

POST /transcribe
- url: 動画URL
- method: "yt-dlp" or "ffmpeg"

## デプロイ

Cloud Runにデプロイ、環境変数にOPENAI_API_KEYを設定
