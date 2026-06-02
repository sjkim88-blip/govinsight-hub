# -*- coding: utf-8 -*-
"""진입점: 전체 크롤러를 실행하고 data/notices.json 으로 병합 저장한다.

각 크롤러는 try/except 로 감싸 실패해도 나머지를 계속 진행한다.
기존 notices.json 이 있으면 id 기준 중복을 제거하고 병합한다.
모든 공고에 classify_size() 를 적용해 sz 필드를 자동 분류한다.
"""
import os
import sys
import json

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
import g2b_crawler
import news_crawler
import iris_pre_crawler
import ntis_crawler
from common import is_allowed_ministry, is_company_fit, classify_size

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
    ("G2B",        g2b_crawler),
    ("NEWS",       news_crawler),
    ("IRIS사전공고", iris_pre_crawler),
    ("NTIS",       ntis_crawler),
]

# 전체교체형: 새 데이터가 수집되면 기존 같은 소스 항목을 모두 교체
REPLACE_SRCS = {"BIZINFO", "G2B", "뉴스", "IRIS사전공고", "NTIS"}


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
    """소관부처·출처 화이트리스트 통과 여부."""
    # 뉴스·NTIS·사전공고 src 는 ministry 대신 src 로 허용
    if item.get("src") in ("뉴스", "NTIS", "IRIS사전공고"):
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

    # 모든 공고에 sz(규모) 자동 분류
    for it in result:
        it["sz"] = classify_size(it.get("perProject"), it.get("totalBudget"))

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
