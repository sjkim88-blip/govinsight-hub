# -*- coding: utf-8 -*-
"""IITP 정보통신기획평가원(과기부) ICT R&D 공고 크롤러.

IITP의 과기부 ICT R&D 공고는 범부처 시스템 IRIS 로 함께 공시된다.
독립 사이트(iitp.kr)는 목록을 AJAX로 로드해 직접 스크래핑이 어려우므로,
IRIS 목록 API에서 전문기관 = 정보통신기획평가원 인 공고만 분리 수집한다.
공고별 상세 딥링크 URL 은 IRIS 상세 페이지로 연결된다.
"""
try:
    import iris_crawler as iris
except ImportError:
    from crawler import iris_crawler as iris

BASE_TAGS = [
    {"text": "#IITP", "type": "agency"},
    {"text": "#과기부", "type": "ministry"},
]


def run():
    results = []
    for x in iris.fetch_current_cached():
        if iris.IITP_AGENCY not in (x.get("sorgnNm") or ""):
            continue
        if not iris.is_allowed_ministry(x.get("blngGovdSeNm")):
            continue  # 부처 화이트리스트 외 제외
        results.append(iris.build_notice(x, "IITP", BASE_TAGS))
    return results


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
