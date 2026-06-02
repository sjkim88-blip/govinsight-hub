# -*- coding: utf-8 -*-
"""뉴스·보도자료 크롤러.

수집 대상:
  1) 산업부·과기부·중기부 보도자료 목록 페이지 (HTML 스크래핑)
  2) 전자신문·디지털타임스 RSS 피드 (XML 파싱)

반환 형식: axis="지원사업", src="뉴스", id="news_..."
금액은 제목에서 extract_amount() 로 파싱해 perProject 에 저장한다.
"""
import re
import hashlib
import xml.etree.ElementTree as ET
from email.utils import parsedate

try:
    from common import get, auto_tags, is_allowed_ministry, extract_amount
except ImportError:
    from crawler.common import get, auto_tags, is_allowed_ministry, extract_amount

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
        "ministry": "산업통상자원부",
        "m_tag": {"text": "#산업부", "type": "ministry"},
    },
    {
        "key": "msit",
        "urls": [
            "https://www.msit.go.kr/bbs/list.do?sCode=user&mPid=238&mId=239",
            "https://www.msit.go.kr/bbs/list.do?sCode=user&mId=239",
        ],
        "ministry": "과학기술정보통신부",
        "m_tag": {"text": "#과기부", "type": "ministry"},
    },
    {
        "key": "mss",
        "urls": [
            "https://www.mss.go.kr/site/smba/ex/bbs/List.do?cbIdx=86",
        ],
        "ministry": "중소벤처기업부",
        "m_tag": {"text": "#중기부", "type": "ministry"},
    },
]

# ── RSS 소스 ───────────────────────────────────────────────────────────────
RSS_SOURCES = [
    {
        "key": "etnews",
        "urls": [
            "https://www.etnews.com/rss/rss.xml",
            "http://www.etnews.com/rss/rss.xml",
        ],
        "ministry": "뉴스",
        "m_tag": {"text": "#전자신문", "type": "ministry"},
    },
    {
        "key": "dt",
        "urls": [
            "https://www.dt.co.kr/rss/rss.xml",
            "http://www.dt.co.kr/rss/rss.xml",
            "https://www.dt.co.kr/rss/it.xml",
        ],
        "ministry": "뉴스",
        "m_tag": {"text": "#디지털타임스", "type": "ministry"},
    },
]

# 보도자료 관련 공고 키워드 — 이 단어가 없으면 제외 (노이즈 감소)
RELEVANCE_KEYWORDS = (
    "R&D", "연구개발", "기술개발", "지원", "공고", "모집", "선정",
    "사업", "과제", "투자", "예산", "억", "조", "펀드",
    "AI", "인공지능", "스마트", "디지털", "제조", "산업",
    "컨소시엄", "협력", "실증", "보급",
)

DATE_RE = re.compile(r'\d{4}[-./]\d{1,2}[-./]\d{1,2}')


def _stable_id(key, url_or_title):
    h = hashlib.md5(url_or_title.encode("utf-8", errors="replace")).hexdigest()[:10]
    return f"news_{key}_{h}"


def _parse_rfc2822(date_str):
    """RFC 2822 pubDate → 'YYYY-MM-DD'. 실패 시 ''."""
    try:
        t = parsedate(date_str)
        if t:
            return f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d}"
    except Exception:
        pass
    m = DATE_RE.search(date_str or "")
    return m.group(0).replace(".", "-").replace("/", "-") if m else ""


def _is_relevant(title):
    return any(kw in title for kw in RELEVANCE_KEYWORDS)


def _make_notice(key, title, url, ministry, m_tag, deadline=""):
    amount = extract_amount(title)
    per_project = f"{amount:.0f}억" if amount else "확인 필요"
    return {
        "id": _stable_id(key, url or title),
        "axis": "지원사업",
        "name": title,
        "sub": "",
        "perProject": per_project,
        "totalBudget": "-",
        "ministry": ministry,
        "agency": key.upper(),
        "deadline": deadline,
        "src": "뉴스",
        "url": url or "",
        "tags": auto_tags(title, [m_tag]),
    }


# ── RSS 파싱 ───────────────────────────────────────────────────────────────
def _fetch_rss(src):
    last_err = None
    for url in src.get("urls", [src.get("url", "")]):
        try:
            r = get(url, timeout=20)
            r.raise_for_status()
            content = r.content
            # XML 선언 인코딩 충돌 방지 (UTF-8 강제)
            if b"<?xml" in content[:200]:
                import re as _re
                content = _re.sub(rb"encoding=['\"][^'\"]+['\"]", b'encoding="utf-8"', content, count=1)
            root = ET.fromstring(content)
            items = []
            for item in root.findall(".//item"):
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub = (item.findtext("pubDate") or "").strip()
                if not title or not _is_relevant(title):
                    continue
                items.append(_make_notice(
                    src["key"], title, link,
                    src["ministry"], src["m_tag"],
                    deadline=_parse_rfc2822(pub),
                ))
                if len(items) >= 20:
                    break
            return items
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"RSS 파싱 실패 {src['key']}: {last_err}")


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

    # 공통 정부 사이트 패턴: 테이블 혹은 리스트 내 a 태그
    candidates = []

    # 방법1: 본문 영역 내 a 태그 (href 에 view/detail/seq 포함)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(" ", strip=True)
        if len(text) < 10:
            continue
        if not any(k in href for k in ("view", "View", "seq", "idx", "bbsId", "nttId", "articleId")):
            continue
        candidates.append((text, href))

    # 방법2: tbody tr a (테이블 목록)
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
        items.append(_make_notice(src["key"], title, full_url, src["ministry"], src["m_tag"]))
        if len(items) >= 15:
            break

    return items


# ── 진입점 ─────────────────────────────────────────────────────────────────
def run():
    """보도자료·RSS 뉴스를 표준 dict 리스트로 반환."""
    results = []

    for src in PRESS_SOURCES:
        try:
            results.extend(_fetch_press(src))
        except Exception as e:
            print(f"  ⚠ 보도자료({src['key']}) 실패: {e}")

    for src in RSS_SOURCES:
        try:
            results.extend(_fetch_rss(src))
        except Exception as e:
            print(f"  ⚠ RSS({src['key']}) 실패: {e}")

    return results


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
