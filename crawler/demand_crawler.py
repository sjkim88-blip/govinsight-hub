# -*- coding: utf-8 -*-
"""수요조사 공고 크롤러.

수집 대상:
  1) IRIS 캐시(진행중/예정)에서 제목에 "수요조사" 포함 항목
  2) 기업마당(bizinfo) "수요조사" 키워드 검색 결과

axis="지원사업", src="수요조사", id 접두사: "demand_iris_" / "demand_biz_"
"""
import re

try:
    from common import get, auto_tags, is_allowed_ministry
    import iris_crawler as iris
except ImportError:
    from crawler.common import get, auto_tags, is_allowed_ministry
    from crawler import iris_crawler as iris

from bs4 import BeautifulSoup

DEMAND_KEYWORDS = ("수요조사", "수요 조사", "수요발굴")
BASE_TAGS = [{"text": "#수요조사", "type": "biztype"}]

BIZINFO_LIST_URL = "https://www.bizinfo.go.kr/web/lay1/bbs/S1T122C128/AS/74/list.do"
BIZINFO_BASE = "https://www.bizinfo.go.kr"
PBLANC_RE = re.compile(r"pblancId=([A-Za-z0-9_]+)", re.I)
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _deadline(text):
    dates = DATE_RE.findall(text or "")
    return dates[-1] if dates else ""


def _from_iris_cached():
    """IRIS 진행중/예정 캐시에서 수요조사 키워드 항목 추출 (API 추가 호출 없음)."""
    results = []
    seen = set()
    for x in iris.fetch_current_cached():
        name = x.get("bsnsAncmTl") or x.get("ancmTl") or ""
        if not any(kw in name for kw in DEMAND_KEYWORDS):
            continue
        if not is_allowed_ministry(x.get("blngGovdSeNm")):
            continue
        key = (x.get("ancmId"), x.get("bsnsAncmSn"))
        if key in seen:
            continue
        seen.add(key)
        agency = x.get("sorgnNm") or ""
        _, src_tags = iris.src_profile(agency)
        notice = iris.build_notice(x, "수요조사", BASE_TAGS + src_tags)
        notice["id"] = "demand_iris_" + x.get("ancmId", "") + "_" + str(x.get("bsnsAncmSn", ""))
        notice["src"] = "수요조사"
        results.append(notice)
    return results


def _from_bizinfo():
    """기업마당에서 수요조사 공고 스크래핑."""
    results = []
    try:
        res = get(BIZINFO_LIST_URL, timeout=20)
        res.raise_for_status()
        res.encoding = "utf-8"
        soup = BeautifulSoup(res.text, "html.parser")

        for i, row in enumerate(soup.select("table tbody tr"), 1):
            tds = row.select("td")
            cols = [c.get_text(" ", strip=True) for c in tds]
            if len(cols) < 4:
                continue
            link = row.select_one("a")
            if not link:
                continue
            name = link.get_text(" ", strip=True)
            if not name:
                continue
            # 실제 수요조사 공고만 추출 (bizinfo 검색 필터가 부정확할 수 있으므로 재확인)
            if not any(kw in name for kw in DEMAND_KEYWORDS):
                continue
            href = link.get("href") or ""
            url = href if href.startswith("http") else BIZINFO_BASE + href
            period = next((c for c in cols if "~" in c or DATE_RE.search(c)), "")
            deadline = _deadline(period)
            sogwan = cols[4] if len(cols) > 4 else ""
            suhaeng = cols[5] if len(cols) > 5 else ""
            pblanc_m = PBLANC_RE.search(href)
            pid = pblanc_m.group(1).lower() if pblanc_m else f"{i:04d}"
            results.append({
                "id": f"demand_biz_{pid}",
                "axis": "지원사업",
                "name": name,
                "sub": sogwan,
                "perProject": "확인 필요",
                "totalBudget": "-",
                "ministry": "중기부",
                "agency": suhaeng or "중소벤처기업진흥공단",
                "deadline": deadline,
                "src": "수요조사",
                "url": url or BIZINFO_LIST_URL,
                "tags": auto_tags(name, BASE_TAGS),
            })
    except Exception as e:
        print(f"  ⚠ bizinfo 수요조사 실패: {e}")
    return results


def run():
    """수요조사 공고를 표준 dict 리스트로 반환."""
    results = _from_iris_cached()

    biz = _from_bizinfo()
    existing = {r["id"] for r in results}
    for item in biz:
        if item["id"] not in existing:
            results.append(item)
    return results


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
