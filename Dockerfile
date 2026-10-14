FROM python:3.13-slim

WORKDIR /app

COPY server/requirements.txt /app/server/requirements.txt
# 阿里云服务器加速：使用阿里云 PyPI 镜像（内网快；其他云厂商可换对应镜像源）
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r /app/server/requirements.txt

COPY server /app/server
COPY web /app/web
COPY config.json /app/config.json

# 音乐目录挂载点（默认 /data/music，可被 docker-compose 覆盖）
ENV MUSIC_DIR=/data/music

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
