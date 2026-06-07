# -*- coding: utf-8 -*-
"""크롤러 공통 유틸: HTTP 세션, SSL 프록시 대응, 키워드 기반 자동 태깅."""
import re
import warnings
import requests

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
    (["주관"], "#주관기관", "role"),
    (["참여"], "#참여기관", "role"),
    (["수요기업"], "#수요기업", "role"),
    (["대기업"], "#대기업참여가능", "role"),
    # ── 도메인 (6+1 카테고리) ─────────────────────────────────────────────
    (["AI", "인공지능", "피지컬AI", "피지컬", "스마트공장", "스마트제조",
      "디지털전환", "DX", "디지털트윈", "예지보전", "비전검사", "머신비전",
      "자율제조", "자율화", "데이터"], "#AI", "domain"),
    (["철강", "금속재료", "금속", "소재", "뿌리기술", "세라믹", "화합물",
      "섬유", "탄소나노", "탄소소재"], "#철강·소재", "domain"),
    (["로봇", "협동로봇"], "#로봇", "domain"),
    (["자동차", "전기차", "수소차", "자율주행", "모빌리티", "EV",
      "배터리", "이차전지"], "#자동차·모빌리티", "domain"),
    (["반도체", "디스플레이", "시스템반도체", "웨이퍼"], "#반도체", "domain"),
    (["석유화학", "화학공정", "화학산업", "화학소재", "정유", "탄소중립",
      "탄소", "ESG", "수소", "신재생", "재생에너지", "태양광", "풍력"],
     "#석유화학·에너지", "domain"),
    (["조선", "방산", "해양", "항공", "공급망", "SCM", "물류",
      "뿌리산업", "도금", "주조", "단조", "용접", "표면처리"], "#기타제조산업", "domain"),
]


# ── 소관부처 화이트리스트 ───────────────────────────────────────────────
# 이 부처들의 공고만 저장한다. 그 외(국토부·복지부·농진청 등)는 제외.
MINISTRY_WHITELIST = [
    "산업부",
    "과학기술정보통신부",
    "중소벤처기업부",
    "조달청",
    "산업통상자원부",
]

# 출처별 부처 표기 변형(IRIS '산업통상부', 기업마당 '중기부' 등)까지 허용하는
# 정규화 키워드. 화이트리스트 부처를 포괄하도록 핵심 토큰만 사용한다.
_ALLOW_KEYWORDS = (
    "산업통상", "산업부", "산업",   # 산업부 / 산업통상자원부 / 산업통상부
    "과학기술", "과기",            # 과학기술정보통신부 / 과기부
    "중소벤처", "중기",            # 중소벤처기업부 / 중기부
    "조달",                        # 조달청
    "KEIT", "IITP", "KIAT", "NIPA", "KETEP", "KOTECH", "NTIS",  # 전문기관 직접 표기
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
