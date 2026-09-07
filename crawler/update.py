# -*- coding: utf-8 -*-
"""진입점: 전체 크롤러를 실행하고 data/notices.json 으로 병합 저장한다.

각 크롤러는 try/except 로 감싸 실패해도 나머지를 계속 진행한다.
기존 notices.json 이 있으면 id 기준 중복을 제거하고 병합한다.
모든 공고에 classify_size() 를 적용해 sz 필드를 자동 분류한다.
"""
import os
import sys
import json
import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import iris_crawler
import keit_crawler
import iitp_crawler
import bizinfo_crawler
import news_crawler
import iris_pre_crawler
import ntis_crawler
import demand_crawler
import newsletter_crawler
import motir_crawler
import smartfactory_crawler
import keit_srome_crawler
import hankyung_industry_crawler
import itco_domestic_crawler
import itco_global_crawler
from common import is_allowed_ministry, is_company_fit, classify_size, classify_domain

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, "data", "notices.json")
INDEX_PATH = os.path.join(ROOT, "index.html")

SAMPLE_START = "/*SAMPLE_DATA_START*/"
SAMPLE_END = "/*SAMPLE_DATA_END*/"

CRAWLERS = [
    ("IRIS",       iris_crawler),
    ("KEIT",       keit_crawler),
    ("IITP",       iitp_crawler),
    ("BIZINFO",    bizinfo_crawler),
    ("NEWS",       news_crawler),
    ("IRIS사전공고", iris_pre_crawler),
    ("NTIS",       ntis_crawler),
    ("수요조사",    demand_crawler),
    ("뉴스레터",    newsletter_crawler),
    ("산자부",      motir_crawler),
    ("스마트공장닷컴", smartfactory_crawler),
    ("KEIT통합", keit_srome_crawler),
    ("한경산업",    hankyung_industry_crawler),
    ("IT동향(국내)", itco_domestic_crawler),
    ("IT동향(해외)", itco_global_crawler),
]

# 전체교체형: 새 데이터가 수집되면 기존 같은 소스 항목을 모두 교체
REPLACE_SRCS = {
    "BIZINFO", "뉴스", "IRIS사전공고", "NTIS", "수요조사", "뉴스레터", "산자부",
    "스마트공장닷컴", "KEIT통합", "한경", "전자신문", "AI타임스",
}


def _dedup_tags(item):
    tags = item.get("tags") or []
    seen, deduped = set(), []
    for t in tags:
        if t.get("text") not in seen:
            deduped.append(t)
            seen.add(t["text"])
    return {**item, "tags": deduped}


