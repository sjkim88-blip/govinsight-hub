# -*- coding: utf-8 -*-
"""IT회사 동향(국내) 크롤러.

기존 버전은 전자신문/AI타임스 RSS 피드에서 "제목에 추적기업명이 우연히
들어간 기사"만 골라 썼는데, 실제로는 거의 0건이 나왔다(대기업 SI 계열사는
일반 IT 뉴스에 회사명이 잘 노출되지 않음). 이번 버전은 각 추적 기업의
공식 홈페이지 뉴스룸/보도자료 페이지를 회사별로 직접 파싱한다.

common.DOMESTIC_IT_COMPANIES(현재 11개사) 를 그대로 기준으로 삼는다(이
파일에서는 수정하지 않음). 회사마다 사이트 구조가 전부 달라 회사별 개별
파서 함수(_fetch_<회사>)를 둔다. 아래는 회사별 구현 방식 요약(실제 fetch로
200 + 콘텐츠까지 확인 후 반영):

  - 삼성SDS: /kr/news/index.html 최신뉴스 위젯(서버렌더, 3~4건)
  - LG CNS: PR센터(/pr/news)가 완전 CSR(React)라 서버 응답에 기사 데이터가
    전혀 없어 스킵(SKIPPED_COMPANIES 참고)
  - 현대오토에버: /kor/about/pr/news/list.do 자체는 빈 셸이고 실제 목록은
    boardController.js 가 호출하는 list.ajax(POST) 에서 옴
  - SK C&C: 사명이 SK AX 로 변경됨(skax.co.kr). 뉴스룸 페이지가 대부분
    클라이언트 렌더링이라 서버 응답에는 최상단 슬라이드(최신 기사) 1건만
    포함됨 — 그 1건만 수집
  - 포스코DX: /kor/pr/newsRoom.do 서버렌더 리스트
  - 한화시스템: /kr/prcenter/news.do 서버렌더 리스트. 상세는 JS onclick
    fnView(idx) 로 열리는 POST 폼이지만 동일 idx 로 GET newsView.do 도 통함
  - 롯데정보통신: PR센터가 Next.js CSR 앱이고 실제 데이터는 인증이 필요한
    내부 API(/api/ko/company-news/press, 401 Unauthorized)에서 오므로 스킵
  - CJ올리브네트웍스: /news/press_release 서버렌더 리스트
  - 두산디지털이노베이션: /kr/promotion/news 서버렌더 리스트(doosandigitalinnovation.com)
  - KT DS: /company/pr_news.jsp 서버렌더 테이블. 상세는 JS onclick
    goView_2(idx, 'pr_news_view.jsp') 로 열리지만 동일 idx 로 GET
    pr_news_view.jsp?idx= 도 통함
  - 코오롱베니트: /pr-center/communityid/news/list.do 서버렌더 리스트.
    상세(view.do)는 POST 전용(GET 405)이라 링크는 목록 페이지로 대체

axis="IT회사 동향", region="domestic", src=회사명, id 접두사: "itcod_"
"""
import hashlib
import re
from datetime import datetime
from urllib.parse import urljoin

try:
    from common import get, post, auto_tags, DOMESTIC_IT_COMPANIES
except ImportError:
    from crawler.common import get, post, auto_tags, DOMESTIC_IT_COMPANIES

from bs4 import BeautifulSoup

MAX_AGE_DAYS = 60          # 최근 1~2개월
MAX_ITEMS_PER_COMPANY = 20  # 날짜 파싱 실패 시 근사 기준(최신순 목록 상위 N건)

_DATE_RE = re.compile(r"(20\d\d)[.\-](\d{1,2})[.\-](\d{1,2})")


def _norm_date(text):
    """'2026.09.03' 등 다양한 표기 → 'YYYY-MM-DD'. 실패 시 ''."""
    m = _DATE_RE.search(text or "")
    if not m:
        return ""
    y, mo, da = m.groups()
    return f"{y}-{int(mo):02d}-{int(da):02d}"


def _within_days(pub_date, days=MAX_AGE_DAYS):
    """pubDate 가 days 일 이내인지. 빈값/파싱실패면 True(상위 N건 근사로 포함)."""
    if not pub_date:
        return True
    try:
        d = datetime.strptime(pub_date, "%Y-%m-%d")
    except ValueError:
        return True
    return (datetime.now() - d).days <= days


def _company_key(company):
    return re.sub(r"[^0-9A-Za-z가-힣]", "", company)


def _stable_id(company, link_or_title):
    h = hashlib.md5((link_or_title or "").encode("utf-8", errors="replace")).hexdigest()[:10]
    return f"itcod_{_company_key(company)}_{h}"


# ── 회사별 파서 ──────────────────────────────────────────────────────────
# 각 함수는 [{"title":..., "url":..., "pubDate":"YYYY-MM-DD" 또는 ""}, ...] 반환.

