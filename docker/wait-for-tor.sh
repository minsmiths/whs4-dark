#!/bin/sh
# Tor가 고정된 몇 초가 아니라 "실제로 회선을 구성해 요청을 중계할 수 있는 상태"가 될 때까지
# 기다린다. development-plan.md M0 완료 기준의 검증 방법(check.torproject.org)을 그대로
# 재사용한다 — 실제 대상 사이트가 아니라 Tor 프로젝트가 공식 제공하는 연결 확인용 페이지다.
#
# 이 스크립트가 없으면(고정 sleep만 쓰면) 컨테이너를 막 켰을 때 Tor가 아직 부트스트랩 중인
# 상태로 첫 크롤링 요청이 나가서, 대상 사이트와 무관하게 타임아웃이 나는 경우가 흔하다.

set -e

max_wait_sec=${TOR_BOOTSTRAP_MAX_WAIT_SEC:-60}
waited=0

until curl --socks5-hostname 127.0.0.1:9050 -m 5 -s https://check.torproject.org/ \
    | grep -q "Congratulations"; do
    waited=$((waited + 2))
    if [ "$waited" -ge "$max_wait_sec" ]; then
        echo "Tor가 ${max_wait_sec}초 안에 부트스트랩되지 않았습니다 (네트워크/방화벽 확인 필요)." >&2
        exit 1
    fi
    sleep 2
done

echo "Tor 부트스트랩 완료 확인됨 (약 ${waited}초 소요)"
