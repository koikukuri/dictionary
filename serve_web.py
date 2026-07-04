#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""謎解き単語検索ウェブアプリ用ローカルサーバー

起動:
    python serve_web.py

ブラウザで開く:
    http://localhost:8080/web/
"""

import http.server
import socketserver
from pathlib import Path

PORT = 8080
ROOT = Path(__file__).resolve().parent


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)


def main():
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print("=" * 50)
        print("  謎解き単語検索 Webアプリ")
        print(f"  http://localhost:{PORT}/web/")
        print("  Ctrl+C で停止")
        print("=" * 50)
        httpd.serve_forever()


if __name__ == "__main__":
    main()
