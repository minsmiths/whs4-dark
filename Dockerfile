# CLAUDE.md §4.1 격리된 실행 환경. Tor · Python · Playwright를 한 컨테이너에 모두 포함한다.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends tor curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

COPY . /app

# 주의: 아래 CMD 나 코드 어디에도 --no-sandbox / --disable-setuid-sandbox 를 추가하지 않는다.
# CI(security.yml)가 이미지 코드 전체에서 해당 문자열을 grep 하여 검증한다 (CLAUDE.md §4.2-1).
CMD service tor start && sleep 3 && python investigate.py "$TARGET_URL" --type "$SOURCE_TYPE"
