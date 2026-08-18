# 소프트웨어 요구사항 명세서 (SRS)

**프로젝트**: darkweb-crawler
**버전**: v0.6 — MVP
**상태**: 초안

> 이 문서는 **무엇을 만들 것인가**를 정리합니다.
> 구현 규칙·시스템 구조·Collector 규격·MD 포맷의 원본은 [../CLAUDE.md](../CLAUDE.md)이며,
> 두 문서가 충돌할 경우 CLAUDE.md가 우선합니다.

---

## 1. 목적 및 범위

다크웹(Tor 히든서비스) 포럼 1곳의 URL을 입력하면, 가용성·구조·통계·콘텐츠 표본·교차참조·접근성·
유저 활동 7개 항목을 자동 수집해 노션 "다크웹 조사 가이드" 23개 칸 구조의 MD 초안을 산출한다.

**포함 (MVP)**: 화이트리스트 검증, 세션 재사용, Cloudflare 챌린지 사람 개입 대응, 구조/통계/콘텐츠
표본/교차참조/접근성/유저 활동 Collector 7종, MD 리포트 생성.

**제외 (v0.6 범위 아님)**: Notion 실시간 API 연동, 사이트 간 자동 병합, 다중 사이트 스케줄러,
대시보드 GUI, 위협 인텔 알림(Phase 2), AI 기반 요약. → [development-plan.md](development-plan.md) 확장 단계 절 참고.

## 2. 용어

| 용어 | 정의 |
| --- | --- |
| Collector | 대상 사이트에 접속해 원문을 가져오고 값을 추출하는 모듈 (`collectors/*.py`) |
| tri-state | Collector 반환값의 세 가지 명시적 상태: 확인함 / `CONFIRMED_ABSENT`(없음) / `BLOCKED`(못 봄) |
| 후보(candidate) | 자동으로 확정하지 않고 사람 검토를 기다리는 값 (예: OFFLINE 후보, 한국 관련 유출 후보) |
| 화이트리스트 | 크롤링이 허용된 대상 목록. `whitelist.yaml`에 사람이 직접 등록 |

## 3. 기능 요구사항

| ID | 요구사항 | 담당 모듈 | 우선순위 |
| --- | --- | --- | --- |
| FR-1 | 화이트리스트에 없는 URL 입력 시 즉시 거부한다 | `investigate.py` | M |
| FR-2 | 로그인 필요 대상은 저장된 세션을 재사용하고, 만료 시 자동 재로그인하지 않는다 | `session_manager.py` | M |
| FR-3 | 모든 Playwright 요청은 Tor SOCKS5 프록시를 경유하며 브라우저 샌드박스를 유지한다 | `config.py` | M |
| FR-4 | Cloudflare 등 챌린지 감지 시 자동 우회하지 않고 VNC로 사람 개입을 기다린다 | 공통 | M |
| FR-5 | 홈페이지 nav/메뉴에서 카테고리를 1단계 depth까지 수집한다 | `collectors/structure.py` | M |
| FR-6 | 규칙/FAQ/가입 페이지 원문을 요약 없이 인용 형태로 수집한다 | `collectors/structure.py` | M |
| FR-7 | 회원수·게시글수·최근 게시일을 파싱하거나(실패 시) 페이지네이션으로 추정한다 | `collectors/stats.py` | M |
| FR-8 | 카테고리별 상위 N건(기본 50)의 제목/날짜/작성자를 수집하고 키워드로 카운트한다 | `collectors/content_sample.py` | M |
| FR-9 | 표본 통계는 항상 "샘플 N건 기준, 전체 아님"을 명시한다 | `report_generator.py` | M |
| FR-10 | 수집 텍스트에서 외부 URL/`.onion`/`t.me/` 패턴을 추출해 "발견"으로만 기록한다 | `collectors/cross_reference.py` | M |
| FR-11 | 로그인 폼 존재 여부와 가입 페이지 입력 필드를 기록하되 절대 제출하지 않는다 | `collectors/access_probe.py` | M |
| FR-12 | 표본 게시글을 작성자 핸들로 그룹화해 상위 10명과 최근 활동일을 기록한다 | `collectors/user_activity.py` | M |
| FR-13 | 동일인 여부는 판단하지 않고 "판단 근거/반대 근거" 빈칸을 MD에 만든다 | `collectors/user_activity.py` | M |
| FR-14 | §7.2 금지 필드는 항상 빈칸/"안 봄"으로 강제한다 | `report_generator.py` | M |
| FR-15 | 결과는 `output/<source_id>_<timestamp>.md` 하나만 컨테이너 밖으로 반출한다 | `investigate.py` | M |

## 4. 비기능 요구사항

| ID | 요구사항 | 검증 방법 |
| --- | --- | --- |
| NFR-1 | 컨테이너 안에 Notion/GitHub 등 외부 자격증명이 없다 | `docker exec <container> env \| grep -iE "notion\|github\|token"` → 0건 |
| NFR-2 | Chromium 실행에 `--no-sandbox`, `--disable-setuid-sandbox`를 쓰지 않는다 | 코드 grep (CI `security.yml`) |
| NFR-3 | Tor SOCKS 포트는 로컬호스트에만 바인딩된다 | `docker port <container>` 확인 |
| NFR-4 | 컨테이너 밖으로 나가는 파일은 결과 MD 하나뿐이다 | 코드 전체에서 네트워크 전송 함수 grep (`output/` 제외) |
| NFR-5 | PII 원문을 저장하지 않는다 (존재 여부/유형만) | `snapshots/`를 이메일·전화번호 정규식으로 grep → 0건 |
| NFR-6 | 유출 파일을 다운로드하지 않는다 | 파일 다운로드 함수 호출부 grep → 없음 |
| NFR-7 | 요청 간 3~5초 랜덤 지연을 적용한다 | 코드 리뷰 |
| NFR-8 | 모든 요청을 로그에 남긴다 | `run_log.json` 기록 수 = 실제 요청 수 |

## 5. 요구사항 추적

| CLAUDE.md §2 요구사항 | 관련 FR | 담당 모듈 |
| --- | --- | --- |
| 1. 로그인 상태 유지 | FR-2 | `session_manager.py` |
| 2. 안티봇 통과 | FR-3, FR-4 | `config.py` |
| 3. 사이트 구조 | FR-5, FR-6, FR-10 | `collectors/structure.py`, `cross_reference.py` |
| 4. 활성화 정도 | FR-7 | `collectors/stats.py` |
| 5. 필터 기반 통계 | FR-8, FR-9 | `collectors/content_sample.py` |
| 6. 운영 방식 | FR-6 | `collectors/structure.py` |
| 7. 유저 활동 | FR-12, FR-13 | `collectors/user_activity.py` |

## 6. 미확정 사항

- 승인된 실제 대상 URL 1곳 (M0에서 `whitelist.yaml`에 등록)
- Cloudflare 우회를 위한 VNC 이미지 선정 (M1)
- 대상 사이트별 CSS selector (실제 마크업 확인 후 확정, M2)

확정 시 이 문서와 [CLAUDE.md](../CLAUDE.md)를 함께 갱신합니다.
