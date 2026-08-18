# MVP 테스트 / 보안 체크리스트

M6 완료 검증과 이후 모든 PR/배포 전에 사용하는 체크리스트입니다. 자동화 가능한 항목은
`.github/workflows/security.yml`에서 CI로도 검증합니다(각 행의 "CI" 표시 참고).

| 항목 | 확인 방법 | 통과 기준 | CI |
| --- | --- | --- | --- |
| 격리(자격증명) | `docker exec <container> env \| grep -iE "notion\|github\|token"` | 결과 0건 | - |
| 브라우저 샌드박스 | 코드에서 `--no-sandbox`, `--disable-setuid-sandbox` grep | 없음 | ✅ |
| Tor 포트 노출 범위 | `docker port <container>` 결과에서 9050 바인딩 주소 확인 | `127.0.0.1`에만 바인딩(또는 노출 안 함) | - |
| 산출물 경계 | 네트워크 전송 함수(`requests.post`, `smtplib`, `socket.send` 등) 호출부 grep — `output/` 관련 코드 제외 | 매칭 없음 | ✅ |
| 세션 재사용 | 세션 파일 존재 시 재실행 → 로그인 페이지로 리다이렉트 안 됨 / 파일 삭제 후 재실행 → 로그인 필요 상태로 정상 감지 | 두 경우 모두 로그에 정확히 구분되어 기록됨 | - |
| 자동 확정 금지 | §7.2 필드 목록에 대해 fixture 데이터로 `report_generator.py` 단위테스트 실행 | 해당 필드가 전부 빈칸/"안 봄"으로 출력됨 | ✅ (`tests/test_report_generator.py`) |
| 파일 다운로드 금지 | 파일 다운로드 관련 함수 호출부 grep, 첨부/샘플 링크 발견 시 존재 여부만 기록되는지 fixture로 확인 | 다운로드 코드 없음 | ✅ |
| PII 미저장 | `snapshots/` 폴더 전체를 이메일 정규식, 전화번호 패턴으로 grep | 매칭 0건 | - |
| 접근 로그 | `run_log.json`의 기록 수가 실제 요청 수와 일치하는지 확인 | 일치 | - |
| 가입 시도 없음 | Playwright 네트워크 로그(`page.on("request")`)에서 가입 페이지에 대한 POST 요청 존재 여부 확인 | POST 요청 0건 | - |
| 요구사항 커버리지 | 생성된 MD에서 23개 칸 중 키 자체가 통째로 누락된 칸이 있는지 확인 | 없음(전부 값/tri-state 중 하나로 존재) | - |
| 시크릿 하드코딩 | gitleaks 스캔 | 매칭 0건 | ✅ (`security.yml`) |

CI로 자동화되지 않은 항목("-" 표시)은 대상 사이트 접속·컨테이너 런타임이 필요하므로
M6과 실사이트 검증 시점에 사람이 수동으로 확인합니다.