def _fetch_samsungsds():
    url = "https://www.samsungsds.com/kr/news/index.html"
    r = get(url, timeout=20)
    r.raise_for_status()
    # 이 사이트는 응답 헤더에 charset 을 안 보내 requests 가 기본값(ISO-8859-1)으로
    # 오판독한다. r.content(바이트)를 넘겨 BeautifulSoup 이 자체 인코딩 감지를 하게 한다.
    soup = BeautifulSoup(r.content, "html.parser")
    items, seen = [], set()
    for sl in soup.select("div.navigationSlide_wrap"):
        a = sl.select_one("a.navigationSlide_readMore[href]")
        title_el = sl.select_one(".navigationSlide_title")
        date_el = sl.select_one(".navigationSlide_date")
        if not a or not title_el:
            continue
        href = a["href"]
        if not href or href == "#":
            continue
        link = urljoin(url, href)
        if link in seen:
            continue
        seen.add(link)
        items.append({
            "title": title_el.get_text(strip=True),
            "url": link,
            "pubDate": _norm_date(date_el.get_text(strip=True) if date_el else ""),
        })
    return items


def _fetch_hyundaiautoever():
    # 목록 페이지 자체는 빈 셸이고, boardController.js 가 호출하는
    # list.ajax(POST) 응답 HTML 조각에 실제 기사 목록이 담겨 있다.
    ajax_url = "https://www.hyundai-autoever.com/kor/about/pr/news/list.ajax"
    r = post(ajax_url, data={"pageIndex": "1", "q": "", "f": "1", "yearQ": "", "monthQ": ""}, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    for a in soup.select("a.list[href]"):
        title_el = a.select_one(".title")
        date_el = a.select_one(".date")
        if not title_el:
            continue
        link = urljoin("https://www.hyundai-autoever.com/kor/about/pr/news/", a["href"])
        items.append({
            "title": title_el.get_text(strip=True),
            "url": link,
            "pubDate": _norm_date(date_el.get_text(strip=True) if date_el else ""),
        })
    return items


def _fetch_poscodx():
    url = "https://www.poscodx.com/kor/pr/newsRoom.do"
    r = get(url, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    for li in soup.select("li.item"):
        a = li.select_one("strong.tit a[href]")
        date_el = li.select_one("span.date")
        if not a:
            continue
        items.append({
            "title": a.get_text(strip=True),
            "url": urljoin(url, a["href"]),
            "pubDate": _norm_date(date_el.get_text(strip=True) if date_el else ""),
        })
    return items


def _fetch_hanwhasystems():
    url = "https://www.hanwhasystems.com/kr/prcenter/news.do"
    r = get(url, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    for li in soup.select("div.board-img1 ul li"):
        a = li.select_one("a[onclick]")
        strong = li.select_one("strong")
        date_el = li.select_one("span.date")
        if not a or not strong:
            continue
        m = re.search(r"fnView\('(\d+)'\)", a.get("onclick", ""))
        if not m:
            continue
        items.append({
            "title": strong.get_text(strip=True),
            "url": f"https://www.hanwhasystems.com/kr/prcenter/newsView.do?bbidx={m.group(1)}",
            "pubDate": _norm_date(date_el.get_text(strip=True) if date_el else ""),
        })
    return items


def _fetch_kolonbenit():
    # 상세(view.do)가 POST 전용(GET 405)이라 기사 링크는 목록 페이지로 대체한다.
    url = "https://www.kolonbenit.com/pr-center/communityid/news/list.do"
    r = get(url, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    for a in soup.select("div.boardType1 a[class^='artcl']"):
        title_el = a.select_one("p.type2")
        date_el = a.select_one("span.type4")
        if not title_el:
            continue
        items.append({
            "title": title_el.get_text(strip=True),
            "url": url,
            "pubDate": _norm_date(date_el.get_text(strip=True) if date_el else ""),
        })
    return items


def _fetch_cjolivenetworks():
    url = "https://www.cjolivenetworks.co.kr/news/press_release"
    r = get(url, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    for li in soup.select("li.items"):
        a = li.select_one("a.desc_box[href]")
        title_el = li.select_one("p.ui_title")
        date_el = li.select_one("p.date")
        if not a or not title_el:
            continue
        items.append({
            "title": title_el.get_text(strip=True),
            "url": urljoin(url, a["href"]),
            "pubDate": _norm_date(date_el.get_text(strip=True) if date_el else ""),
        })
    return items


def _fetch_doosan_di():
    url = "https://www.doosandigitalinnovation.com/kr/promotion/news"
    r = get(url, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    for dl in soup.select("dl.context-box"):
        a = dl.select_one("dt a[href]")
        date_el = dl.select_one("p.date")
        if not a:
            continue
        items.append({
            "title": a.get_text(strip=True),
            "url": urljoin(url, a["href"]),
            "pubDate": _norm_date(date_el.get_text(strip=True) if date_el else ""),
        })
    return items


def _fetch_ktds():
    url = "https://www.ktds.com/company/pr_news.jsp"
    r = get(url, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    for a in soup.select("td.emp.alignL a[onclick]"):
        m = re.search(r"goView_2\('(\d+)'", a.get("onclick", ""))
        if not m:
            continue
        title = a.get_text(strip=True)
        if not title:
            continue
        tr = a.find_parent("tr")
        tds = tr.find_all("td") if tr else []
        date_text = tds[-1].get_text(strip=True) if tds else ""
        items.append({
            "title": title,
            "url": f"https://www.ktds.com/company/pr_news_view.jsp?idx={m.group(1)}",
            "pubDate": _norm_date(date_text),
        })
    return items


def _fetch_skcc():
    # 사명이 'SK AX'로 변경됨(skax.co.kr). 뉴스룸 목록은 대부분 클라이언트
    # 렌더링이라 서버 응답에는 최상단 슬라이드(최신 기사) 1건만 포함된다.
    url = "https://www.skax.co.kr/company/news-rooms"
    r = get(url, timeout=20)
    r.raise_for_status()
    text = r.text
    m_href = re.search(r'href="(/company/news-room/[^"]+)"', text)
    m_title = re.search(r'capitalize md:text-xl">([^<]+)</span>', text)
    m_date = re.search(r'text-base font-normal text-\[#555\]">(20\d\d\.\d\d\.\d\d)</span>', text)
    if not m_href or not m_title:
        return []
    return [{
        "title": m_title.group(1).strip(),
        "url": urljoin(url, m_href.group(1)),
        "pubDate": _norm_date(m_date.group(1)) if m_date else "",
    }]


COMPANY_FETCHERS = {
    "삼성SDS": _fetch_samsungsds,
    "현대오토에버": _fetch_hyundaiautoever,
    "SK C&C": _fetch_skcc,
    "포스코DX": _fetch_poscodx,
    "한화시스템": _fetch_hanwhasystems,
    "CJ올리브네트웍스": _fetch_cjolivenetworks,
    "두산디지털이노베이션": _fetch_doosan_di,
    "KT DS": _fetch_ktds,
    "코오롱베니트": _fetch_kolonbenit,
}

# 회사 공식 뉴스룸이 완전 클라이언트 렌더링(CSR)이거나 데이터 API 에 인증이
# 걸려 있어 이번 버전에서는 서버사이드로 수집할 수 없는 회사와 그 사유.
SKIPPED_COMPANIES = {
    "LG CNS": (
        "PR센터(lgcns.com/pr/news)가 완전 CSR(React) 렌더링. 서버 응답 HTML에 "
        "기사 제목/날짜/JSON 데이터가 전혀 없음(__NEXT_DATA__ 등도 미발견)"
    ),
    "롯데정보통신": (
        "PR센터(ldcc.co.kr/prcenter/press/list)가 Next.js CSR 앱이라 서버 HTML엔 "
        "i18n 문자열뿐이고, 실제 데이터는 내부 API(/api/ko/company-news/press)에서 "
        "가져오는데 이 API가 401 Unauthorized 반환(인증 토큰 필요). 참고로 사명도 "
        "'롯데이노베이트'로 변경됨"
    ),
}


def run():
    """common.DOMESTIC_IT_COMPANIES 각 회사의 공식 뉴스룸에서 최근 기사를 표준 dict 리스트로 반환."""
    results = []

    for company, reason in SKIPPED_COMPANIES.items():
        print(f"  ⚠ IT회사동향(국내:{company}) 건너뜀: {reason}")

    for company in DOMESTIC_IT_COMPANIES:
        fetcher = COMPANY_FETCHERS.get(company)
        if not fetcher:
            if company not in SKIPPED_COMPANIES:
                print(f"  ⚠ IT회사동향(국내:{company}) 건너뜀: 뉴스룸 URL/파서 미구현")
            continue
        try:
            items = fetcher()
        except Exception as e:
            print(f"  ⚠ IT회사동향(국내:{company}) 실패: {e}")
            continue

        count = 0
        for it in items[:MAX_ITEMS_PER_COMPANY]:
            title = (it.get("title") or "").strip()
            link = it.get("url") or ""
            pub_date = it.get("pubDate") or ""
            if not title:
                continue
            if not _within_days(pub_date):
                continue
            # 코오롱베니트처럼 상세 링크가 없어 모든 기사가 같은 목록 URL을 쓰는
            # 경우도 있으므로, id 해시는 link 만이 아니라 title 도 함께 반영한다.
            results.append({
                "id": _stable_id(company, f"{link}|{title}"),
                "axis": "IT회사 동향",
                "name": title,
                "sub": "",
                "perProject": "",
                "totalBudget": "-",
                "ministry": "",
                "agency": company,
                "deadline": "",
                "pubDate": pub_date,
                "src": company,
                "region": "domestic",
                "company": company,
                "url": link,
                "tags": auto_tags(title, [{"text": "#" + company, "type": "agency"}]),
            })
            count += 1
        print(f"  ✓ IT회사동향(국내:{company}) {count}건")

    return results


if __name__ == "__main__":
    import json
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(run(), ensure_ascii=False, indent=2))
