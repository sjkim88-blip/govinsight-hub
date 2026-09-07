# -*- coding: utf-8 -*-
"""크롤러 공통 유틸: HTTP 세션, SSL 프록시 대응, 키워드 기반 자동 태깅."""
import re
import warnings
import requests
import xml.etree.ElementTree as ET
from email.utils import parsedate

# ── 사내 SSL 프록시(MITM 자체서명 CA) 대응 ──────────────────────────────
# 사내망은 Zscaler 등 프록시가 TLS를 가로채며 자체 루트 CA로 재서명한다.
# 이 루트 CA는 보통 Windows 인증서 저장소에 설치돼 있으므로,
# truststore 로 OS 신뢰저장소를 파이썬 ssl 에 주입하면 검증이 통과된다.
_TRUSTSTORE_OK = False
try:
    import truststore
    truststore.inject_into_ssl()
    _TRUSTSTORE_OK = True
except Exception:
    # truststore 미설치/실패 시 get() 에서 verify=False 폴백 사용
    pass

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# 리다이렉트/쿠키 유지를 위한 공용 세션
SESSION = requests.Session()
SESSION.headers.update(HEADERS)
SESSION.trust_env = True  # 환경변수 프록시(HTTP_PROXY 등) 자동 적용

# (키워드 리스트, 태그텍스트, 태그타입)
KEYWORD_RULES = [
    (["산업부"], "#산자부", "ministry"),
    (["과기부"], "#과기부", "ministry"),
    (["중기부"], "#중기부", "ministry"),
    (["NIPA", "정보화진흥원"], "#NIPA", "agency"),
    (["KIAT", "산업기술진흥원"], "#KIAT", "agency"),
    (["KETEP", "에너지기술평가원"], "#KETEP", "agency"),
    (["기술개발"], "#기술개발", "biztype"),
    (["실증"], "#실증", "biztype"),
    (["보급", "확산"], "#보급확산", "biztype"),
    (["컨소시엄"], "#컨소시엄", "biztype"),
    (["AX", "AI전환", "선도모델"], "#AX전환", "biztype"),
    (["상생형", "상생협력", "대중소상생"], "#상생협력", "biztype"),
    (["주관기관모집", "주관기관 모집"], "#주관기관모집", "role"),
    (["TIPA", "기술정보진흥원"], "#TIPA", "agency"),
    (["주관"], "#주관기관", "role"),
    (["참여"], "#참여기관", "role"),
    (["수요기업"], "#수요기업", "role"),
    (["대기업"], "#대기업참여가능", "role"),
    # ── 도메인 (4 카테고리) ────────────────────────────────────────────────
    # 산업별 뉴스 탭의 4개 서브탭과 1:1 대응. classify_news_domain() 도 이 규칙을 재사용한다.
    (["AI", "인공지능", "피지컬AI", "피지컬", "로봇", "협동로봇",
      "스마트공장", "스마트제조", "디지털전환", "DX", "디지털트윈",
      "예지보전", "비전검사", "머신비전", "자율제조", "자율화", "데이터",
      "에듀테크", "EdTech", "edtech", "이러닝", "e-러닝", "이-러닝",
      "스마트교육", "디지털교육", "교육플랫폼", "학습관리시스템", "LMS",
      "교육콘텐츠", "교육소프트웨어", "에드테크", "교육기술", "학습콘텐츠",
      "원격교육", "교육데이터", "AI교육", "AI 교육"], "#AI·로봇", "domain"),
    (["반도체", "디스플레이", "시스템반도체", "웨이퍼", "전자", "가전",
      "파운드리", "팹리스", "OLED"], "#반도체·전자", "domain"),
    (["자동차", "전기차", "수소차", "자율주행", "모빌리티", "EV",
      "배터리", "이차전지"], "#모빌리티·자동차", "domain"),
    (["철강", "금속재료", "금속", "소재", "뿌리기술", "세라믹", "화합물",
      "섬유", "탄소나노", "탄소소재",
      "석유화학", "화학공정", "화학산업", "화학소재", "정유", "탄소중립",
      "탄소", "ESG", "수소", "신재생", "재생에너지", "태양광", "풍력",
      "조선", "방산", "해양", "항공", "공급망", "SCM", "물류",
      "뿌리산업", "도금", "주조", "단조", "용접", "표면처리"], "#철강·소재·에너지", "domain"),
]

# 산업별 뉴스 탭 서브탭 4개(고정 순서). classify_news_domain() 반환값은 항상 이 중 하나.
NEWS_DOMAINS = ["AI·로봇", "반도체·전자", "모빌리티·자동차", "철강·소재·에너지"]
_NEWS_DOMAIN_RULES = [(kws, label.lstrip("#")) for kws, label, typ in KEYWORD_RULES if typ == "domain"]


