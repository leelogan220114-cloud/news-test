#!/usr/bin/env python3
import os, sys, requests
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup

KST = timezone(timedelta(hours=9))
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_PARENT_PAGE_ID = os.environ.get("NOTION_PARENT_PAGE_ID", "36c96cdee84e81a998aedb03ab498afe")
_H = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR,ko;q=0.9"}

def _get(url, enc="euc-kr"):
    try:
        r = requests.get(url, headers=_H, timeout=15)
        r.encoding = enc
        return BeautifulSoup(r.text, "lxml")
    except Exception as e:
        print(f"⚠ {url} 실패: {e}"); return None

def fetch_top_news():
    news, seen = [], set()
    for url in ["https://finance.naver.com/news/mainnews.naver",
                "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258"]:
        soup = _get(url)
        if not soup: continue
        for sel in ["dl.simpleNewsList dt a", ".articleSubject a", ".articleTitle a", ".title a"]:
            for tag in soup.select(sel):
                t = tag.get_text(strip=True)
                href = tag.get("href", "")
                if t and len(t) > 6 and t not in seen:
                    seen.add(t)
                    link = f"https://finance.naver.com{href}" if href.startswith("/") else href
                    news.append({"title": t, "link": link})
        if len(news) >= 10: break
    return news[:5]

def fetch_stocks():
    result = {"rise": [], "fall": []}
    for key, url in [("rise","https://finance.naver.com/sise/sise_rise.naver"),
                     ("fall","https://finance.naver.com/sise/sise_fall.naver")]:
        soup = _get(url)
        if not soup: continue
        for row in soup.select("table.type_2 tr"):
            n = row.select_one("td.name a")
            r = row.select_one("td.rate em") or row.select_one("td:nth-child(5)")
            if n and n.get_text(strip=True):
                result[key].append({"name": n.get_text(strip=True), "rate": r.get_text(strip=True) if r else ""})
            if len(result[key]) >= 5: break
    return result

def fetch_sectors():
    res = {"up": [], "down": []}
    soup = _get("https://finance.naver.com/sise/sise_group.naver")
    if not soup: return res
    for row in soup.select("table.type_1 tr, table.sise_tbl tr"):
        cols = row.select("td")
        if len(cols) < 3: continue
        name = cols[0].get_text(strip=True)
        rate_text = cols[2].get_text(strip=True)
        if not name or name == "업종명": continue
        try:
            v = float(rate_text.replace("%","").replace("+","").replace(",",""))
        except: continue
        (res["up"] if v > 0 else res["down"]).append({"sector": name, "rate": rate_text})
    res["up"] = sorted(res["up"], key=lambda x: float(x["rate"].replace("%","").replace("+","").replace(",","")), reverse=True)[:5]
    res["down"] = sorted(res["down"], key=lambda x: float(x["rate"].replace("%","").replace("+","").replace(",","")))[:3]
    return res

def blk(t, obj, **kw): return {"object":"block","type":t,t:{"rich_text":[{"type":"text","text":{"content":obj}}],**kw}}
def h2(t): return blk("heading_2",t)
def h3(t): return blk("heading_3",t)
def para(t): return blk("paragraph",t)
def divider(): return {"object":"block","type":"divider","divider":{}}
def callout(t,e="📌"): return {"object":"block","type":"callout","callout":{"rich_text":[{"type":"text","text":{"content":t}}],"icon":{"emoji":e}}}
def bullet(t, link=""):
    rt = {"type":"text","text":{"content":t}}
    if link: rt["text"]["link"]={"url":link}
    return {"object":"block","type":"bulleted_list_item","bulleted_list_item":{"rich_text":[rt]}}

def build(news, stocks, sectors):
    b = [callout(f"수집 시각: {datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}","🕔"), divider(),
         h2("📈 주요 증시 뉴스 TOP 5")]
    b += [bullet(f"{i}. {n['title']}", n.get("link","")) for i,n in enumerate(news,1)] or [para("뉴스 없음")]
    b += [divider(), h2("⭐ 특징주"), h3("🔴 급등")]
    b += [bullet(f"{s['name']}  {s['rate']}") for s in stocks["rise"]] or [para("데이터 없음")]
    b += [h3("🔵 급락")]
    b += [bullet(f"{s['name']}  {s['rate']}") for s in stocks["fall"]] or [para("데이터 없음")]
    b += [divider(), h2("🏭 주도 섹터"), h3("📈 강세 업종")]
    b += [bullet(f"{s['sector']}  {s['rate']}") for s in sectors["up"]] or [para("데이터 없음")]
    b += [h3("📉 약세 업종")]
    b += [bullet(f"{s['sector']}  {s['rate']}") for s in sectors["down"]] or [para("데이터 없음")]
    b += [divider(), callout("본 뉴스는 투자 참고용 정보이며, 투자 결정은 본인 판단으로 하시기 바랍니다.","⚠️")]
    return b

def main():
    print(f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}] 시작")
    news = fetch_top_news(); print(f"뉴스 {len(news)}개")
    stocks = fetch_stocks(); sectors = fetch_sectors()
    now_kst = datetime.now(KST)
    title = f"📰 일일 뉴스 — {now_kst.strftime('%Y년 %m월 %d일')}"
    resp = requests.post("https://api.notion.com/v1/pages",
        headers={"Authorization":f"Bearer {NOTION_TOKEN}","Content-Type":"application/json","Notion-Version":"2022-06-28"},
        json={"parent":{"type":"page_id","page_id":NOTION_PARENT_PAGE_ID},"icon":{"type":"emoji","emoji":"📰"},
              "properties":{"title":{"title":[{"type":"text","text":{"content":title}}]}},
              "children":build(news,stocks,sectors)}, timeout=30)
    resp.raise_for_status()
    print(f"완료! {resp.json().get('url','')}")

if __name__ == "__main__":
    try: main()
    except Exception as e: print(f"오류: {e}", file=sys.stderr); sys.exit(1)