def load_existing():
    if os.path.exists(DATA_PATH):
        try:
            with open(DATA_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except (json.JSONDecodeError, OSError) as e:
            print(f"⚠ 기존 notices.json 읽기 실패: {e}")
    return []


def _ministry_ok(item):
    """소관부처·출처 화이트리스트 통과 여부.

    부처 화이트리스트는 "정부지원사업"(grant listing) 축에만 의미가 있다.
    IT회사 동향/산업별 뉴스는 ministry 개념이 없으므로 그대로 통과시킨다.
    """
    if item.get("axis") != "지원사업":
        return True
    # NTIS·사전공고·수요조사·스마트공장닷컴 등은 ministry 대신 src 로 허용
    if item.get("src") in ("NTIS", "IRIS사전공고", "수요조사", "스마트공장닷컴", "KEIT통합"):
        return True
    return is_allowed_ministry(item.get("ministry"))


def main():
    collected = []
    dropped = 0
    replaced_srcs = set()

    for name, mod in CRAWLERS:
        try:
            items = mod.run()
            kept = [
                it for it in items
                if _ministry_ok(it) and is_company_fit(it.get("name"), it.get("sub"))
            ]
            dropped += len(items) - len(kept)
            collected.extend(kept)
            srcs_got = {it["src"] for it in kept if it.get("src")}
            replaced_srcs |= srcs_got & REPLACE_SRCS
            print(f"✓ {name}: {len(kept)}개 수집")
        except Exception as e:  # noqa: BLE001
            print(f"⚠ {name} 실패: {e}")

    if dropped:
        print(f"  · 부처 화이트리스트/대기업 적합 필터로 {dropped}건 제외")

    # 병합: REPLACE_SRCS 는 기존 항목 버리고 새 데이터로 교체
    merged = {}
    for item in load_existing():
        if isinstance(item, dict) and "id" in item:
            if item.get("src") not in replaced_srcs:
                merged[item["id"]] = _dedup_tags(item)
    for item in collected:
        if isinstance(item, dict) and "id" in item:
            merged[item["id"]] = item

    # 화이트리스트 + 적합 필터 재적용 (기존 데이터 잔존 방어)
    result = [
        it for it in merged.values()
        if _ministry_ok(it) and is_company_fit(it.get("name"), it.get("sub"))
    ]

    # 마감(deadline 경과) 공고 제거: IRIS 등 병합형 소스는 재수집 시 사라진 마감
    # 공고를 자동으로 걸러내지 못하므로, 여기서 deadline 기준으로 직접 제거한다.
    # deadline 이 없는 항목(뉴스·뉴스레터 등 상시성 콘텐츠)은 유지한다.
    today = datetime.date.today().isoformat()
    before_cnt = len(result)
    result = [it for it in result if not it.get("deadline") or it["deadline"] >= today]
    expired_cnt = before_cnt - len(result)
    if expired_cnt:
        print(f"  · 마감된 공고 {expired_cnt}건 제외")

    # ministry 필드 정규화: 표기 변형 통일
    _MINISTRY_MAP = {
        "산업통상부": "산업통상자원부",
        "산업부": "산업통상자원부",
        "중기부": "중소벤처기업부",
        "과기부": "과학기술정보통신부",
    }
    for it in result:
        m = it.get("ministry", "")
        if m in _MINISTRY_MAP:
            it["ministry"] = _MINISTRY_MAP[m]

    # 태그명 마이그레이션: #산업부 → #산자부
    for it in result:
        for t in (it.get("tags") or []):
            if t.get("text") == "#산업부":
                t["text"] = "#산자부"

    # 전문기관·출처 태그 타입 마이그레이션: "ministry" → "agency"
    _AGENCY_TEXTS = {
        "#KEIT", "#IITP", "#NRF", "#TIPA", "#KISTEP", "#KIAT", "#NIPA", "#KETEP",
        "#IRIS", "#BIZINFO", "#NTIS", "#IRIS사전공고", "#전자신문", "#디지털타임스", "#KEIT이슈픽", "#AI타임스",
    }
    for it in result:
        for t in (it.get("tags") or []):
            if t.get("text") in _AGENCY_TEXTS and t.get("type") == "ministry":
                t["type"] = "agency"

    # 도메인 태그 재생성: KEYWORD_RULES 변경 시 기존 캐시 항목도 자동 갱신
    from common import auto_tags as _retag
    for it in result:
        non_domain = [t for t in (it.get("tags") or []) if t.get("type") != "domain"]
        it["tags"] = _retag(it.get("name", ""), non_domain)

    # 모든 공고에 sz(규모) 및 domain(분야) 자동 분류
    for it in result:
        it["sz"] = classify_size(it.get("perProject"), it.get("totalBudget"))
        it["domain"] = classify_domain(it.get("name"), it.get("sub"))

    cnt = {"large": 0, "mid": 0, "small": 0}
    for it in result:
        cnt[it["sz"]] = cnt.get(it["sz"], 0) + 1

    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(
        f"✓ 총 {len(result)}개 공고 저장 "
        f"(대형: {cnt['large']} / 중형: {cnt['mid']} / 소형: {cnt['small']})"
    )

    inject_fallback(result)


def inject_fallback(result):
    """index.html 의 SAMPLE_DATA(폴백)에 실데이터를 주입."""
    if not os.path.exists(INDEX_PATH):
        return
    try:
        html = open(INDEX_PATH, encoding="utf-8").read()
        s, e = html.find(SAMPLE_START), html.find(SAMPLE_END)
        if s == -1 or e == -1:
            return
        payload = json.dumps(result, ensure_ascii=False)
        block = f"{SAMPLE_START}\nconst SAMPLE_DATA = {payload};\n"
        html = html[:s] + block + html[e:]
        open(INDEX_PATH, "w", encoding="utf-8").write(html)
        print(f"✓ index.html 폴백 데이터 갱신({len(result)}건)")
    except Exception as ex:  # noqa: BLE001
        print(f"⚠ index.html 폴백 주입 실패: {ex}")


if __name__ == "__main__":
    main()
