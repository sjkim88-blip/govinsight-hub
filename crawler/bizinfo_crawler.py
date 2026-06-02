# -*- coding: utf-8 -*-
"""기업마당(중기부) 정부지원사업 공고 크롤러.

목록 페이지(list.do)는 서버사이드 HTML 테이블을 제공한다.
컬럼: 번호 | 분야 | 사업명(상세링크) | 신청기간 | 소관기관 | 사업수행기관 | 등록일 | 조회수
신청기간의 종료일을 마감일로, 사업명 링크(pblancId)를 상세 딥링크 URL로 사용한다.
"""
import re

try:
    from common import get, auto_tags, is_allowed_ministry
except ImportError:
    from crawler.common import get, auto_tags, is_allowed_ministry
from bs4 import BeautifulSoup

BASE = "https://www.bizinfo.go.kr"
LIST_URL = BASE + "/web/lay1/bbs/S1T122C128/AS/74/list.do"  # 지원사업 공고
BASE_TAGS = [{"text": "#중기부", "type": "ministry"}]

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
PBLANC_RE = re.compile(r"pblancId=([A-Za-z0-9_]+)")


def _deadline(period_text):
    """'2026-05-29 ~ 2026-06-02' → 종료일 '2026-06-02'. 상시 등은 '' 반환."""
    dates = DATE_RE.findall(period_text or "")
    return dates[-1] if dates else ""


def run():
    notices = []
    res = get(LIST_URL)
    res.raise_for_status()
    res.encoding = "utf-8"
    soup = BeautifulSoup(res.text, "html.parser")

    rows = soup.select("table tbody tr")
    for i, row in enumerate(rows, 1):
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
        href = link.get("href") or ""
        url = href if href.startswith("http") else BASE + href

        period = next((c for c in cols if "~" in c or DATE_RE.search(c)), "")
        deadline = _deadline(period)
        sogwan = cols[4] if len(cols) > 4 else ""
        suhaeng = cols[5] if len(cols) > 5 else ""

        # 기업마당은 중기부 소관 → 화이트리스트 통과(방어적 확인)
        if not is_allowed_ministry("중기부"):
            continue

        # URL 의 pblancId 를 ID 로 사용해 목록 순서 변경에 강인하게 유지
        pblanc_m = PBLANC_RE.search(href)
        pid = pblanc_m.group(1).lower() if pblanc_m else f"bizinfo_{i:03d}"

        notices.append({
            "id": f"bizinfo_{pid}",
            "axis": "지원사업",
            "name": name,
            "sub": sogwan,
            "perProject": "확인 필요",
            "totalBudget": "-",
            "ministry": "중기부",
            "agency": suhaeng or "중소벤처기업진흥공단",
            "deadline": deadline,
            "src": "BIZINFO",
            "url": url or BASE,
            "tags": auto_tags(name, BASE_TAGS),
        })
    return notices


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
