# -*- coding: utf-8 -*-
"""IRIS 사전공고 크롤러.

사전공고(계획공고)는 본공고와 동일한 IRIS 인프라를 사용하지만
rcveStt 상태값이 다르거나, 별도 엔드포인트(retrieveAnnouncementList.do)로
제공된다. 두 가지 경로를 순서대로 시도하고 첫 성공 결과를 반환한다.

axis: "지원사업", src: "IRIS사전공고", id 접두사: "irispre_"
"""
try:
    from common import post, auto_tags, is_allowed_ministry
    import iris_crawler as iris
except ImportError:
    from crawler.common import post, auto_tags, is_allowed_ministry
    from crawler import iris_crawler as iris

BASE = "https://www.iris.go.kr"
PRE_LIST_API = BASE + "/contents/retrieveAnnouncementList.do"

# IRIS 사전공고 상태값 후보 (실제 코드는 시스템마다 다를 수 있음)
PRE_STATUSES = {"사전공고", "계획공고", "계획", "준비", "공고예정"}

BASE_TAGS = [{"text": "#IRIS사전공고", "type": "ministry"}]
MAX_ITEMS = 60
MAX_SCAN = 30


# ── 전용 엔드포인트 시도 ────────────────────────────────────────────────────
def _fetch_dedicated_page(page_index):
    r = post(PRE_LIST_API, data={"pageIndex": str(page_index)}, timeout=20)
    r.raise_for_status()
    j = r.json()
    return (
        j.get("listBsnsAncm")
        or j.get("listAncm")
        or j.get("list")
        or []
    )


def _try_dedicated():
    """전용 사전공고 API 호출. 빈 결과면 [] 반환."""
    results = []
    try:
        page1 = _fetch_dedicated_page(1)
        if not page1:
            return []
        # 첫 페이지가 비어 있지 않으면 진짜 API라고 가정
        for x in page1:
            if not is_allowed_ministry(x.get("blngGovdSeNm")):
                continue
            agency = x.get("sorgnNm") or ""
            src, base_tags = iris.src_profile(agency)
            notice = iris.build_notice(x, "IRIS사전공고", BASE_TAGS)
            notice["id"] = "irispre_" + notice["id"].split("_", 1)[-1]
            notice["src"] = "IRIS사전공고"
            results.append(notice)
            if len(results) >= MAX_ITEMS:
                break
    except Exception:
        pass
    return results


# ── 메인 IRIS API 스캔으로 사전공고 상태 항목 추출 ─────────────────────────
def _try_main_api_scan():
    """기존 IRIS 목록 API를 더 넓게 스캔해 사전공고 상태 항목 추출."""
    results = []
    try:
        last = iris._find_last_page()
        for page in range(last, max(1, last - MAX_SCAN), -1):
            for x in iris._fetch_page(page):
                if x.get("rcveStt") not in PRE_STATUSES:
                    continue
                if not is_allowed_ministry(x.get("blngGovdSeNm")):
                    continue
                if iris.KEIT_AGENCY in (x.get("sorgnNm") or "") or \
                   iris.IITP_AGENCY in (x.get("sorgnNm") or ""):
                    continue
                notice = iris.build_notice(x, "IRIS사전공고", BASE_TAGS)
                notice["id"] = "irispre_" + notice["id"].split("_", 1)[-1]
                notice["src"] = "IRIS사전공고"
                results.append(notice)
                if len(results) >= MAX_ITEMS:
                    return results
    except Exception:
        pass
    return results


def run():
    """IRIS 사전공고를 표준 dict 리스트로 반환."""
    results = _try_dedicated()
    if not results:
        results = _try_main_api_scan()
    return results


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
