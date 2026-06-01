#!/usr/bin/env python3
"""
매일 오전 7시 주식시장 일일 브리핑 → 카카오톡 전송
뉴스 스크래핑 기반 — pykrx / KRX 로그인 불필요
수집 내용이 없으면 전송하지 않음
"""

import os, sys, json, time, requests, schedule
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

BASE_DIR           = Path(__file__).parent
TOKEN_FILE         = BASE_DIR / ".kakao_tokens.json"
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "")

# Gmail SMTP (카카오톡 대신 사용 시)
GMAIL_ADDRESS      = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
SENDGRID_API_KEY   = os.getenv("SENDGRID_API_KEY", "")

MARKET_HOLIDAYS: set[str] = {
    "20250101","20250128","20250129","20250130","20250131",
    "20250301","20250505","20250506","20250515","20250606",
    "20250815","20251003","20251009","20251225",
    "20260101","20260216","20260217","20260218","20260219",
    "20260301","20260505","20260525","20260606",
    "20260924","20260925","20260926","20260929",
    "20261009","20261225",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Referer": "https://finance.naver.com/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# 섹터 분류 키워드
SECTOR_KEYWORDS = {
    "AI/반도체": ["반도체", "AI", "HBM", "엔비디아", "DRAM", "낸드"],
    "조선":      ["조선", "HD현대", "한화오션", "삼성중공업", "LNG선"],
    "방산":      ["방산", "한화에어로", "LIG넥스원", "K방산"],
    "바이오":    ["바이오", "제약", "신약", "임상", "FDA"],
    "2차전지":   ["2차전지", "배터리", "LG에너지", "삼성SDI", "양극재"],
    "자동차":    ["자동차", "현대차", "기아", "EV", "전기차"],
    "금융":      ["금융", "은행", "증권", "보험", "금리"],
}


# ─── 유틸 ──────────────────────────────────────────────────────────────────────

def is_trading_day(dt=None) -> bool:
    if dt is None:
        dt = datetime.now()
    return dt.weekday() < 5 and dt.strftime("%Y%m%d") not in MARKET_HOLIDAYS


def _get(url: str, **kw) -> requests.Response | None:
    try:
        r = requests.get(url, headers=_HEADERS, timeout=8, **kw)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"[WARN] {url[:60]} — {e}")
        return None


# ─── 데이터 수집 ───────────────────────────────────────────────────────────────

def fetch_index() -> dict[str, str]:
    """네이버 모바일 API — KOSPI / KOSDAQ 지수"""
    result = {}
    for name, code in [("KOSPI", "KOSPI"), ("KOSDAQ", "KOSDAQ")]:
        r = _get(f"https://m.stock.naver.com/api/index/{code}/basic")
        if not r:
            continue
        try:
            d     = r.json()
            price = d.get("closePrice", "")
            ratio = d.get("fluctuationsRatio", "")
            code2 = d.get("compareToPreviousPrice", {}).get("code", "")
            arrow = "▲" if code2 == "2" else ("▼" if code2 == "5" else "─")
            result[name] = f"{price}  {arrow}{ratio}%"
        except Exception:
            pass
    return result


def fetch_naver_finance_headlines(n: int = 8) -> list[str]:
    """네이버 금융 메인 뉴스 헤드라인"""
    r = _get("https://finance.naver.com/news/mainnews.naver")
    if not r:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    titles = []
    for el in soup.select("ul.realtimeNewsList li a, .mainNewsList li a, dl.newsList dt a"):
        t = el.get_text(strip=True)
        if t and len(t) > 8 and t not in titles:
            titles.append(t)
        if len(titles) >= n:
            break
    return titles


def fetch_news_search(query: str, n: int = 3) -> list[str]:
    """네이버 뉴스 검색 — 당일 기사"""
    r = _get(
        "https://search.naver.com/search.naver",
        params={"where": "news", "query": query, "sort": "1", "pd": "1"},
    )
    if not r:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    return [el.get_text(strip=True) for el in soup.select(".news_tit")[:n]]


