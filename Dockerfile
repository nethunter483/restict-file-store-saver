FROM debian:12-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# System packages & Playwright browser libraries
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    procps \
    python3 \
    python3-pip \
    python3-venv \
    ca-certificates \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libx11-xcb1 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Official MEGAcmd for Debian 12
RUN curl -fsSL https://mega.nz/linux/repo/Debian_12/amd64/megacmd_2.5.2-1.1_amd64.deb -o /tmp/megacmd.deb \
    && apt-get update \
    && apt-get install -y /tmp/megacmd.deb \
    && rm /tmp/megacmd.deb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install --with-deps chromium

COPY . .

CMD ["python3", "bot.py"]
