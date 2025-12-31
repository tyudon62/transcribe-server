FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*
RUN pip install yt-dlp openai flask flask-cors

COPY server.py .

CMD ["python", "server.py"]
