# 개발 로드맵 — MVP (M0~M6)

요구사항 정의는 [SRS.md](SRS.md), 구현 규칙·시스템 구조는 [../CLAUDE.md](../CLAUDE.md)를 참조하세요.

---

## M0 — 격리 환경 구성 + 화이트리스트 확정

**세부 작업**
1. Docker 설치, `Dockerfile` 작성(CLAUDE.md §4.1) 및 이미지 빌드
2. 컨테이너 안 Tor 기동 확인: `docker exec <container> service tor status`
3. Tor 프록시 동작 확인: `docker exec <container> curl --socks5-hostname 127.0.0.1:9050 https://check.torproject.org/` → "Congratulations" 포함 확인
4. Chromium이 `--no-sandbox` 없이 정상 실행되는지 확인
5. 승인된 대상 1곳을 `whitelist.yaml`에 등록 — 최소 필드: `name`, `url`, `source_type`, `approved_by`, `approved_at`
   (`whitelist.example.yaml`을 복사해서 사용, 실제 파일은 커밋하지 않음)
6. 컨테이너 안에 외부 자격증명이 없는지 확인: `docker exec <container> env | grep -iE "notion|github|token"`

**산출물**: `Dockerfile`, `whitelist.yaml`
**완료 기준**: 컨테이너 안에서 Playwright로 등록된 대상 페이지를 요청해 HTML 응답(200자 이상)을 받으면 통과. 자격증명 확인 결과 0건.

---

## M1 — 세션 매니저 (`session_manager.py`)

**세부 작업**
1. VNC가 내장된 브라우저 이미지를 활용하거나 컨테이너에 VNC 서버를 추가
2. `save_session(source_id)`: 사람이 로그인 완료 후 `context.storage_state()`로 `sessions/<source_id>.json` 저장
3. `load_session(source_id)`: 저장된 세션 파일이 있으면 `storage_state=path`로 context 생성, 없으면 None 반환
4. `is_session_valid(page)`: 로그인 후에만 보이는 요소 확인해 True/False 반환
5. 세션 무효 시: 자동 재로그인 없이 `run_log.json`에 만료 이벤트 기록 후 해당 Collector 단계를 `BLOCKED("세션 만료")`로 반환, 다음 단계로 진행(전체 중단 아님)

**산출물**: `session_manager.py`, `sessions/<source_id>.json`(named volume), `run_log.json`
**완료 기준**: (a) VNC로 로그인 가능 (b) 세션 파일 유지한 채 재실행 → `is_session_valid()` True (c) 세션 파일 비운 뒤 재실행 → `BLOCKED` 기록되고 프로그램이 죽지 않고 계속 진행

---

## M2 — 가용성 체크 + 구조 크롤 (`availability.py`, `structure.py`)

**세부 작업 (availability)**
1. Playwright로 대상 URL 요청, 상태 코드·응답 시간 기록
2. 타임아웃(기본 30초) 시 `상태: 미확인`
3. 압수배너 키워드("seized" 등) 매칭 → `상태: 후보-OFFLINE(사람 확인 필요)`로만 기록
4. 도메인 파킹 페이지 패턴 매칭 → 동일하게 후보 처리
5. `Onion-Location` 헤더/본문 `.onion` 정규식 → 어니언 주소 후보

**세부 작업 (structure)**
1. 홈페이지 nav/메뉴 링크 추출 (대상 실제 마크업 확인 후 selector 확정)
2. 카테고리/서브포럼 제목 리스트 수집 (1단계 depth만)
3. 규칙/FAQ/가입 페이지 URL 탐색 후 본문 원문 수집

**산출물**: `availability.py`, `structure.py`, `snapshots/<source_id>/<timestamp>/`에 raw html
**완료 기준**: `상태`, `어니언 주소`, `어떤 곳인지`, `들어가는 법` 필드가 값 또는 tri-state로 채워짐. 미등록 URL 입력 시 즉시 에러.

---

## M3 — 통계 크롤 + 콘텐츠 표본 크롤 (`stats.py`, `content_sample.py`)

**세부 작업 (stats)**
1. 통계 영역 파싱 시도
2. 실패 시 페이지네이션 마지막 번호로 총량 추정
3. 목록 첫 페이지 최상단 타임스탬프 → `최근 게시일`

**세부 작업 (content_sample)**
1. 카테고리별 상위 N건(기본 50) 제목/날짜/작성자 수집 (`langdetect` 등 추가)
2. 언어감지 후 비중 집계 → `사용 언어`
3. 한국 관련 키워드 매칭 카운트 → `한국 관련 유출` 후보
4. 결과에 항상 표본 규모 명시(전체 아님)

