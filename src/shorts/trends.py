"""ネタ出し用トレンド自動収集（この実行環境から到達可能なソースのみ・全て無料）。

ソース（2026-07-06 実測で疎通確認済み）:
  - Google トレンド 日本 (RSS)      : 検索急上昇ワード
  - はてなブックマーク ホットエントリ : ネットで話題の記事
  - Wikipedia(ja) 日別閲覧数上位     : 世間の関心事（放送・訃報・炎上の反映が早い）
  - YouTube 急上昇 (yt-dlp, 任意)    : 動画で流行っているもの・ミーム

使い方:
    python -m src.shorts.trends -o work/trends/trends.json [--youtube]

出力: {"collected_at": ..., "items": [{source, title, detail, rank}]}
これを Claude が docs/shorts-ideation.md の型と掛け合わせて企画カードにする。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import urllib.request
import xml.etree.ElementTree as ET

UA = {"User-Agent": "Mozilla/5.0 (trend-collector for content ideation)"}


def _get(url: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def google_trends_jp(limit: int = 20) -> list[dict]:
    xml = _get("https://trends.google.com/trending/rss?geo=JP")
    root = ET.fromstring(xml)
    ns = {"ht": "https://trends.google.com/trending/rss"}
    items = []
    for i, item in enumerate(root.iter("item")):
        if i >= limit:
            break
        title = item.findtext("title") or ""
        traffic = item.findtext("ht:approx_traffic", default="", namespaces=ns)
        news = item.findtext("ht:news_item_title", default="", namespaces=ns)
        items.append({"source": "google_trends_jp", "title": title.strip(),
                      "detail": f"{traffic} {news}".strip(), "rank": i + 1})
    return items


def hatena_hotentry(limit: int = 20, category: str = "all") -> list[dict]:
    import html as _html

    xml = _get(f"https://b.hatena.ne.jp/hotentry/{category}.rss")
    root = ET.fromstring(xml)
    items = []
    for i, item in enumerate(root.iter("{http://purl.org/rss/1.0/}item")):
        if i >= limit:
            break
        # XMLパース後もHTMLエンティティ(&#x...;)が残ることがあるためデコード
        title = _html.unescape(item.findtext("{http://purl.org/rss/1.0/}title") or "")
        link = item.findtext("{http://purl.org/rss/1.0/}link") or ""
        items.append({"source": f"hatena_{category}", "title": title.strip(),
                      "detail": link, "rank": i + 1})
    return items


_WIKI_SKIP = re.compile(r"^(メインページ|特別:|Wikipedia:|Portal:|Help:|ノート:|Category:|Template:|ファイル:)")


def wikipedia_top_ja(limit: int = 20) -> list[dict]:
    day = dt.date.today() - dt.timedelta(days=1)
    url = (f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/"
           f"ja.wikipedia/all-access/{day.year}/{day.month:02d}/{day.day:02d}")
    data = json.loads(_get(url))
    items = []
    for a in data["items"][0]["articles"]:
        title = a["article"].replace("_", " ")
        if _WIKI_SKIP.match(title):
            continue
        items.append({"source": "wikipedia_ja_top", "title": title,
                      "detail": f"{a['views']:,} views", "rank": len(items) + 1})
        if len(items) >= limit:
            break
    return items


def x_trends_yahoo(limit: int = 20) -> list[dict]:
    """X(Twitter) の日本トレンド。Yahoo!リアルタイム検索（国内Xデータ提携）の
    トップページに埋め込まれた __NEXT_DATA__ から buzzTrend を取る。"""
    html = _get("https://search.yahoo.co.jp/realtime").decode("utf-8", errors="ignore")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise RuntimeError("__NEXT_DATA__ が見つからない（ページ構造変更の可能性）")
    data = json.loads(m.group(1))
    buzz = data["props"]["pageProps"]["pageData"]["buzzTrend"]["items"]
    items = []
    for i, b in enumerate(buzz[:limit]):
        tw = b.get("tweetCount") or ""
        items.append({"source": "x_trends_yahoo_jp", "title": b["query"],
                      "detail": f"{tw} tweets" if tw else "", "rank": i + 1})
    return items


def tiktok_trends_jp(limit: int = 20) -> list[dict]:
    """TikTok Creative Center（公開・認証不要ページ）の急上昇ハッシュタグ。
    APIは署名ヘッダが必要なため、ヘッドレスChromiumでページを開いて
    creative_radar_api のレスポンスを横取りする（定番手法）。"""
    from playwright.sync_api import sync_playwright

    url = ("https://ads.tiktok.com/business/creativecenter/inspiration/"
           "popular/hashtag/pc/ja")
    captured: list = []
    proxy_url = os.environ.get("HTTPS_PROXY")
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/opt/pw-browsers/chromium",
                                    args=["--no-sandbox"],
                                    proxy={"server": proxy_url} if proxy_url else None)
        page = browser.new_page()
        page.on("response", lambda r: captured.append(r)
                if "popular_trend/hashtag/list" in r.url else None)
        page.goto(url, wait_until="networkidle", timeout=60000)
        items = []
        for r in captured:
            try:
                data = r.json()
                for h in data.get("data", {}).get("list", []):
                    items.append({"source": "tiktok_cc_jp",
                                  "title": "#" + h.get("hashtag_name", ""),
                                  "detail": f"{h.get('publish_cnt', 0):,} posts",
                                  "rank": h.get("rank", len(items) + 1)})
            except Exception:
                continue
        browser.close()
    if not items:
        raise RuntimeError("Creative Center からデータを取得できず（要デバッグ）")
    return items[:limit]


def youtube_trending_jp(limit: int = 20) -> list[dict]:
    """yt-dlp のメタデータ取得（メディアDLなし）。数十秒かかるので任意。"""
    env = dict(os.environ, NODE_EXTRA_CA_CERTS="/root/.ccr/ca-bundle.crt")
    out = subprocess.check_output(
        ["yt-dlp", "--flat-playlist", "-J",
         "https://www.youtube.com/feed/trending?gl=JP&hl=ja"],
        env=env, timeout=120, stderr=subprocess.DEVNULL, text=True)
    data = json.loads(out)
    items = []
    for i, e in enumerate((data.get("entries") or [])[:limit]):
        items.append({"source": "youtube_trending_jp",
                      "title": (e.get("title") or "").strip(),
                      "detail": f"{e.get('view_count') or 0:,} views / {e.get('uploader') or ''}",
                      "rank": i + 1})
    return items


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--out", default="work/trends/trends.json")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--youtube", action="store_true", help="YouTube急上昇も収集（数十秒）")
    ap.add_argument("--tiktok", action="store_true", help="TikTok CCも収集（ヘッドレスブラウザ・1分程度）")
    args = ap.parse_args()

    collectors = [google_trends_jp, hatena_hotentry, wikipedia_top_ja, x_trends_yahoo]
    if args.tiktok:
        collectors.append(tiktok_trends_jp)
    if args.youtube:
        collectors.append(youtube_trending_jp)

    items, errors = [], []
    for fn in collectors:
        try:
            items.extend(fn(args.limit))
        except Exception as e:  # ソース1つの失敗で全体を止めない
            errors.append(f"{fn.__name__}: {e}")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    payload = {"collected_at": dt.datetime.now().isoformat(timespec="seconds"),
               "items": items, "errors": errors}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"{len(items)} 件収集 → {args.out}" + (f" (失敗: {errors})" if errors else ""))
    for it in items:
        print(f" [{it['source']:>18}] #{it['rank']:>2} {it['title'][:50]}")


if __name__ == "__main__":
    main()
