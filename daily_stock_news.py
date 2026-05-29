#!/usr/bin/env python3
import os, sys, json, base64, requests
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup

KST = timezone(timedelta(hours=9))
KAKAO_REST_API_KEY = os.environ["KAKAO_REST_API_KEY"]
KAKAO_REFRESH_TOKEN = os.environ["KAKAO_REFRESH_TOKEN"]
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "")

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
        "grant_type": "refresh_token",
        "client_id": KAKAO_REST_API_KEY,
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


def send_kakao(token, text):
    r = requests.post(
        "https://kapi.kakao.com/v2/api/talk/memo/default/send",
        headers={"Authorization": f"Bearer {token}"},
        data={"template_object": json.dumps({
            "object_type": "text",
            "text": text[:200],
            "link": {"web_url": "https://finance.naver.com",
                     "mobile_web_url": "https://m.stock.naver.com"},
        }, ensure_ascii=False)})
    r.raise_for_status()
    print(f"✓ 전송: {text[:30]}…")


def fetch_top_news():
    news, seen = [], set()
    for url in [
        "https://finance.naver.com/news/mainnews.naver",
        "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258",
    ]:
        soup = _get(url)
        if not soup:
            continue
        for sel in ["dl.simpleNewsList dt a", ".articleSubject a", ".articleTitle a", ".title a"]:
            for tag in soup.select(sel):
                t = tag.get_text(strip=True)
                href = tag.get("href", "")
                if t and len(t) > 6 and t not in seen:
                    seen.add(t)
                    link = f"https://finance.naver.com{href}" if href.startswith("/") else href
                    news.append({"title": t, "link": link})
        if len(news) >= 10:
            break
    return news[:5]


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
                result[key].append({"name": n.get_text(strip=True),
                                    "rate": r.get_text(strip=True) if r else ""})
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
        name = cols[0].get_text(strip=True)
        rate_text = cols[2].get_text(strip=True)
        if not name or name == "업종명":
            continue
        try:
            v = float(rate_text.replace("%", "").replace("+", "").replace(",", ""))
        except Exception:
            continue
        (res["up"] if v > 0 else res["down"]).append({"sector": name, "rate": rate_text})
    res["up"] = sorted(res["up"],
        key=lambda x: float(x["rate"].replace("%","").replace("+","").replace(",","")),
        reverse=True)[:5]
    res["down"] = sorted(res["down"],
        key=lambda x: float(x["rate"].replace("%","").replace("+","").replace(",","")))[:3]
    return res


def _trunc(s, n):
    return s[:n] + "…" if len(s) > n else s


def build_messages(news, stocks, sectors, now):
    day_map = {"Mon":"월","Tue":"화","Wed":"수","Thu":"목","Fri":"금","Sat":"토","Sun":"일"}
    dow = day_map.get(now.strftime("%a"), now.strftime("%a"))
    date_str = f"{now.strftime('%m/%d')}({dow})"

    lines = [f"📰 {date_str} 주요 뉴스 TOP5"]
    for i, n in enumerate(news, 1):
        lines.append(f"{i}. {_trunc(n['title'], 27)}")
    if not news:
        lines.append("(뉴스 없음)")
    msg1 = "\n".join(lines)

    rise = "  ".join(f"{s['name']}({s['rate']})" for s in stocks["rise"][:3]) or "없음"
    fall = "  ".join(f"{s['name']}({s['rate']})" for s in stocks["fall"][:3]) or "없음"
    msg2 = f"⭐ 특징주\n▲ 급등: {rise}\n▼ 급락: {fall}"

    up = "  ".join(f"{s['sector']}({s['rate']})" for s in sectors["up"][:3]) or "없음"
    dn = "  ".join(f"{s['sector']}({s['rate']})" for s in sectors["down"][:2]) or "없음"
    msg3 = f"🏭 주도 섹터\n📈 강세: {up}\n📉 약세: {dn}"

    return msg1, msg2, msg3


def main():
    now = datetime.now(KST)
    print(f"[{now.strftime('%Y-%m-%d %H:%M KST')}] 시작")

    news = fetch_top_news()
    print(f"뉴스 {len(news)}개")
    stocks = fetch_stocks()
    sectors = fetch_sectors()

    token = refresh_kakao_token()
    for msg in build_messages(news, stocks, sectors, now):
        send_kakao(token, msg)

    print("완료!")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"오류: {e}", file=sys.stderr)
        sys.exit(1)