def classify_news_domain(title, default=None):
    """기사 제목 → 산업별 뉴스 4개 도메인 중 하나(단일값, 첫 매칭 우선).

    한경 산업 섹션은 AI·로봇 전용 섹션이 없어(로봇 기사가 중공업/반도체·전자에
    섞여 나옴) 섹션 라벨 대신 이 키워드 분류기로 재분류한다. 매칭 안 되면
    default(호출부가 넘긴 원 섹션의 기본 도메인)를 반환.
    """
    text = title or ""
    for keywords, label in _NEWS_DOMAIN_RULES:
        if any(kw in text for kw in keywords):
            return label
    return default


# ── 소관부처 화이트리스트 ───────────────────────────────────────────────
# 이 부처들의 공고만 저장한다. 그 외(조달청·국토부·복지부·농진청 등)는 제외.
MINISTRY_WHITELIST = [
    "산업통상자원부",
    "과학기술정보통신부",
    "중소벤처기업부",
]

# 출처별 부처 표기 변형(IRIS '산업통상부', 기업마당 '중기부' 등)까지 허용하는
# 정규화 키워드. 화이트리스트 부처를 포괄하도록 핵심 토큰만 사용한다.
_ALLOW_KEYWORDS = (
    "산업통상", "산업부", "산업",   # 산업부 / 산업통상자원부 / 산업통상부
    "과학기술", "과기",            # 과학기술정보통신부 / 과기부
    "중소벤처", "중기",            # 중소벤처기업부 / 중기부
    "KEIT", "IITP", "KIAT", "NIPA", "KETEP", "KOTECH", "NTIS",  # 전문기관 직접 표기
    "TIPA", "기술정보진흥원",       # 중소기업기술정보진흥원
    "스마트공장",                   # 스마트공장 사업
    "교육부", "교육혁신",           # 에듀테크 관련 교육부
    "뉴스",                        # 뉴스/보도자료 항목
    "수요조사",                     # 수요조사 공고
    "뉴스레터",                     # 기관 간행물
)


def is_allowed_ministry(name):
    """소관부처명이 화이트리스트에 해당하는지(표기 변형 허용) 여부."""
    if not name:
        return False
    return any(kw in name for kw in _ALLOW_KEYWORDS)


# ── 대기업(VNTG) 부적합 공고 키워드 ─────────────────────────────────────
# 소상공인·창업·투자/융자연계·농어업 등 회사 규모·성격에 맞지 않는 공고는
# 수집 단계에서 제외한다(저장하지 않음).
UNFIT_KEYWORDS = (
    "소상공인", "소공인", "자영업", "예비창업", "청년창업", "재창업",
    "초기창업", "창업초기", "창업도약", "1인 창업", "1인창업", "1인기업",
    "마을기업", "사회적기업", "사회적경제", "협동조합", "전통시장", "골목상권",
    "소셜벤처", "여성기업", "장애인기업", "시니어",
    "농업", "농촌", "어업", "어촌", "귀농", "임업", "축산", "수산업",
    "투자연계", "투자형", "융자", "보증", "바우처", "상권", "점포",
)


AMOUNT_RE = re.compile(r'(\d+[\.,]?\d*)\s*(억|조)')


def extract_amount(text):
    """텍스트에서 첫 번째 금액(억 단위 float) 추출. 없으면 None."""
    if not text:
        return None
    m = AMOUNT_RE.search(str(text))
    if not m:
        return None
    val = float(m.group(1).replace(',', ''))
    if m.group(2) == '조':
        val *= 10000
    return val


def classify_size(per_project=None, total=None):
    """규모 분류. 반환: 'large' | 'mid' | 'small'.

    대형: 과제당 20억↑ or 총사업비 500억↑
    중형: 과제당 5억~20억 or 총사업비 100억~500억
    소형/미확인: 그 이하 → 'small'
    """
    pp = extract_amount(str(per_project or ''))
    tb = extract_amount(str(total or ''))
    if (pp is not None and pp >= 20) or (tb is not None and tb >= 500):
        return 'large'
    if (pp is not None and pp >= 5) or (tb is not None and tb >= 100):
        return 'mid'
    return 'small'


def is_company_fit(name, sub=""):
    """대기업 VNTG 에 적합한 공고인지(부적합 키워드 미포함) 여부."""
    text = (name or "") + " " + (sub or "")
    return not any(kw in text for kw in UNFIT_KEYWORDS)


def get(url, **kwargs):
    """공용 세션 GET. SSL 검증 실패 시 verify=False 로 1회 재시도."""
    kwargs.setdefault("timeout", 15)
    try:
        return SESSION.get(url, **kwargs)
    except requests.exceptions.SSLError:
        # truststore 로도 해결 안 되는 환경(루트 CA 미설치 등) 최후 폴백
        warnings.filterwarnings("ignore", message="Unverified HTTPS request")
        kwargs["verify"] = False
        return SESSION.get(url, **kwargs)


def post(url, **kwargs):
    """공용 세션 POST. JSON API 형식 공고 목록 수집용."""
    kwargs.setdefault("timeout", 15)
    try:
        return SESSION.post(url, **kwargs)
    except requests.exceptions.SSLError:
        warnings.filterwarnings("ignore", message="Unverified HTTPS request")
        kwargs["verify"] = False
        return SESSION.post(url, **kwargs)


