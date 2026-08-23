#!/bin/sh
# VNC로 사람이 직접 로그인하는 1회성 진입점 (로드맵 M1, CLAUDE.md §4.2-2).
#
# 평소 자동 크롤링(Dockerfile의 기본 CMD)과는 별도로, 로그인이 필요한 대상을 처음 등록할
# 때만 명시적으로 실행한다:
#   docker run --rm -p 127.0.0.1:5900:5900 -e VNC_PASSWORD=<암호> <image> \
#       ./docker/login.sh <whitelist.yaml 의 name 또는 url>
#
# 암호는 이미지에 하드코딩하지 않고 실행 시점에 환경변수로 받는다. VNC 뷰어로
# 127.0.0.1:5900에 접속해 화면을 보며 로그인한 뒤, 컨테이너 로그에 뜨는 안내에 따라
# 터미널(docker attach 등)에서 Enter를 누르면 세션이 sessions/<name>.json 에 저장된다.

set -e

: "${VNC_PASSWORD:?VNC_PASSWORD 환경변수를 설정하세요 (예: -e VNC_PASSWORD=...)}"

mkdir -p /tmp/.vnc
x11vnc -storepasswd "$VNC_PASSWORD" /tmp/.vnc/passwd

Xvfb "$DISPLAY" -screen 0 1280x800x24 &
sleep 1

x11vnc -display "$DISPLAY" -forever -shared -rfbauth /tmp/.vnc/passwd -rfbport 5900 -bg -o /var/log/x11vnc.log

service tor start
"$(dirname "$0")/wait-for-tor.sh"

python login_session.py "$@"
