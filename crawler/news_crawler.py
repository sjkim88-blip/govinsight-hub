# -*- coding: utf-8 -*-
"""정부부처 보도자료 크롤러 — IT회사 동향 원천 중 하나.

수집 대상: 산업부·과기부·중기부 보도자료 목록 페이지 (HTML 스크래핑)

메인 IA 개편(정부지원사업/IT회사 동향/산업별 뉴스 3탭)에 따라 axis 를
고정하지 않는다. 보도자료 제목에 IT회사 동향 추적 기업(common.py 의
DOMESTIC_IT_COMPANIES/GLOBAL_TECH_KEYWORDS)이 언급된 건만 "IT회사 동향"
으로 채택하고, 그 외(정책 공지 등 일반 보도자료)는 채택하지 않는다.
"산업별 뉴스" 탭은 한경(hankyung.com) 전용이라(hankyung_industry_crawler.py)
여기서는 그쪽으로 보내지 않는다.

반환 형식: axis="IT회사 동향", src="뉴스", id="news_..."
"""
import hashlib

try:
    from common import get, auto_tags, match_domestic_company, match_global_tech
except ImportError:
    from crawler.common import get, auto_tags, match_domestic_company, match_global_tech

from bs4 import BeautifulSoup

# ── 보도자료 소스 ──────────────────────────────────────────────────────────
PRESS_SOURCES = [
    {
        "key": "motie",
        # 산업부 보도자료 목록 (게시판 목록 URL 후보 순서대로 시도)
        "urls": [
            "https://www.motie.go.kr/motie/ne/presse/press2/bbs/bbsView.do",
            "https://www.motie.go.kr/kor/article/LIST415/31/view",
            "https://www.motie.go.kr/motie/ne/presse/press2/bbs/bbsList.do?bbs_cd_n=81",
        ],
        "m_tag": {"text": "#산자부", "type": "ministry"},
    },
    {
        "key": "msit",
        "urls": [
            "https://www.msit.go.kr/bbs/list.do?sCode=user&mPid=238&mId=239",
            "https://www.msit.go.kr/bbs/list.do?sCode=user&mId=239",
        ],
        "m_tag": {"text": "#과기부", "type": "ministry"},
    },
    {
        "key": "mss",
        "urls": [
            "https://www.mss.go.kr/site/smba/ex/bbs/List.do?cbIdx=86",
        ],
        "m_tag": {"text": "#중기부", "type": "ministry"},
    },
]

# 노이즈 감소용 최소 관련성 키워드 (하나도 없으면 제외)
RELEVANCE_KEYWORDS = (
    "R&D", "연구개발", "기술개발", "지원", "공고", "모집", "선정",
    "사업", "과제", "투자", "예산", "억", "조", "펀드",
    "AI", "인공지능", "스마트", "디지털", "제조", "산업",
    "컨소시엄", "협력", "실증", "보급",
)


def _stable_id(key, url_or_title):
    h = hashlib.md5(url_or_title.encode("utf-8", errors="replace")).hexdigest()[:10]
    return f"news_{key}_{h}"


def _is_relevant(title):
    return any(kw in title for kw in RELEVANCE_KEYWORDS)


def _to_notice(key, title, url, m_tag):
    """보도자료 → IT회사 동향 표준 dict. 추적기업 미매칭이면 None."""
    company = match_domestic_company(title)
    region = "domestic"
    if not company:
        company = match_global_tech(title)
        region = "global" if company else None
    if not company:
        return None
    return {
        "id": _stable_id(key, url or title),
        "axis": "IT회사 동향",
        "name": title,
        "sub": "",
        "perProject": "",
        "totalBudget": "-",
        "ministry": "",
        "agency": key.upper(),
        "deadline": "",
        "src": "뉴스",
        "region": region,
        "company": company,
        "url": url or "",
        "tags": auto_tags(title, [m_tag]),
    }


# ── 보도자료 HTML 스크래핑 ──────────────────────────────────────────────────
def _fetch_press(src):
    last_err = None
    r = None
    for url in src.get("urls", [src.get("url", "")]):
        try:
            r = get(url, timeout=20)
            r.raise_for_status()
            break
        except Exception as e:
            last_err = e
            r = None
            continue
    if r is None:
        raise RuntimeError(f"보도자료 요청 실패 {src['key']}: {last_err}")

    soup = BeautifulSoup(r.text, "html.parser")
    items = []

    candidates = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(" ", strip=True)
        if len(text) < 10:
            continue
        if not any(k in href for k in ("view", "View", "seq", "idx", "bbsId", "nttId", "articleId")):
            continue
        candidates.append((text, href))

    if not candidates:
        for tr in soup.select("table tbody tr"):
            a = tr.find("a", href=True)
            if not a:
                continue
            text = a.get_text(" ", strip=True)
            href = a["href"]
            if len(text) < 10:
                continue
            candidates.append((text, href))

    seen = set()
    for title, href in candidates:
        if title in seen or not _is_relevant(title):
            continue
        seen.add(title)
        base_url = src["urls"][0] if "urls" in src else src.get("url", "")
        full_url = href if href.startswith("http") else base_url.split("/bbs/")[0] + href
        notice = _to_notice(src["key"], title, full_url, src["m_tag"])
        if notice:
            items.append(notice)
        if len(items) >= 15:
            break

    return items


# ── 진입점 ─────────────────────────────────────────────────────────────────
def run():
    """정부부처 보도자료 중 IT회사 동향 추적기업이 언급된 건만 표준 dict 리스트로 반환."""
    results = []
    for src in PRESS_SOURCES:
        try:
            results.extend(_fetch_press(src))
        except Exception as e:
            print(f"  ⚠ 보도자료({src['key']}) 실패: {e}")
    return results


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
