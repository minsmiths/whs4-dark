# darkweb-crawler

승인된 다크웹(Tor 히든서비스) 포럼 URL 하나를 넣으면, 격리된 Docker 컨테이너 안에서
로그인·크롤링·분석을 전부 자동으로 수행하고, 조사 초안 MD 파일 하나를 산출하는 CLI 도구입니다.

- 무엇을·왜: [CLAUDE.md](CLAUDE.md) — 프로젝트 계약서(요구사항·준수사항·시스템 구조·Collector 규격 원본)
- 요구사항 명세: [docs/SRS.md](docs/SRS.md)
- 개발 로드맵(M0~M6): [docs/development-plan.md](docs/development-plan.md)
- 보안 위협 모델: [docs/threat-model.md](docs/threat-model.md)
- PR/배포 전 체크리스트: [docs/security-checklist.md](docs/security-checklist.md)

> 이 저장소는 스캐폴딩 단계입니다. 코드는 [CLAUDE.md](CLAUDE.md)의 규격을 따르는 뼈대(skeleton)이며,
> 대상 사이트별 selector·파싱 로직은 실제 승인된 대상이 정해진 뒤 채웁니다(§3-8 — 실 사이트 접속은
> 담당자 입회 하에만 검증).

---

## 실행 방법 (완성 후 기준)

```bash
docker build -t darkweb-crawler .
docker run --rm \
  -e TARGET_URL=https://example.onion \
  -e SOURCE_TYPE=forum \
  -v $(pwd)/output:/app/output \
  -v crawler-state:/app/sessions \
  -v crawler-state:/app/snapshots \
  darkweb-crawler
```

`SOURCE_TYPE`은 사람이 직접 지정합니다(자동 추정 안 함) — `forum` / `marketplace` / `dls` / `paste` 중 하나.
MVP는 `forum`만 실제 구현하고 나머지는 뼈대만 둡니다. (CLAUDE.md §4.5)

## 저장소 구조

```
darkweb-crawler/
├── investigate.py            # 진입점 CLI — Collector ①~⑦ 순서 고정 호출
├── config.py                 # Tor 프록시 주소, 타임아웃 등 설정
├── session_manager.py        # 로그인 세션 저장/재사용
├── report_generator.py       # 수집 결과 → MD 파일 변환, §7.2 금지 필드 강제
├── collectors/
│   ├── availability.py       # ① 가용성 체크
│   ├── structure.py          # ② 구조 크롤
│   ├── stats.py               # ③ 통계 크롤
│   ├── content_sample.py     # ④ 콘텐츠 표본 크롤
│   ├── cross_reference.py    # ⑤ 교차참조 크롤
│   ├── access_probe.py       # ⑥ 접근성 프로빙
│   └── user_activity.py      # ⑦ 유저 활동 집계
├── keywords/korea_keywords.txt
├── whitelist.example.yaml    # 커밋 O — whitelist.yaml 필드 예시
├── whitelist.yaml            # 커밋 X — 실제 승인 대상 (.gitignore)
├── sessions/  snapshots/     # named volume 마운트 지점 (내용물 커밋 X)
├── output/                   # 결과 MD 산출 위치 (내용물 기본 커밋 X)
├── tests/
├── Dockerfile
├── requirements.txt
└── requirements-dev.txt
```

## 개발 시작하기

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp whitelist.example.yaml whitelist.yaml   # 로컬 테스트용 값으로 채우기
ruff check .
pytest -q
```

> AI(Claude 등)를 포함한 개발 과정에서 실제 대상 사이트 접속·로그인·CAPTCHA 우회는 수행하지 않습니다.
> 개발/테스트는 공개 페이지 또는 로컬 fixture(`tests/fixtures/`)로 진행합니다(CLAUDE.md §3-8).
