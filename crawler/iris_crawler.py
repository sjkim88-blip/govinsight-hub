# -*- coding: utf-8 -*-
"""IRIS 범부처통합연구지원시스템 R&D 공고 크롤러.

IRIS는 SPA이며 목록을 JSON API(retrieveBsnsAncmList.do)로 제공한다.
기본 정렬이 오래된 순이라, 마지막 페이지(=최신)를 이진탐색으로 찾은 뒤
뒤에서부터 '진행중/예정' 공고를 수집한다. 각 공고는 식별자(ancmId 등)로
상세 페이지 딥링크 URL을 생성한다 → 출처 클릭 시 해당 공고로 바로 이동.

IRIS는 범부처 통합 시스템이라 KEIT(산업부)·IITP(과기부) 전문기관 공고도
함께 들어온다. 그 두 기관 공고는 keit_crawler/iitp_crawler 가 가져가도록
이 모듈의 run() 에서는 제외한다(중복 방지).
"""
from urllib.parse import urlencode

try:
    from common import post, auto_tags, is_allowed_ministry
except ImportError:
    from crawler.common import post, auto_tags, is_allowed_ministry

BASE = "https://www.iris.go.kr"
LIST_API = BASE + "/contents/retrieveBsnsAncmList.do"
VIEW_URL = BASE + "/contents/retrieveBsnsAncmView.do"

# 전문기관명 식별자 (sorgnNm 부분일치)
KEIT_AGENCY = "산업기술기획평가원"   # 한국산업기술기획평가원
IITP_AGENCY = "정보통신기획평가원"   # 정보통신기획평가원

# 전문기관(sorgnNm 부분일치) → 출처 코드 매핑.
# KEIT·IITP 는 전용 크롤러가 담당하므로 여기서 제외하고, 나머지 범부처 공고를
# 무조건 'IRIS' 로 뭉뚱그리지 않고 실제 전문기관별 출처로 라벨링한다.
# 매칭 안 되는 기타 기관은 'IRIS' 로 남긴다.
SRC_BY_AGENCY = [
    ("산업기술진흥원", "KIAT"),        # 한국산업기술진흥원 (소부장·지역산업·국제협력)
    ("연구재단", "NRF"),              # 한국연구재단 (기초연구)
    ("중소기업기술정보진흥원", "TIPA"),  # 중기부 R&D 전문기관
    ("과학기술기획평가원", "KISTEP"),   # 한국과학기술기획평가원
    ("에너지기술평가원", "KETEP"),      # 한국에너지기술평가원
    ("정보통신산업진흥원", "NIPA"),     # 정보통신산업진흥원
    ("테크노파크", "TP"),             # 지역 테크노파크
]


def src_profile(agency):
    """전문기관명 → (출처 코드, 기본 태그 리스트). 미매칭 시 IRIS."""
    agency = agency or ""
    for key, code in SRC_BY_AGENCY:
        if key in agency:
            return code, [{"text": f"#{code}", "type": "agency"}]
    return "IRIS", [{"text": "#IRIS", "type": "agency"}]

# 부처명 → 부처 태그 매핑
MINISTRY_TAG = [
    ("산업통상", "#산자부"), ("산업부", "#산자부"),
    ("과학기술", "#과기부"), ("과기", "#과기부"),
    ("중소벤처", "#중기부"), ("중기", "#중기부"),
]

MAX_SCAN_PAGES = 25   # 마지막 페이지부터 거슬러 스캔할 최대 페이지 수
MAX_ITEMS = 80        # 수집 상한

_FETCH_CACHE = None   # 단일 update.py 실행 내 IRIS API 삼중 호출 방지(iris/keit/iitp 공용)


def _fetch_page(page_index):
    r = post(LIST_API, data={"pageIndex": str(page_index)}, timeout=20)
    r.raise_for_status()
    return r.json().get("listBsnsAncm", []) or []


def _find_last_page():
    """비어 있지 않은 마지막 페이지(=최신 공고) 번호를 이진탐색으로 찾는다."""
    lo, hi = 1, 64
    while _fetch_page(hi) and hi < 20000:
        lo, hi = hi, hi * 2
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if _fetch_page(mid):
            lo = mid
        else:
            hi = mid
    return lo


