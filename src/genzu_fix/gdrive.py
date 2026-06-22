"""Google Drive の「リンク共有」ファイルをサンドボックスから直接ダウンロードする。

MCPコネクタの10MB制限を受けずに大容量PSDを取得するための補助。
大容量ファイルのウイルススキャン確認(confirmトークン/usercontentフォーム)に対応。
※ファイルが「リンクを知っている全員が閲覧可」である必要がある。
"""
from __future__ import annotations
import http.cookiejar
import os
import re
import urllib.parse
import urllib.request

_UA = "Mozilla/5.0 (compatible; genzu-fix/1.0)"


def fetch(file_id: str, out_path: str, timeout: int = 600) -> int:
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", _UA)]
    base = "https://drive.google.com/uc?export=download&id=" + file_id

    r = op.open(base, timeout=timeout)
    data = r.read()
    ctype = r.headers.get("Content-Type", "")

    if "text/html" in ctype:
        html = data.decode("utf-8", "ignore")
        m = re.search(r'action="([^"]+)"', html)
        if m:  # 新フロー: 確認フォームを送信
            action = m.group(1).replace("&amp;", "&")
            inputs = dict(re.findall(r'name="([^"]+)"\s+value="([^"]*)"', html))
            sep = "&" if "?" in action else "?"
            url = action + sep + urllib.parse.urlencode(inputs)
            data = op.open(url, timeout=timeout).read()
        else:  # 旧フロー: cookie の download_warning トークン
            token = next((c.value for c in cj if c.name.startswith("download_warning")), None)
            if token:
                data = op.open(base + "&confirm=" + token, timeout=timeout).read()

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(data)
    return len(data)


if __name__ == "__main__":
    import sys
    n = fetch(sys.argv[1], sys.argv[2])
    print(f"{n} bytes -> {sys.argv[2]}")