def fetch_top_stocks() -> list[str]:
    """네이버 금융 — 코스피 급등주 상위 종목명"""
    r = _get("https://finance.naver.com/sise/sise_rise_day.naver?sosok=0")
    if not r:
        return []
    soup  = BeautifulSoup(r.text, "html.parser")
    names = []
    for a in soup.select("table.type_2 td a, table td.col_name a"):
        name = a.get_text(strip=True)
        if name and name not in names and len(name) >= 2:
            names.append(name)
        if len(names) >= 5:
            break
    return names


# ─── 브리핑 조립 ───────────────────────────────────────────────────────────────

_DAY_KO = ["월","화","수","목","금","토","일"]


def _classify_sectors(headlines: list[str]) -> dict[str, list[str]]:
    """헤드라인을 섹터별로 분류"""
    buckets: dict[str, list[str]] = {}
    for h in headlines:
        for sector, kws in SECTOR_KEYWORDS.items():
            if any(kw in h for kw in kws):
                buckets.setdefault(sector, []).append(h)
                break  # 첫 번째 매칭 섹터에만 할당
    return buckets


def build_briefing() -> str | None:
    """
    브리핑 문자열 반환.
    수집 내용이 충분하지 않으면 None → 전송 skip.
    """
    now  = datetime.now()
    date = now.strftime(f"%m/%d({_DAY_KO[now.weekday()]})")

    lines:       list[str] = []
    has_content: bool      = False

    # ① 지수
    indices = fetch_index()
    if indices:
        lines.append(f"📊 [{date}] 주식시장 브리핑")
        lines.append("─" * 22)
        lines.append("📈 주요 지수")
        for name, val in indices.items():
            lines.append(f"  {name}  {val}")
        has_content = True
    else:
        lines.append(f"📊 [{date}] 주식시장 브리핑")
        lines.append("─" * 22)

    # ② 급등주 + 관련 뉴스
    top = fetch_top_stocks()
    if top:
        lines.append("\n🚀 특징주")
        for stock in top[:3]:
            lines.append(f"  • {stock}")
            news = fetch_news_search(stock, n=1)
            if news:
                lines.append(f"    └ {news[0][:48]}")
        has_content = True

    # ③ 뉴스 헤드라인 → 섹터 분류
    headlines = fetch_naver_finance_headlines(n=10)
    if not headlines:
        # fallback: 시황 검색
        headlines = fetch_news_search("증시 시황 오늘", n=5)

    sectors = _classify_sectors(headlines)
    if sectors:
        lines.append("\n🏭 주도 섹터 & 이슈")
        for sector, items in list(sectors.items())[:4]:
            lines.append(f"  [{sector}]")
            for h in items[:2]:
                lines.append(f"    • {h[:50]}")
        has_content = True

    # ④ 분류되지 않은 일반 시황 뉴스
    classified = {h for items in sectors.values() for h in items}
    general = [h for h in headlines if h not in classified][:2]
    if general:
        lines.append("\n📰 기타 시황")
        for h in general:
            lines.append(f"  • {h[:50]}")

    if not has_content:
        return None

    lines.append(f"\n─ 07:00 자동 브리핑 · 전일 기준 ─")
    return "\n".join(lines)


# ─── 이메일 전송 ──────────────────────────────────────────────────────────────

def send_gmail(text: str):
    """Gmail SMTP — 앱 비밀번호 방식 (2단계 인증 필요)"""
    import smtplib
    from email.mime.text import MIMEText

    now = datetime.now()
    msg = MIMEText(text, "plain", "utf-8")
    msg["Subject"] = f"📊 주식 브리핑 {now.strftime('%m/%d')}"
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = GMAIL_ADDRESS

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        s.send_message(msg)
    print(f"[{now:%H:%M:%S}] Gmail 전송 완료 ✓")


def send_sendgrid(text: str):
    """SendGrid API — 앱 비밀번호 없이 사용 가능 (무료 100건/일)"""
    now = datetime.now()
    resp = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={"Authorization": f"Bearer {SENDGRID_API_KEY}",
                 "Content-Type": "application/json"},
        json={
            "personalizations": [{"to": [{"email": GMAIL_ADDRESS}]}],
            "from":    {"email": GMAIL_ADDRESS},
            "subject": f"📊 주식 브리핑 {now.strftime('%m/%d')}",
            "content": [{"type": "text/plain", "value": text}],
        },
        timeout=15,
    )
    resp.raise_for_status()
    print(f"[{now:%H:%M:%S}] SendGrid 전송 완료 ✓")


