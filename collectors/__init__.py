"""Collector 7종. investigate.py 가 이 순서대로 고정 호출한다 (CLAUDE.md §1 동작 흐름 4).

① availability  ② structure  ③ stats  ④ content_sample
⑤ cross_reference  ⑥ access_probe  ⑦ user_activity

각 모듈은 `run(page, source) -> dict` 하나를 노출한다. 반환값 규격은 CLAUDE.md §5 참고.
"""
