# -*- coding: utf-8 -*-
"""IT회사 동향(국내) 크롤러.

대기업 그룹 캡티브마켓을 보유한 SI/IT서비스 계열사 12개(VNTG 경쟁사)의
동향을 IT/경제 뉴스 RSS 피드에서 찾아낸다. 전자신문·AI타임스 RSS를
일반 뉴스 소스로 재사용하되(기존 news_crawler.py 가 쓰던 소스), 이 탭
용도로는 제목에 추적 기업명이 등장하는 기사만 골라 쓴다.

axis="IT회사 동향", region="domestic", src=피드명, id 접두사: "itcod_"
"""
import hashlib

try:
    from common import fetch_rss, auto_tags, match_domestic_company
except ImportError:
    from crawler.common import fetch_rss, auto_tags, match_domestic_company

RSS_SOURCES = [
    {"key": "전자신문", "url": "https://rss.etnews.com/Section901.xml", "tag": "#전자신문"},
    {"key": "AI타임스", "url": "https://www.aitimes.com/rss/allArticle.xml", "tag": "#AI타임스"},
]

MAX_ITEMS = 30


def _stable_id(key, link_or_title):
    h = hashlib.md5(link_or_title.encode("utf-8", errors="replace")).hexdigest()[:10]
    return f"itcod_{key}_{h}"


def run():
    """추적 기업이 언급된 국내 IT회사 동향 기사를 표준 dict 리스트로 반환."""
    results = []
    for src in RSS_SOURCES:
        try:
            items = fetch_rss(src["url"], limit=MAX_ITEMS)
        except Exception as e:
            print(f"  ⚠ IT회사동향(국내:{src['key']}) 실패: {e}")
            continue
        for it in items:
            title = it["title"]
            company = match_domestic_company(title)
            if not company:
                continue
            results.append({
                "id": _stable_id(src["key"], it["link"] or title),
                "axis": "IT회사 동향",
                "name": title,
                "sub": "",
                "perProject": "",
                "totalBudget": "-",
                "ministry": "",
                "agency": src["key"],
                "deadline": "",
                "pubDate": it["pubDate"],
                "src": src["key"],
                "region": "domestic",
                "company": company,
                "url": it["link"] or "",
                "tags": auto_tags(title, [{"text": src["tag"], "type": "agency"}]),
            })
    return results


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