def fetch_current(scan_pages=MAX_SCAN_PAGES):
    """현재 '진행중/예정' 공고 원본 레코드를 최신순으로 반환(중복 제거)."""
    last = _find_last_page()
    recs, seen = [], set()
    for page in range(last, max(1, last - scan_pages), -1):
        for x in _fetch_page(page):
            if x.get("rcveStt") not in ("진행중", "예정"):
                continue
            key = (x.get("ancmId"), x.get("bsnsYy"), x.get("bsnsAncmSn"))
            if key in seen:
                continue
            seen.add(key)
            recs.append(x)
    return recs


def _ministry_tag(name, govd):
    src = (name or "") + " " + (govd or "")
    for key, tag in MINISTRY_TAG:
        if key in src:
            return [{"text": tag, "type": "ministry"}]
    return []


def detail_params(x):
    """IRIS 상세 페이지로 이동하기 위한 POST 파라미터.

    IRIS 상세는 GET 쿼리스트링을 읽지 않고 POST 본문으로만 조회된다.
    따라서 대시보드 '출처' 버튼은 이 값들을 hidden form 으로 POST 제출한다.
    """
    return {
        "ancmId": str(x.get("ancmId", "")),
        "bsnsYy": str(x.get("bsnsYy", "")),
        "sorgnBsnsCd": str(x.get("sorgnBsnsCd", "")),
        "bsnsAncmSn": str(x.get("bsnsAncmSn", "")),
        "ancmTurn": str(x.get("ancmTurn", "")),
        "hirkSorgnBsnsCd": str(x.get("hirkSorgnBsnsCd", "")),
        "sorgnId": str(x.get("sorgnId", "")),
    }


def detail_url(x):
    """참고용 GET URL(파라미터 포함). 실제 이동은 post 파라미터로 수행."""
    return VIEW_URL + "?" + urlencode(detail_params(x))


def build_notice(x, src, base_tags):
    """IRIS 원본 레코드 → 대시보드 표준 공고 dict."""
    name = x.get("bsnsAncmTl") or x.get("ancmTl") or "(제목없음)"
    govd = x.get("blngGovdSeNm") or "범부처"
    deadline = (x.get("rcveEndDt") or "").replace("/", "-")
    tags = auto_tags(name, list(base_tags) + _ministry_tag(name, govd))
    return {
        "id": f"{src.lower()}_{x.get('ancmId')}_{x.get('bsnsAncmSn')}",
        "axis": "지원사업",
        "name": name,
        "sub": x.get("sorgnBsnsNm") or "",
        "perProject": "확인 필요",
        "totalBudget": "-",
        "ministry": govd,
        "agency": x.get("sorgnNm") or "",
        "deadline": deadline,
        "src": src,
        "url": VIEW_URL,            # POST 액션 엔드포인트
        "post": detail_params(x),   # 출처 클릭 시 POST 본문 → 실제 공고 페이지
        "tags": tags,
    }


def fetch_current_cached(scan_pages=MAX_SCAN_PAGES):
    """fetch_current() 결과를 모듈 수준에서 캐싱.

    update.py 가 iris/keit/iitp 크롤러를 순서대로 실행할 때 IRIS API를 3회
    호출하는 것을 방지한다. 프로세스 재시작 시 캐시는 자동 초기화된다.
    """
    global _FETCH_CACHE
    if _FETCH_CACHE is None:
        _FETCH_CACHE = fetch_current(scan_pages)
    return _FETCH_CACHE


def run():
    """범부처 공고(KEIT·IITP 전문기관 제외)를 표준 dict 리스트로 반환.

    소관부처 화이트리스트(산업부/과기부/중기부/조달청 등)에 해당하는 공고만 저장.
    """
    results = []
    for x in fetch_current_cached():
        agency = x.get("sorgnNm") or ""
        if KEIT_AGENCY in agency or IITP_AGENCY in agency:
            continue  # KEIT/IITP 전용 크롤러가 담당
        if not is_allowed_ministry(x.get("blngGovdSeNm")):
            continue  # 화이트리스트 외 부처 제외
        src, base_tags = src_profile(agency)
        results.append(build_notice(x, src, base_tags))
        if len(results) >= MAX_ITEMS:
            break
    return results


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
