# -*- coding: utf-8 -*-
"""KEIT 통합관리시스템(srome.keit.re.kr) 사업공고·수요조사 크롤러.

SROME은 KEIT 산업기술R&D 통합관리시스템. 공개 게시판에서
사업공고와 수요조사 항목을 수집한다.
"""
import re
import hashlib

try:
    from common import get, post, auto_tags
except ImportError:
    from crawler.common import get, post, auto_tags

from bs4 import BeautifulSoup

BASE = "https://srome.keit.re.kr"
INDEX_URL = BASE + "/srome/sromeIndex.do"

# 공고 목록 API 후보 (Spring MVC .do 패턴)
LIST_CANDIDATES = [
    BASE + "/srome/pub/pbanc/retrievePbancListView.do",
    BASE + "/srome/biz/pbanc/retrievePbancListView.do",
    BASE + "/srome/biz/pbanc/bsnsPbanc/retrieveBsnsPbancListView.do",
    BASE + "/srome/pub/retrieveNoticeListView.do",
]

# 수요조사 목록 API 후보
DMND_CANDIDATES = [
    BASE + "/srome/pub/dmnd/retrieveDmndListView.do",
    BASE + "/srome/biz/dmnd/retrieveDmndListView.do",
]

BASE_TAGS = [
    {"text": "#산자부", "type": "ministry"},
    {"text": "#KEIT", "type": "agency"},
]
DATE_RE = re.compile(r"(\d{4})[-./]\s*(\d{1,2})[-./]\s*(\d{1,2})")
MAX_ITEMS = 30


def _normalize_date(text):
    m = DATE_RE.search(text or "")
    if not m:
        return ""
    return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"


def _deadline_from_period(text):
    """'2026-07-01 ~ 2026-08-14' 에서 마지막 날짜 추출."""
    dates = DATE_RE.findall(text or "")
    if not dates:
        return ""
    y, mo, d = dates[-1]
    return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"


def _period_str(text):
    """기간 텍스트를 'YYYY-MM-DD ~ YYYY-MM-DD' 정규화."""
    dates = DATE_RE.findall(text or "")
    if len(dates) >= 2:
        s = f"{dates[0][0]}-{dates[0][1].zfill(2)}-{dates[0][2].zfill(2)}"
        e = f"{dates[-1][0]}-{dates[-1][1].zfill(2)}-{dates[-1][2].zfill(2)}"
        return f"{s} ~ {e}"
    if len(dates) == 1:
        return f"{dates[0][0]}-{dates[0][1].zfill(2)}-{dates[0][2].zfill(2)}"
    return ""


def _stable_id(prefix, key):
    h = hashlib.md5(str(key).encode()).hexdigest()[:8]
    return f"keitsrome_{prefix}_{h}"


def _parse_table(soup, is_demand=False):
    """공통 테이블 파싱 — thead/tbody 기반."""
    items = []
    seen = set()

    for table in soup.find_all("table"):
        for row in table.select("tr"):
            cells = row.select("td")
            if len(cells) < 2:
                continue

            link = row.select_one("a[href], a[onclick]")
            if not link:
                continue

            title = link.get_text(" ", strip=True)
            if not title or len(title) < 5:
                continue
            if title in seen:
                continue
            seen.add(title)

            href = link.get("href") or ""
            onclick = link.get("onclick") or ""
            url_raw = href if href.startswith("http") else (BASE + href if href.startswith("/") else "")

            # onclick에서 파라미터 추출
            m_id = re.search(r"['\"](\d{5,})['\"]", onclick + href)
            key = m_id.group(1) if m_id else title

            cols = [c.get_text(" ", strip=True) for c in cells]
            period_text = next((c for c in cols if "~" in c or DATE_RE.search(c)), "")
            deadline = _deadline_from_period(period_text)
            period = _period_str(period_text)

            is_dmnd = is_demand or "수요조사" in title
            src = "수요조사" if is_dmnd else "KEIT통합"
            prefix = "dmnd" if is_dmnd else "pbanc"

            items.append({
                "id": _stable_id(prefix, key),
                "axis": "지원사업",
                "name": title,
                "sub": "",
                "perProject": "확인 필요",
                "totalBudget": "-",
                "ministry": "산업통상자원부",
                "agency": "한국산업기술기획평가원",
                "deadline": deadline,
                "period": period,
                "src": src,
                "url": url_raw or INDEX_URL,
                "tags": auto_tags(title, list(BASE_TAGS)),
            })
            if len(items) >= MAX_ITEMS:
                break
        if len(items) >= MAX_ITEMS:
            break

    return items


def _try_fetch(url, params=None):
    """GET 시도 후 HTML soup 반환. 실패 시 None."""
    try:
        r = get(url, params=params, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        # 빈 페이지 또는 로그인 페이지 체크
        if soup.find("table") or soup.find("ul", class_=re.compile(r"list|board", re.I)):
            return soup
    except Exception:
        pass
    return None


def _try_post(url, data=None):
    """POST 시도 후 HTML soup 반환. 실패 시 None."""
    try:
        r = post(url, data=data or {"pageIndex": "1", "pageUnit": "20"}, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        if soup.find("table"):
            return soup
    except Exception:
        pass
    return None


def _fetch_from_index():
    """메인 인덱스 페이지 파싱으로 공개 링크 수집."""
    try:
        soup = _try_fetch(INDEX_URL)
        if not soup:
            return []
        return _parse_table(soup)
    except Exception:
        return []


def run():
    """KEIT SROME 공고를 표준 dict 리스트로 반환. 수집 실패 시 빈 리스트."""
    results = []
    seen_ids = set()

    # 공고 목록 시도
    for url in LIST_CANDIDATES:
        soup = _try_fetch(url, params={"pageIndex": "1", "pageUnit": "20"})
        if not soup:
            soup = _try_post(url)
        if soup:
            for item in _parse_table(soup, is_demand=False):
                if item["id"] not in seen_ids:
                    seen_ids.add(item["id"])
                    results.append(item)
            if results:
                break

    # 수요조사 시도
    for url in DMND_CANDIDATES:
        soup = _try_fetch(url, params={"pageIndex": "1", "pageUnit": "20"})
        if not soup:
            soup = _try_post(url)
        if soup:
            for item in _parse_table(soup, is_demand=True):
                if item["id"] not in seen_ids:
                    seen_ids.add(item["id"])
                    results.append(item)
            break

    # 모든 후보 실패 시 인덱스 페이지 폴백
    if not results:
        results = _fetch_from_index()

    if results:
        print(f"  · KEIT SROME: {len(results)}건 수집")
    else:
        print("  · KEIT SROME: 수집 0건 (공개 게시판 미확인)")

    return results


if __name__ == "__main__":
    import json
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    result = run()
    print(f"수집: {len(result)}건")
    print(json.dumps(result[:3], ensure_ascii=False, indent=2))
