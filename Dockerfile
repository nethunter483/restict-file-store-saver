FROM debian:12-slim

# System tools aur Python install karein
RUN apt-get update && apt-get install -y \
    curl \
    procps \
    python3 \
    python3-pip \
    python3-venv \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Official MEGAcmd (Debian 12) install karein
RUN curl -fsSL https://mega.nz/linux/repo/Debian_12/amd64/megacmd_2.5.2-1.1_amd64.deb -o /tmp/megacmd.deb \
    && apt-get update \
    && apt-get install -y /tmp/megacmd.deb \
    && rm /tmp/megacmd.deb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Virtual environment setup
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python3", "bot.py"]
