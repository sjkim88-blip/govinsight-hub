# -*- coding: utf-8 -*-
"""한경(hankyung.com) 산업 섹션 크롤러 — "산업별 뉴스" 탭 전용 소스.

한경 산업면 중 아래 4개 섹션만 수집한다(유통·F&B·중소중견·경영재계 등은 제외):
  반도체·전자(1064) / 모빌리티(1065) / 중공업(1067) / 에너지·화학(1214)

한경엔 "AI·로봇" 전용 섹션이 없어(로봇 기사가 중공업/반도체·전자에 섞여
나옴) 섹션 라벨을 그대로 쓰지 않고, 기사 제목에 common.classify_news_domain()
을 적용해 AI·로봇/반도체·전자/모빌리티·자동차/철강·소재·에너지 중 하나로
재분류한다(매칭 안 되면 원 섹션의 기본 도메인으로 폴백).

IT회사 동향(국내 11개사/글로벌 빅테크) 이 걸리는 기사는 우선순위 최상위로
그쪽 axis 로 보내고, "산업별 뉴스" 에서는 제외한다.

axis: "산업별 뉴스" 또는 "IT회사 동향", src="한경"
"""
import re

try:
    from common import (
        get, auto_tags, classify_news_domain,
        match_domestic_company, match_global_tech,
    )
except ImportError:
    from crawler.common import (
        get, auto_tags, classify_news_domain,
        match_domestic_company, match_global_tech,
    )

from bs4 import BeautifulSoup

BASE = "https://www.hankyung.com"

# (섹션ID, 섹션이 매칭 실패 시 폴백으로 쓸 기본 도메인)
SECTIONS = [
    ("1064", "반도체·전자"),      # 반도체·전자
    ("1065", "모빌리티·자동차"),   # 모빌리티
    ("1067", "철강·소재·에너지"),      # 중공업(조선·방산 등)
    ("1214", "철강·소재·에너지"),      # 에너지·화학
]

MAX_PAGES = 2       # 섹션당 최대 2페이지(약 50건)
MAX_PER_SECTION = 40
DATE_RE = re.compile(r"(\d{4})\.(\d{2})\.(\d{2})")
ID_RE = re.compile(r"/article/(\d+)")


def _pub_date(text):
    m = DATE_RE.search(text or "")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def _fetch_section(section_id, page):
    url = f"{BASE}/industry/{section_id}"
    r = get(url, params={"page": str(page)} if page > 1 else None, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    for li in soup.select("ul.news-list li"):
        a = li.select_one("h2.news-tit a[href]")
        if not a:
            continue
        title = a.get_text(" ", strip=True)
        href = a["href"]
        if not title or not href:
            continue
        date_el = li.select_one("p.txt-date")
        pub_date = _pub_date(date_el.get_text(strip=True) if date_el else "")
        items.append({"title": title, "url": href, "pubDate": pub_date})
    return items


def _to_notice(item, default_domain):
    title = item["title"]
    m = ID_RE.search(item["url"])
    art_id = m.group(1) if m else str(abs(hash(item["url"] or title)))[:10]

    company = match_domestic_company(title)
    region = "domestic"
    if not company:
        company = match_global_tech(title)
        region = "global" if company else None

    base = {
        "id": f"hk_{art_id}",
        "name": title,
        "sub": "",
        "perProject": "",
        "totalBudget": "-",
        "ministry": "",
        "agency": "한경",
        "deadline": "",
        "pubDate": item["pubDate"],
        "src": "한경",
        "url": item["url"],
        "tags": auto_tags(title, [{"text": "#한경", "type": "agency"}]),
    }

    if company:
        # IT회사 동향 추적기업 매칭이 최우선 — 산업별 뉴스에서 제외하고 그쪽으로 보낸다.
        base.update({"axis": "IT회사 동향", "region": region, "company": company})
        return base

    domain = classify_news_domain(title, default=default_domain)
    base.update({"axis": "산업별 뉴스", "category": domain})
    return base


def run():
    """한경 산업 4개 섹션 기사를 표준 dict 리스트(산업별 뉴스 + IT회사 동향)로 반환."""
    results = []
    seen_ids = set()

    for section_id, default_domain in SECTIONS:
        count = 0
        for page in range(1, MAX_PAGES + 1):
            try:
                items = _fetch_section(section_id, page)
            except Exception as e:
                print(f"  ⚠ 한경({section_id}) 페이지{page} 실패: {e}")
                break
            if not items:
                break
            for it in items:
                notice = _to_notice(it, default_domain)
                if notice["id"] in seen_ids:
                    continue
                seen_ids.add(notice["id"])
                results.append(notice)
                count += 1
                if count >= MAX_PER_SECTION:
                    break
            if count >= MAX_PER_SECTION:
                break

    return results


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
