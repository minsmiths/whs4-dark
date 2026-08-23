# CLAUDE.md §4.1 격리된 실행 환경. Tor · Python · Playwright · VNC를 한 컨테이너에 모두 포함한다.
FROM python:3.11-slim

# xvfb: 가상 디스플레이(:99) — 로그인 시 Chromium이 headed로 뜨는 화면.
# x11vnc: 그 가상 디스플레이를 VNC로 노출 — 로그인·챌린지 통과 시 사람이 여기 접속한다(§4.2-2).
# 평소 자동 크롤링(CMD, investigate.py)은 headless라 Xvfb/x11vnc를 띄우지 않는다 —
# VNC는 오직 아래 docker/login.sh(login_session.py) 경로에서만 켜진다.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tor curl xvfb x11vnc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

COPY . /app
RUN chmod +x docker/login.sh docker/wait-for-tor.sh

ENV DISPLAY=:99

# VNC 포트. `docker run` 시 반드시 로컬호스트에만 바인딩한다(예: -p 127.0.0.1:5900:5900) —
# Tor 9050 포트와 같은 원칙이다(CLAUDE.md §4.2-3). 0.0.0.0으로 열지 않는다.
EXPOSE 5900

# 주의: 아래 CMD/docker/login.sh 나 코드 어디에도 --no-sandbox / --disable-setuid-sandbox 를
# 추가하지 않는다. CI(security.yml)가 이미지 코드 전체에서 해당 문자열을 grep 하여 검증한다
# (CLAUDE.md §4.2-1).
#
# 기본 CMD는 평소 자동 크롤링(로그인 불필요 대상, 또는 이미 세션이 저장된 대상)이다.
# 로그인이 필요한 대상을 처음 등록할 때는 이 CMD 대신 VNC 로그인 진입점을 명시적으로 실행한다:
#   docker run --rm -p 127.0.0.1:5900:5900 -e VNC_PASSWORD=... <image> \
#       ./docker/login.sh <whitelist.yaml 의 name 또는 url>
CMD service tor start && ./docker/wait-for-tor.sh && python investigate.py "$TARGET_URL" --type "$SOURCE_TYPE"