def send_notification(text: str):
    """전송 수단 자동 선택: SendGrid → Gmail SMTP → KakaoTalk"""
    if SENDGRID_API_KEY and GMAIL_ADDRESS:
        send_sendgrid(text)
    elif GMAIL_ADDRESS and GMAIL_APP_PASSWORD:
        send_gmail(text)
    else:
        send_kakao(text)


# ─── KakaoTalk ────────────────────────────────────────────────────────────────

def _load_tokens() -> dict:
    # 로컬: 파일 우선 / GitHub Actions: 환경변수
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text())
    at = os.getenv("KAKAO_ACCESS_TOKEN", "")
    rt = os.getenv("KAKAO_REFRESH_TOKEN", "")
    if rt:
        return {"access_token": at, "refresh_token": rt}
    return {}

def _save_tokens(tokens: dict):
    # GitHub Actions 환경에서는 파일 저장 생략
    if os.getenv("GITHUB_ACTIONS"):
        return
    TOKEN_FILE.write_text(json.dumps(tokens, indent=2))
    TOKEN_FILE.chmod(0o600)

def _refresh_token() -> str:
    tokens = _load_tokens()
    rt = tokens.get("refresh_token")
    if not rt:
        raise RuntimeError("먼저 'python kakao_auth.py' 를 실행하세요.")
    r = requests.post(
        "https://kauth.kakao.com/oauth/token",
        data={"grant_type": "refresh_token", "client_id": KAKAO_REST_API_KEY,
              "refresh_token": rt},
        timeout=15,
    )
    r.raise_for_status()
    d = r.json()
    tokens["access_token"] = d["access_token"]
    if "refresh_token" in d:
        tokens["refresh_token"] = d["refresh_token"]
    _save_tokens(tokens)
    return tokens["access_token"]

def send_kakao(text: str):
    tokens = _load_tokens()
    token  = tokens.get("access_token") or _refresh_token()

    def _post(t: str):
        return requests.post(
            "https://kapi.kakao.com/v2/api/talk/memo/default/send",
            headers={"Authorization": f"Bearer {t}"},
            data={"template_object": json.dumps({
                "object_type": "text",
                "text":        text[:2000],
                "link": {"web_url":        "https://finance.naver.com",
                         "mobile_web_url": "https://m.stock.naver.com"},
            })},
            timeout=15,
        )

    resp = _post(token)
    if resp.status_code == 401:
        resp = _post(_refresh_token())
    resp.raise_for_status()
    print(f"[{datetime.now():%H:%M:%S}] 카카오톡 전송 완료 ✓")


# ─── 엔트리포인트 ──────────────────────────────────────────────────────────────

def run_briefing():
    now = datetime.now()
    print(f"[{now:%Y-%m-%d %H:%M:%S}] 브리핑 시작")

    if not is_trading_day(now):
        kind = "주말" if now.weekday() >= 5 else "공휴일"
        send_notification(
            f"📊 [{now.strftime('%m/%d')}] 오늘은 {kind}입니다.\n"
            f"증시 휴장 — 다음 거래일에 브리핑을 드립니다 😊"
        )
        return

    try:
        msg = build_briefing()
        if msg:
            send_notification(msg)
        else:
            print("수집 내용 없음 — 전송 생략")
    except Exception as e:
        print(f"ERROR: {e}")
        try:
            send_notification(f"⚠️ 브리핑 실패 ({now.strftime('%m/%d %H:%M')})\n{e}")
        except Exception as e2:
            print(f"오류 메시지 전송도 실패: {e2}")


def main():
    if "--now" in sys.argv or "-n" in sys.argv:
        run_briefing()
        return

    schedule.every().day.at("07:00").do(run_briefing)
    print("스케줄러 가동 — 매일 07:00 브리핑 전송")
    print("즉시 실행 테스트: python daily_briefing.py --now")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
