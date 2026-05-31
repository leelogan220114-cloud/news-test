#!/usr/bin/env python3
import os, sys, json, base64, requests
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup

KST = timezone(timedelta(hours=9))
KAKAO_REST_API_KEY  = os.environ["KAKAO_REST_API_KEY"]
KAKAO_REFRESH_TOKEN = os.environ["KAKAO_REFRESH_TOKEN"]
GITHUB_TOKEN        = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPOSITORY   = os.environ.get("GITHUB_REPOSITORY", "")

_H = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR,ko;q=0.9"}


def _get(url, enc="euc-kr"):
    try:
        r = requests.get(url, headers=_H, timeout=15)
        r.encoding = enc
        return BeautifulSoup(r.text, "lxml")
    except Exception as e:
        print(f"⚠ {url} 실패: {e}"); return None


def refresh_kakao_token():
    r = requests.post("https://kauth.kakao.com/oauth/token", data={
        "grant_type":    "refresh_token",
        "client_id":     KAKAO_REST_API_KEY,
        "refresh_token": KAKAO_REFRESH_TOKEN,
    })
    r.raise_for_status()
    data = r.json()
    new_rt = data.get("refresh_token")
    if new_rt and new_rt != KAKAO_REFRESH_TOKEN:
        _update_github_secret("KAKAO_REFRESH_TOKEN", new_rt)
    return data["access_token"]


def _update_github_secret(name, value):
    if not GITHUB_TOKEN or not GITHUB_REPOSITORY:
        return
    try:
        from nacl import encoding, public
        owner, repo = GITHUB_REPOSITORY.split("/", 1)
        gh = {"Authorization": f"Bearer {GITHUB_TOKEN}",
              "Accept": "application/vnd.github+json",
              "X-GitHub-Api-Version": "2022-11-28"}
        pk = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/actions/secrets/public-key",
            headers=gh).json()
        box = public.SealedBox(public.PublicKey(pk["key"].encode(), encoding.Base64Encoder()))
        encrypted = base64.b64encode(box.encrypt(value.encode())).decode()
        requests.put(
            f"https://api.github.com/repos/{owner}/{repo}/actions/secrets/{name}",
            headers=gh, json={"encrypted_value": encrypted, "key_id": pk["key_id"]})
        print(f"✓ GitHub Secret '{name}' 갱신 완료")
    except Exception as e:
        print(f"⚠ Secret 갱신 실패: {e}")


def send_kakao(token, title, body):
    """feed 타입 — title 200자 + description 512자, 한 번에 전송"""
    template = {
        "object_type": "feed",
        "content": {
            "title":       title[:200],
            "description": body[:512],
            "link": {
                "web_url":        "https://finance.naver.com",
                "mobile_web_url": "https://m.stock.naver.com",
            },
        },
        "buttons": [{"title": "네이버 금융", "link": {
            "web_url":        "https://finance.naver.com",
            "mobile_web_url": "https://m.stock.naver.com",
        }}],
    }
    r = requests.post(
        "https://kapi.kakao.com/v2/api/talk/memo/default/send",
        headers={"Authorization": f"Bearer {token}"},
        data={"template_object": json.dumps(template, ensure_ascii=False)},
    )
    r.raise_for_status()
    print("✓ 카카오톡 전송 완료")


def fetch_stocks():
    result = {"rise": [], "fall": []}
    for key, url in [
        ("rise", "https://finance.naver.com/sise/sise_rise.naver"),
        ("fall", "https://finance.naver.com/sise/sise_fall.naver"),
    ]:
        soup = _get(url)
        if not soup:
            continue
        for row in soup.select("table.type_2 tr"):
            n = row.select_one("td.name a")
            r = row.select_one("td.rate em") or row.select_one("td:nth-child(5)")
            if n and n.get_text(strip=True):
                result[key].append({
                    "name": n.get_text(strip=True),
                    "rate": r.get_text(strip=True) if r else "",
                })
            if len(result[key]) >= 5:
                break
    return result


def fetch_sectors():
    res = {"up": [], "down": []}
    soup = _get("https://finance.naver.com/sise/sise_group.naver")
    if not soup:
        return res
    for row in soup.select("table.type_1 tr, table.sise_tbl tr"):
        cols = row.select("td")
        if len(cols) < 3:
            continue
        name      = cols[0].get_text(strip=True)
        rate_text = cols[2].get_text(strip=True)
        if not name or name == "업종명":
            continue
        try:
            v = float(rate_text.replace("%","").replace("+","").replace(",",""))
        except Exception:
            continue
        (res["up"] if v > 0 else res["down"]).append({"sector": name, "rate": rate_text})
    res["up"]   = sorted(res["up"],
        key=lambda x: float(x["rate"].replace("%","").replace("+","").replace(",","")),
        reverse=True)[:4]
    res["down"] = sorted(res["down"],
        key=lambda x: float(x["rate"].replace("%","").replace("+","").replace(",","")))[:2]
    return res


def _trunc(s, n):
    return s[:n] + "…" if len(s) > n else s


def build_message(stocks, sectors, now):
    day_map  = {"Mon":"월","Tue":"화","Wed":"수","Thu":"목","Fri":"금","Sat":"토","Sun":"일"}
    dow      = day_map.get(now.strftime("%a"), now.strftime("%a"))
    date_str = f"{now.strftime('%m/%d')}({dow})"

    title = f"📊 [{date_str} 주식 브리핑]"

    rise = "  ".join(f"{_trunc(s['name'],6)}({s['rate']})" for s in stocks["rise"][:4]) or "없음"
    fall = "  ".join(f"{_trunc(s['name'],6)}({s['rate']})" for s in stocks["fall"][:4]) or "없음"
    up   = "  ".join(f"{_trunc(s['sector'],7)}({s['rate']})" for s in sectors["up"][:4])  or "없음"
    dn   = "  ".join(f"{_trunc(s['sector'],7)}({s['rate']})" for s in sectors["down"][:2]) or "없음"

    body = "\n".join([
        f"🔥 급등  {rise}",
        f"💥 급락  {fall}",
        f"📈 강세섹터  {up}",
        f"📉 약세섹터  {dn}",
    ])
    return title, body


def main():
    now = datetime.now(KST)
    print(f"[{now.strftime('%Y-%m-%d %H:%M KST')}] 시작")

    if now.weekday() >= 5:
        day   = "토요일" if now.weekday() == 5 else "일요일"
        token = refresh_kakao_token()
        send_kakao(token,
                   f"📅 {now.strftime('%m/%d')} 주식시장 휴장",
                   f"오늘은 {day}입니다. 좋은 주말 보내세요! 🌿")
        return

    stocks  = fetch_stocks()
    sectors = fetch_sectors()
    title, body = build_message(stocks, sectors, now)

    token = refresh_kakao_token()
    send_kakao(token, title, body)
    print("완료!")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"오류: {e}", file=sys.stderr)
        sys.exit(1)
