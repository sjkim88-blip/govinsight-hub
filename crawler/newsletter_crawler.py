# -*- coding: utf-8 -*-
"""기관 간행물·뉴스레터 크롤러.

정책/예산 규모 파악용. 수집 대상:
  - KEIT 이슈픽 (srome.keit.re.kr): 산업기술 분야별 월간 동향 브리프

사내 프록시 환경에서 접근 가능한 소스만 포함.
axis="지원사업", src="뉴스레터"
"""
import sys
import hashlib
import re

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from common import get, auto_tags, extract_amount
except ImportError:
    from crawler.common import get, auto_tags, extract_amount

from bs4 import BeautifulSoup

LIST_URL = "https://srome.keit.re.kr/srome/biz/info/keitPub/retrieveKeitIssuListView.do"
DETAIL_URL = "https://srome.keit.re.kr/srome/biz/info/keitPub/retrieveKeitIssuInfoView.do"

BASE_TAG = {"text": "#KEIT이슈픽", "type": "agency"}
DATE_RE = re.compile(r'\d{4}[-./]\d{1,2}[-./]\d{1,2}')
BLLTS_RE = re.compile(r"f_detail\('(\d+)'\)")
MAX_ITEMS = 12


def _stable_id(bllts_seq):
    return f"newsletter_keit_{bllts_seq}"


def _parse_date(text):
    m = DATE_RE.search(text or "")
    return m.group(0).replace(".", "-").replace("/", "-") if m else ""


def _fetch_keit():
    r = get(LIST_URL, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    seen = set()

    for a in soup.find_all("a", href=True):
        title = a.get_text(" ", strip=True)
        href = a["href"]
        if len(title) < 10 or title in seen:
            continue
        m = BLLTS_RE.search(href)
        if not m:
            continue
        bllts_seq = m.group(1)
        seen.add(title)
        amount = extract_amount(title)
        items.append({
            "id": _stable_id(bllts_seq),
            "axis": "지원사업",
            "name": title,
            "sub": "",
            "perProject": f"{amount:.0f}억" if amount else "확인 필요",
            "totalBudget": "-",
            "ministry": "뉴스레터",
            "agency": "KEIT",
            "deadline": "",
            "src": "뉴스레터",
            "url": f"{DETAIL_URL}?blltSeq={bllts_seq}",
            "tags": auto_tags(title, [BASE_TAG]),
        })
        if len(items) >= MAX_ITEMS:
            break
    return items


def run():
    """기관 간행물/뉴스레터를 표준 dict 리스트로 반환."""
    try:
        return _fetch_keit()
    except Exception as e:
        print(f"  ⚠ 뉴스레터(KEIT) 실패: {e}")
        return []


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
