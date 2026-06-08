# -*- coding: utf-8 -*-
"""신규 공고 이메일 알림.

GitHub Actions 에서 update.py 실행 후 호출된다.
git HEAD 의 notices.json 과 현재 notices.json 을 비교해
새로 추가된 공고가 있으면 SMTP 로 팀 메일을 발송한다.

GitHub Secrets 필요:
  SMTP_USER  - 발신 Gmail 주소 (예: govinsight@gmail.com)
  SMTP_PASS  - Gmail 앱 비밀번호 (16자리)
  NOTIFY_TO  - 수신 이메일, 쉼표 구분 (예: a@co.kr,b@co.kr)
"""
import json
import os
import smtplib
import subprocess
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, "data", "notices.json")
DASHBOARD_URL = "https://sjkim88-blip.github.io/govinsight-hub/"

# 알림 제외 소스 (뉴스·레터는 공고가 아니므로 제외)
SKIP_SRCS = {"뉴스", "뉴스레터"}


def _load_current():
    with open(DATA_PATH, encoding="utf-8") as f:
        return {item["id"]: item for item in json.load(f)}


def _load_previous():
    """git HEAD 의 notices.json ID 집합을 반환 (커밋 전 비교용)."""
    try:
        r = subprocess.run(
            ["git", "show", "HEAD:data/notices.json"],
            capture_output=True, text=True, encoding="utf-8", check=True,
        )
        return {item["id"] for item in json.loads(r.stdout)}
    except Exception:
        return set()


def _build_html(items):
    sz_label = {"large": "대형", "mid": "중형", "small": "소형"}
    rows = ""
    for d in items:
        ministry = d.get("ministry", "")
        agency = d.get("agency", "")
        org = f"{ministry} › {agency}" if agency else ministry
        deadline = d.get("deadline") or "-"
        url = d.get("url") or DASHBOARD_URL
        sz = sz_label.get(d.get("sz", ""), "")
        rows += (
            f'<tr>'
            f'<td style="padding:9px 12px;border-bottom:1px solid #f0f0f0;font-size:13px">'
            f'  <a href="{url}" style="color:#1a1a1a;font-weight:600;text-decoration:none">{d.get("name","")}</a>'
            f'  {"<br><span style=\'font-size:11px;color:#bbb\'>" + sz + "</span>" if sz else ""}'
            f'</td>'
            f'<td style="padding:9px 12px;border-bottom:1px solid #f0f0f0;font-size:12px;color:#888;white-space:nowrap">{org}</td>'
            f'<td style="padding:9px 12px;border-bottom:1px solid #f0f0f0;font-size:12px;color:#888;white-space:nowrap">{deadline}</td>'
            f'<td style="padding:9px 12px;border-bottom:1px solid #f0f0f0;font-size:12px;color:#888;white-space:nowrap">{d.get("src","")}</td>'
            f'</tr>'
        )

    today = datetime.now().strftime("%Y-%m-%d")
    return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#f5f5f5;font-family:'Malgun Gothic',Arial,sans-serif">
<div style="max-width:680px;margin:32px auto;background:#fff;border-radius:8px;overflow:hidden;border:1px solid #e8e8e8">
  <div style="background:#1a1a1a;padding:20px 24px">
    <span style="color:#fff;font-size:16px;font-weight:600">Gov. Insight</span>
    <span style="color:#888;font-size:12px;margin-left:12px">신규 공고 알림</span>
  </div>
  <div style="padding:20px 24px">
    <p style="font-size:15px;font-weight:600;margin:0 0 4px">신규 공고 {len(items)}건이 등록됐습니다.</p>
    <p style="font-size:12px;color:#aaa;margin:0 0 20px">{today} 자동 갱신</p>
    <table style="width:100%;border-collapse:collapse;border:1px solid #e8e8e8;border-radius:6px;overflow:hidden">
      <thead>
        <tr style="background:#fafafa">
          <th style="padding:8px 12px;text-align:left;font-size:11px;color:#aaa;font-weight:600">사업명</th>
          <th style="padding:8px 12px;text-align:left;font-size:11px;color:#aaa;font-weight:600;white-space:nowrap">부처·기관</th>
          <th style="padding:8px 12px;text-align:left;font-size:11px;color:#aaa;font-weight:600;white-space:nowrap">마감일</th>
          <th style="padding:8px 12px;text-align:left;font-size:11px;color:#aaa;font-weight:600;white-space:nowrap">출처</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    <p style="margin-top:20px;font-size:13px">
      <a href="{DASHBOARD_URL}" style="color:#2d5a8e;font-weight:500">→ 대시보드에서 전체 보기</a>
    </p>
  </div>
  <div style="padding:12px 24px;background:#fafafa;border-top:1px solid #f0f0f0">
    <p style="font-size:11px;color:#ccc;margin:0">Gov. Insight 자동 갱신 시스템 · 수신 거부는 관리자에게 문의</p>
  </div>
</div>
</body></html>"""


def _send(items):
    user = os.environ.get("SMTP_USER", "").strip()
    pwd  = os.environ.get("SMTP_PASS", "").strip()
    to   = os.environ.get("NOTIFY_TO", "").strip()

    if not (user and pwd and to):
        print("  ⚠ SMTP_USER / SMTP_PASS / NOTIFY_TO 환경변수 미설정 — 알림 건너뜀")
        return

    recipients = [r.strip() for r in to.split(",") if r.strip()]
    today = datetime.now().strftime("%Y-%m-%d")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Gov. Insight] 신규 공고 {len(items)}건 ({today})"
    msg["From"]    = f"Gov. Insight <{user}>"
    msg["To"]      = ", ".join(recipients)

    plain = f"Gov. Insight 신규 공고 {len(items)}건 ({today})\n\n"
    for d in items:
        plain += f"• {d.get('name','')}  |  {d.get('deadline','-')}  |  {d.get('src','')}\n"
    plain += f"\n대시보드: {DASHBOARD_URL}"

    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(_build_html(items), "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(user, pwd)
        smtp.sendmail(user, recipients, msg.as_string())

    print(f"✓ 이메일 발송: {len(items)}건 → {', '.join(recipients)}")


def main():
    current  = _load_current()
    prev_ids = _load_previous()

    new_items = [
        v for k, v in current.items()
        if k not in prev_ids and v.get("src") not in SKIP_SRCS
    ]

    if not new_items:
        print("  · 신규 공고 없음 — 이메일 생략")
        return

    # 마감 임박 순 정렬
    new_items.sort(key=lambda x: x.get("deadline") or "9999")
    print(f"  · 신규 공고 {len(new_items)}건 발견")
    _send(new_items)


if __name__ == "__main__":
    main()
