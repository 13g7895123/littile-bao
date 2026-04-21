FROM python:3.11-slim-bookworm

# 安裝 Wine 及相依套件（用於 cross-compile Windows exe）
RUN dpkg --add-architecture i386 && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        wget gnupg2 ca-certificates xvfb unzip && \
    mkdir -pm755 /etc/apt/keyrings && \
    wget -O /etc/apt/keyrings/winehq-archive.key https://dl.winehq.org/wine-builds/winehq.key && \
    echo "deb [signed-by=/etc/apt/keyrings/winehq-archive.key] https://dl.winehq.org/wine-builds/debian/ bookworm main" \
      > /etc/apt/sources.list.d/winehq.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends winehq-stable && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY src/ /src/
COPY build.spec /src/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
