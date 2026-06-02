# -*- coding: utf-8 -*-
"""나라장터(조달청) 혁신제품 공공조달 크롤러.

나라장터 차세대 시스템(g2b.go.kr)은 공공데이터포털(data.go.kr) 서비스키가
있어야 목록 API를 호출할 수 있는 잠금형 SPA다. 키 없이 임의 데이터를
넣으면 가짜 공고가 섞이므로, 현재는 빈 결과를 반환한다.

▶ 라이브 수집 활성화 방법
  1) data.go.kr 에서 '나라장터 혁신제품 지정정보' 활용신청 → 서비스키 발급
  2) 환경변수 G2B_SERVICE_KEY 로 키 주입
  3) 아래 run() 의 API 호출 분기를 활성화
"""
import os

try:
    from common import get, auto_tags  # noqa: F401
except ImportError:
    from crawler.common import get, auto_tags  # noqa: F401

BASE = "https://www.g2b.go.kr"
BASE_TAGS = [
    {"text": "#조달청", "type": "ministry"},
    {"text": "#혁신제품", "type": "biztype"},
]

SERVICE_KEY = os.environ.get("G2B_SERVICE_KEY", "")


def run():
    """공공조달 혁신제품 공고 수집. 서비스키 없으면 빈 리스트 반환(가짜 데이터 방지)."""
    if not SERVICE_KEY:
        # 키 미설정: 정직하게 빈 결과 (update.py 가 '0개 수집'으로 표시)
        return []

    # 서비스키가 있을 때만 공공데이터포털 혁신제품 API 호출
    api = "https://apis.data.go.kr/1230000/ad/InnoProdInfoService/getInnoProdInfoList"
    params = {
        "serviceKey": SERVICE_KEY,
        "type": "json",
        "numOfRows": "50",
        "pageNo": "1",
    }
    notices = []
    try:
        r = get(api, params=params, timeout=20)
        r.raise_for_status()
        items = (r.json().get("response", {}).get("body", {})
                 .get("items", {}).get("item", [])) or []
        if isinstance(items, dict):
            items = [items]
        for i, it in enumerate(items, 1):
            name = it.get("prdctNm") or it.get("innoPrdctNm") or "혁신제품"
            notices.append({
                "id": f"g2b_{it.get('innoPrdctId', i)}",
                "axis": "공공조달",
                "name": name,
                "sub": it.get("dminsttNm") or "",
                "perProject": "확인 필요",
                "totalBudget": "-",
                "ministry": "조달청",
                "agency": it.get("dminsttNm") or "조달청",
                "deadline": it.get("dsgntPdEndDt") or "",
                "src": "G2B",
                "url": it.get("dtlUrl") or BASE,
                "tags": auto_tags(name, BASE_TAGS),
            })
    except Exception as e:
        raise RuntimeError(f"G2B API 호출 실패: {e}")
    return notices


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