**산출물**: `stats.py`, `content_sample.py`, `keywords/korea_keywords.txt`
**완료 기준**: `규모`, `상태`(신선도), `사용 언어`, `한국 관련 유출`(후보) 필드가 값 또는 tri-state로 채워짐. 표본 50건 미만에서도 에러 없이 동작.

**확장 (2026-08-23)**: `content_sample.crawl_site()` — 홈페이지에서 발견한 모든 카테고리(하위
서브포럼 포함)를 재귀적으로 다 돌며 게시글 헤드라인(제목/작성자/날짜)만 모은다(본문 페이지에는
들어가지 않음). `sample_list_url`을 매번 사람이 지정해줘야 하던 방식을 대체한다(명시적으로
지정하면 여전히 그쪽이 우선). 카테고리당 페이지네이션은 `config.SITE_MAP_MAX_PAGES_PER_CATEGORY`
(기본 5)까지만. 세션 만료/챌린지 감지(`challenge.py`, §4.2-6) 시 자동 재로그인은 하지 않고(§3-3)
`content_sample.CrawlInterrupted`를 던진다 — 그 시점까지 모은 결과는 체크포인트
(`config.CHECKPOINT_DIR`)에 남아 `investigate.py --resume`(`docker/run-crawl.ps1 -Resume`)으로
이어서 진행할 수 있다. 자세한 배경은 [progress-log/2026-08-23-handoff.md](../progress-log/2026-08-23-handoff.md) 참고.

---

## M4 — 교차참조 + 접근성 프로빙 + 유저 활동 집계

**세부 작업 (cross_reference)**
1. M2~M3 텍스트에서 정규식으로 외부 URL/`.onion`/`t.me/` 추출
2. 중복 제거 후 "발견된 언급" 리스트 (자동 확정 안 함)

**세부 작업 (access_probe)**
1. 비로그인 상태로 로그인 폼(`password` input) 존재 여부 확인
2. 존재하면 `가입 필요: true`, 가입 페이지 입력 필드 목록 수집 — **절대 제출하지 않음**

**세부 작업 (user_activity)**
1. 표본 게시글을 작성자 핸들로 그룹화, `Counter`로 집계
2. 상위 10명과 최근 활동일 기록, "판단 근거/반대 근거" 빈칸 템플릿 삽입

**산출물**: `cross_reference.py`, `access_probe.py`, `user_activity.py`
**완료 기준**: `연결된 곳`(후보), `가입 필요`, `들어가는 법`(가입조건), 유저 활동 섹션 채워짐. 가입 페이지에 POST 요청 없음(네트워크 로그 확인).

---

## M5 — 리포트 생성 + 전체 통합 (`report_generator.py`, `investigate.py`)

**세부 작업**
1. M1~M4 Collector를 순서대로 호출하는 `investigate.py` 작성 (①~⑦ 순서 고정)
2. Collector 반환 dict 취합 → CLAUDE.md §7 포맷 규칙대로 MD 문자열 생성
3. `FORBIDDEN_AUTO_FIELDS` 상수 선언, 해당 필드는 항상 빈칸/"안 봄" 강제 — 유닛테스트로 별도 검증
4. `output/<source_id>_<timestamp>.md`로 저장 후 콘솔에 경로 출력

**산출물**: `report_generator.py`, `investigate.py`, `output/*.md`
**완료 기준**: `docker run` 한 줄 실행으로 `output/`에 MD 파일 1개 생성. 23개 칸 전부 값/tri-state/빈칸 중 하나로 채워지고 통째로 누락된 칸 없음.

---

## M6 — MVP 완료 검증

**세부 작업**
1. 담당자 입회 하에 승인된 실제 대상 1곳으로 전체 파이프라인 1회 실행
2. [security-checklist.md](security-checklist.md) 전 항목 실행 및 결과 기록
3. 산출된 MD를 노션 "다크웹 조사 가이드"에 실제로 옮겨 적어보고 포맷 불일치 기록

**완료 기준**: 체크리스트 전 항목 통과. MD → 노션 이관 시 수작업 수정이 "사람 전결 필드 채우기" 수준을 넘지 않음.

---

## 확장 단계 (MVP 범위 아님)

Notion API 실시간 연동, 네트워크 격리 강제(Tor 전용 internal 네트워크), Host/Collector VM 분리,
사이트 간 자동 병합(압수배너·디자인 지문 매칭), Stats Engine 대시보드, 다중 사이트 스케줄러, MCP,
AI 기반 요약(원문 대신 구조화된 사실만 입력), Phase 2(위협 인텔리전스).
