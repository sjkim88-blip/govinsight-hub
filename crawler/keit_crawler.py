# -*- coding: utf-8 -*-
"""KEIT 한국산업기술기획평가원(산업부) 공고 크롤러.

KEIT의 산업부 R&D 공고는 범부처 시스템 IRIS 로 함께 공시된다.
독립 사이트(keit.re.kr)는 JS/SROME 기반이라 직접 스크래핑이 불안정하므로,
IRIS 목록 API에서 전문기관 = 한국산업기술기획평가원 인 공고만 분리 수집한다.
공고별 상세 딥링크 URL 은 IRIS 상세 페이지로 연결된다.
"""
try:
    from common import auto_tags  # noqa: F401  (build_notice 내부에서 사용)
    import iris_crawler as iris
except ImportError:
    from crawler import iris_crawler as iris

BASE_TAGS = [
    {"text": "#KEIT", "type": "agency"},
    {"text": "#산자부", "type": "ministry"},
]


def run():
    results = []
    for x in iris.fetch_current_cached():
        if iris.KEIT_AGENCY not in (x.get("sorgnNm") or ""):
            continue
        if not iris.is_allowed_ministry(x.get("blngGovdSeNm")):
            continue  # 부처 화이트리스트 외 제외
        results.append(iris.build_notice(x, "KEIT", BASE_TAGS))
    return results


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
