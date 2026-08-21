# -*- coding: utf-8 -*-
"""스마트공장닷컴(smart-factory.kr) 사업공고 크롤러.

smart-factory.kr 은 React SPA 이므로 HTML 파싱 대신 내부 JSON API 를 직접 호출한다.
API: POST /usr/bg/ba/ma/bsnsPbanc/selectBsnsPbancPage.do
     body: {"key":"list", "rcptStts":"", "ordrSe":"REG", "currentPage": N}
"""
import re

try:
    from common import post, auto_tags
except ImportError:
    from crawler.common import post, auto_tags

BASE = "https://www.smart-factory.kr"
API_URL = BASE + "/usr/bg/ba/ma/bsnsPbanc/selectBsnsPbancPage.do"
LIST_URL = BASE + "/usr/bg/ba/ma/bsnsPbanc"
DETAIL_BASE = BASE + "/usr/bg/ba/ma/bsnsPbancDtl"

BASE_TAGS = [
    {"text": "#중기부", "type": "ministry"},
    {"text": "#TIPA", "type": "agency"},
]

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
MAX_PAGES = 5  # 최대 50건 (페이지당 10건)


def _deadline(period_text):
    """'2026-06-18 00:00 ~ 2026-07-14 23:50' → '2026-07-14'. 없으면 ''."""
    dates = DATE_RE.findall(period_text or "")
    return dates[-1] if len(dates) >= 2 else (dates[0] if dates else "")


def _period(period_text):
    """'2026-06-18 00:00 ~ 2026-07-14 23:50' → '2026-06-18 ~ 2026-07-14'. 없으면 ''."""
    dates = DATE_RE.findall(period_text or "")
    if len(dates) >= 2:
        return f"{dates[0]} ~ {dates[1]}"
    return dates[0] if dates else ""


def _item_id(pbancId, pbancSn):
    safe = re.sub(r"[^A-Za-z0-9]", "_", str(pbancId))
    return f"sf_{safe}_{pbancSn}"


def _detail_url(pbancId, pbancSn):
    return f"{DETAIL_BASE}?pbancId={pbancId}&pbancSn={pbancSn}"


def _fetch_page(page):
    headers = {
        "Content-Type": "application/json",
        "Referer": LIST_URL,
    }
    r = post(API_URL, json={"key": "list", "rcptStts": "", "ordrSe": "REG", "currentPage": page},
             headers=headers, timeout=20)
    r.raise_for_status()
    data = r.json()
    model = data.get("modelAndView", {}).get("model", {})
    pbanc_list = model.get("pbancList") or []
    pagination = data.get("paginationInfo", {})
    total_pages = int(pagination.get("totalPageCount", 1))
    return pbanc_list, total_pages


def run():
    notices = []
    seen_ids = set()

    for page in range(1, MAX_PAGES + 1):
        items, total_pages = _fetch_page(page)
        for item in items:
            pbanc_id = item.get("pbancId", "")
            pbanc_sn = item.get("pbancSn", 0)
            nid = _item_id(pbanc_id, pbanc_sn)
            if nid in seen_ids:
                continue
            seen_ids.add(nid)

            name = item.get("dtlPbancNm", "").strip()
            if not name:
                continue

            rcpt_raw = item.get("rcptYmdDa2001", "")
            deadline = _deadline(rcpt_raw)
            period = _period(rcpt_raw)
            url = _detail_url(pbanc_id, pbanc_sn)

            try:
                tags = auto_tags(name, BASE_TAGS)
            except Exception:
                tags = []

            notices.append({
                "id": nid,
                "axis": "지원사업",
                "name": name,
                "sub": item.get("bizClsfYrNm", ""),
                "perProject": "확인 필요",
                "totalBudget": "-",
                "ministry": "중소벤처기업부",
                "agency": "중소기업기술정보진흥원",
                "deadline": deadline,
                "period": period,
                "src": "스마트공장닷컴",
                "url": url,
                "tags": tags,
            })

        if page >= total_pages:
            break

    return notices


if __name__ == "__main__":
    import json
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    result = run()
    print(f"수집: {len(result)}건")
    print(json.dumps(result[:3], ensure_ascii=False, indent=2))