_RSS_DATE_RE = re.compile(r'\d{4}[-./]\d{1,2}[-./]\d{1,2}')


def parse_rfc2822_date(date_str):
    """RSS pubDate(RFC 2822 등) → 'YYYY-MM-DD'. 실패 시 ''."""
    try:
        t = parsedate(date_str)
        if t:
            return f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d}"
    except Exception:
        pass
    m = _RSS_DATE_RE.search(date_str or "")
    return m.group(0).replace(".", "-").replace("/", "-") if m else ""


def fetch_rss(url, limit=30, timeout=20):
    """RSS 2.0 피드를 [{title, link, pubDate}, ...] 로 파싱. 실패 시 예외 발생."""
    r = get(url, timeout=timeout)
    r.raise_for_status()
    content = r.content
    if b"<?xml" in content[:200]:
        content = re.sub(rb"encoding=['\"][^'\"]+['\"]", b'encoding="utf-8"', content, count=1)
    root = ET.fromstring(content)
    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        if not title:
            continue
        items.append({"title": title, "link": link, "pubDate": parse_rfc2822_date(pub)})
        if len(items) >= limit:
            break
    return items


DOMAIN_RULES = [
    (["AX", "DX", "디지털전환", "AI전환", "보급확산", "선도모델",
      "상생형", "상생협력"], "AX/DX 솔루션 공급"),
    (["스마트공장", "스마트팩토리", "공장고도화", "현장자동화",
      "제조혁신", "설비", "로봇도입"], "스마트공장·제조현장 구축"),
    (["AI", "인공지능", "피지컬AI", "비전검사", "머신비전",
      "예지보전", "자율제조", "자율화", "디지털트윈"], "AI·피지컬AI R&D"),
    (["ERP", "그룹웨어", "RPA", "업무자동화", "기간계",
      "전자결재", "협업툴"], "기간계·업무시스템 전환"),
]


def classify_domain(name, sub=""):
    """사업명·세부사업명 기반 분야 분류. 중복 매칭 허용, 매칭 없으면 빈 리스트."""
    text = (name or "") + " " + (sub or "")
    return [domain for keywords, domain in DOMAIN_RULES if any(kw in text for kw in keywords)]


def auto_tags(name, base_tags=None):
    """사업명 키워드 기반으로 태그를 생성. base_tags(사이트 기본태그)와 병합."""
    seen = set()
    tags = []
    for t in (base_tags or []):
        if t["text"] not in seen:
            tags.append(t)
            seen.add(t["text"])
    text = name or ""
    for keywords, tag_text, tag_type in KEYWORD_RULES:
        if any(kw in text for kw in keywords) and tag_text not in seen:
            tags.append({"text": tag_text, "type": tag_type})
            seen.add(tag_text)
    return tags


# ── IT회사 동향 탭: 추적 기업 매칭 ───────────────────────────────────────
# 대기업 그룹 캡티브마켓을 보유한 SI/IT서비스 계열사(VNTG 경쟁사) 11개.
# 기사 제목/본문에 등장하면 최우선으로 'IT회사 동향(국내)'으로 분류한다.
DOMESTIC_IT_COMPANIES = [
    "삼성SDS", "LG CNS", "현대오토에버", "SK C&C", "포스코DX",
    "한화시스템", "롯데정보통신", "CJ올리브네트웍스",
    "두산디지털이노베이션", "KT DS", "코오롱베니트",
]

# 해외: 특정 기업으로 제한하지 않고 "글로벌 빅테크/반도체/AI 기업" 관련이면
# 포함한다. 주요 기업명을 폭넓게 등록해 제목 매칭에 사용한다(대소문자 무관).
GLOBAL_TECH_KEYWORDS = [
    "엔비디아", "NVIDIA", "구글", "Google", "알파벳", "Alphabet",
    "마이크로소프트", "Microsoft", "MS", "애플", "Apple", "아마존", "Amazon",
    "메타", "Meta", "테슬라", "Tesla", "오픈AI", "OpenAI", "알리바바", "Alibaba",
    "텐센트", "Tencent", "바이두", "Baidu", "화웨이", "Huawei", "샤오미", "Xiaomi",
    "마이크론", "Micron", "인텔", "Intel", "퀄컴", "Qualcomm", "ASML",
    "TSMC", "브로드컴", "Broadcom", "AMD", "IBM", "오라클", "Oracle",
    "세일즈포스", "Salesforce", "소프트뱅크", "SoftBank", "바이트댄스", "ByteDance",
]


def match_domestic_company(text):
    """국내 추적 IT기업 12개 중 제목/본문에 등장하는 첫 회사명. 없으면 None."""
    t = text or ""
    return next((c for c in DOMESTIC_IT_COMPANIES if c in t), None)


def match_global_tech(text):
    """글로벌 빅테크/반도체/AI 기업 키워드 매칭 여부(제목/본문). 매칭된 키워드 또는 None."""
    t = text or ""
    return next((k for k in GLOBAL_TECH_KEYWORDS if k.lower() in t.lower()), None)
