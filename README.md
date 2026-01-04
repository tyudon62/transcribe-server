# Transcribe Server

動画URLから音声を抽出してWhisperで文字起こしするAPIサーバー

## 特徴

- **Groq API 優先**（超高速、60分の動画が1〜3分で完了）
- OpenAI API へのフォールバック
- 長い音声ファイルの自動分割

## 環境変数

| 変数名 | 必須 | 説明 |
|--------|------|------|
| `GROQ_API_KEY` | 推奨 | Groq API キー（高速） |
| `OPENAI_API_KEY` | どちらか必須 | OpenAI API キー（フォールバック） |

**優先順位**: GROQ_API_KEY があれば Groq を使用、なければ OpenAI

## Groq API キーの取得

1. https://console.groq.com にアクセス
2. Google アカウントでログイン
3. API Keys から新規作成
4. **無料枠**: 月20時間の音声処理

## エンドポイント

### POST /transcribe
動画URLから文字起こし

```json
{
  "url": "https://example.com/video.m3u8",
  "method": "ffmpeg",
  "referer": "https://example.com",
  "cookies": ""
}
```

### POST /transcribe-audio
音声ファイルをアップロードして文字起こし

### GET /health
ヘルスチェック（使用中のプロバイダーも返す）

## デプロイ

### Cloud Run

```bash
gcloud run deploy transcribe-server \
  --source . \
  --set-env-vars "GROQ_API_KEY=your_key" \
  --memory 2Gi \
  --timeout 600
```

## 処理時間の目安

| プロバイダー | 60分の動画 | 料金 |
|-------------|-----------|------|
| Groq | 1〜3分 | ~$0.11 |
| OpenAI | 5〜10分 | ~$0.36 |
