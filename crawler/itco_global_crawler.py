# -*- coding: utf-8 -*-
"""IT회사 동향(해외) 크롤러.

글로벌 빅테크/반도체/AI 기업(엔비디아·구글·마이크로소프트·알리바바·마이크론 등)
관련 기사를 IT/경제 뉴스 RSS 피드에서 찾아낸다. 특정 기업으로 제한하지
않고 common.GLOBAL_TECH_KEYWORDS 매칭 여부로 판단한다.
기존 news_crawler.py 가 쓰던 전자신문·AI타임스 RSS를 재사용한다.

axis="IT회사 동향", region="global", src=피드명, id 접두사: "itcog_"
"""
import hashlib

try:
    from common import fetch_rss, auto_tags, match_global_tech
except ImportError:
    from crawler.common import fetch_rss, auto_tags, match_global_tech

RSS_SOURCES = [
    {"key": "전자신문", "url": "https://rss.etnews.com/Section901.xml", "tag": "#전자신문"},
    {"key": "AI타임스", "url": "https://www.aitimes.com/rss/allArticle.xml", "tag": "#AI타임스"},
]

MAX_ITEMS = 30


def _stable_id(key, link_or_title):
    h = hashlib.md5(link_or_title.encode("utf-8", errors="replace")).hexdigest()[:10]
    return f"itcog_{key}_{h}"


def run():
    """글로벌 빅테크 관련 IT회사 동향 기사를 표준 dict 리스트로 반환."""
    results = []
    for src in RSS_SOURCES:
        try:
            items = fetch_rss(src["url"], limit=MAX_ITEMS)
        except Exception as e:
            print(f"  ⚠ IT회사동향(해외:{src['key']}) 실패: {e}")
            continue
        for it in items:
            title = it["title"]
            company = match_global_tech(title)
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
                "region": "global",
                "company": company,
                "url": it["link"] or "",
                "tags": auto_tags(title, [{"text": src["tag"], "type": "agency"}]),
            })
    return results


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
