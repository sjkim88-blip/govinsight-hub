# -*- coding: utf-8 -*-
"""산업통상자원부(산자부) 직접 공고 크롤러.

산자부 공식 홈페이지(motir.go.kr) 사업공고 게시판을 스크래핑한다.
IRIS/KEIT/KIAT 를 경유하지 않는 산자부 직접 공고를 수집한다.
"""
import re
from bs4 import BeautifulSoup

try:
    from common import get, auto_tags
except ImportError:
    from crawler.common import get, auto_tags

BASE = "https://www.motir.go.kr"
LIST_URL = BASE + "/kor/article/ATCL2826a2625"

BASE_TAGS = [{"text": "#산자부", "type": "ministry"}]
MAX_PAGES = 3  # 최신 3페이지(약 30건)만 수집

DATE_RE = re.compile(r'(\d{4})[.\-/]\s*(\d{1,2})[.\-/]\s*(\d{1,2})')


def _normalize_date(text):
    m = DATE_RE.search(text or "")
    if not m:
        return ""
    y, mo, d = m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)
    return f"{y}-{mo}-{d}"


def _fetch_list(page=1):
    r = get(LIST_URL, params={"pageIndex": str(page)}, timeout=20)
    r.raise_for_status()
    r.encoding = "utf-8"
    soup = BeautifulSoup(r.text, "html.parser")

    items = []
    for row in soup.select("table tbody tr"):
        tds = row.select("td")
        if len(tds) < 4:
            continue
        link = row.select_one("a")
        if not link:
            continue

        # href="javascript:article.view('71122')" 또는 onclick 에서 ID 추출
        id_src = (link.get("href") or "") + " " + (link.get("onclick") or "")
        m = re.search(r"article\.view\(['\"]?(\d+)['\"]?\)", id_src)
        if not m:
            continue

        article_id = m.group(1)
        name = link.get_text(" ", strip=True)
        if not name:
            continue

        cols = [td.get_text(" ", strip=True) for td in tds]
        # 컬럼 순서: 공고번호, 제목, 담당부서, 등록일, 조회수, 첨부
        dept = cols[2] if len(cols) > 2 else ""
        reg_date = _normalize_date(cols[3]) if len(cols) > 3 else ""

        items.append({
            "id": article_id,
            "name": name,
            "dept": dept,
            "reg_date": reg_date,
            "url": f"{LIST_URL}/{article_id}/view",
        })

    return items


def run():
    results = []
    seen = set()

    for page in range(1, MAX_PAGES + 1):
        try:
            items = _fetch_list(page)
            if not items:
                break
        except Exception as e:
            print(f"  ⚠ 산자부 직접공고 페이지 {page} 실패: {e}")
            break

        for item in items:
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            results.append({
                "id": f"motir_{item['id']}",
                "axis": "지원사업",
                "name": item["name"],
                "sub": item["dept"],
                "perProject": "확인 필요",
                "totalBudget": "-",
                "ministry": "산업통상자원부",
                "agency": "",
                "deadline": item["reg_date"],
                "src": "산자부",
                "url": item["url"],
                "tags": auto_tags(item["name"], list(BASE_TAGS)),
            })

    return results


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
