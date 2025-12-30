FROM python:3.11-slim

# 必要なツールをインストール
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Denoをインストール
RUN curl -fsSL https://deno.land/x/install/install.sh | sh
ENV DENO_INSTALL="/root/.deno"
ENV PATH="$DENO_INSTALL/bin:$PATH"

# Pythonパッケージをインストール
RUN pip install yt-dlp openai flask flask-cors

COPY server.py .

CMD ["python", "server.py"]
