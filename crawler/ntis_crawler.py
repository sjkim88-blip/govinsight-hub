# -*- coding: utf-8 -*-
"""NTIS 진행과제 크롤러 — 컨소시엄 파트너 탐색용.

NTIS(국가과학기술지식정보서비스) 전체과제 검색에서 진행중인 R&D 과제를
수집한다. 주요 활용: 수요기업/참여기관으로 진입 가능한 과제 탐색.

axis: "지원사업", src: "NTIS", id 접두사: "ntis_"
"""
try:
    from common import post, get, auto_tags, is_allowed_ministry
except ImportError:
    from crawler.common import post, get, auto_tags, is_allowed_ministry

from bs4 import BeautifulSoup

LIST_URL = "https://www.ntis.go.kr/outcomes/popup/srchTotlPrjt.do"
BASE_TAGS = [{"text": "#NTIS", "type": "ministry"}]
MAX_ITEMS = 40

# 화이트리스트 부처·기관 키워드 (NTIS 부처명 정규화)
_NTIS_ALLOW = ("산업", "과기", "과학기술", "중기", "중소", "조달")


def _allowed(ministry_text):
    if not ministry_text:
        return False
    return is_allowed_ministry(ministry_text) or any(k in ministry_text for k in _NTIS_ALLOW)


def _parse_html(html):
    soup = BeautifulSoup(html, "html.parser")
    results = []

    # 공통 패턴1: table tbody tr
    for tr in soup.select("table tbody tr"):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue
        a = tr.find("a", href=True)
        name = (a.get_text(" ", strip=True) if a else tds[1].get_text(" ", strip=True))
        if not name or len(name) < 5:
            continue
        href = a["href"] if a else ""
        url = href if href.startswith("http") else (LIST_URL + href if href else LIST_URL)

        ministry = tds[-2].get_text(strip=True) if len(tds) >= 2 else ""
        agency = tds[-1].get_text(strip=True) if len(tds) >= 1 else ""

        if not _allowed(ministry or agency):
            continue

        cols = [td.get_text(" ", strip=True) for td in tds]
        # 기간 정보 탐색
        deadline = ""
        for col in cols:
            if "~" in col and len(col) > 15:
                parts = col.split("~")
                if len(parts) == 2:
                    deadline = parts[-1].strip()[:10]
                break

        results.append({
            "id": f"ntis_{len(results):04d}",
            "axis": "지원사업",
            "name": name,
            "sub": "",
            "perProject": "확인 필요",
            "totalBudget": "-",
            "ministry": ministry or "NTIS",
            "agency": agency or "NTIS",
            "deadline": deadline,
            "src": "NTIS",
            "url": url,
            "tags": auto_tags(name, BASE_TAGS),
        })
        if len(results) >= MAX_ITEMS:
            break

    return results


def run():
    """NTIS 진행과제를 표준 dict 리스트로 반환. 실패 시 빈 리스트."""
    try:
        r = post(LIST_URL, data={
            "pageIndex": "1",
            "recordCountPerPage": str(MAX_ITEMS),
            "searchKeyword": "",
        }, timeout=25)
        r.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"NTIS 요청 실패: {e}")

    # JSON 응답 시도
    try:
        j = r.json()
        items = j.get("list") or j.get("items") or j.get("data") or []
        if items:
            results = []
            for it in items:
                name = (it.get("prjtNm") or it.get("projectName") or
                        it.get("name") or "")
                if not name:
                    continue
                ministry = it.get("govMinistry") or it.get("ministry") or "NTIS"
                agency = it.get("prjtInstitution") or it.get("agency") or "NTIS"
                if not _allowed(ministry or agency):
                    continue
                results.append({
                    "id": f"ntis_{it.get('prjtId', len(results)):04}",
                    "axis": "지원사업",
                    "name": name,
                    "sub": it.get("prjtSubNm") or "",
                    "perProject": "확인 필요",
                    "totalBudget": "-",
                    "ministry": ministry,
                    "agency": agency,
                    "deadline": (it.get("endDate") or it.get("prjtEndYy") or ""),
                    "src": "NTIS",
                    "url": it.get("url") or LIST_URL,
                    "tags": auto_tags(name, BASE_TAGS),
                })
                if len(results) >= MAX_ITEMS:
                    break
            if results:
                return results
    except (ValueError, AttributeError):
        pass

    # HTML 응답 파싱
    return _parse_html(r.text)


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
