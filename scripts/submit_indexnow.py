#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree

INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
SITEMAP_NAMESPACE = {"sitemap": "http://www.sitemaps.org/schemas/sitemap/0.9"}
INDEXNOW_KEY_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,128}$")


def sitemap_urls(base_url: str) -> list[str]:
    with urlopen(f"{base_url}/sitemap.xml", timeout=20) as response:
        root = ElementTree.fromstring(response.read())
    return [
        location.text
        for location in root.findall("sitemap:url/sitemap:loc", SITEMAP_NAMESPACE)
        if location.text
    ]


def submit(base_url: str, key: str, urls: list[str]) -> int:
    parts = urlsplit(base_url)
    host = parts.netloc
    if parts.scheme not in {"http", "https"} or not host:
        raise ValueError("PUBLIC_BASE_URL must be an absolute HTTP or HTTPS URL")
    if not INDEXNOW_KEY_PATTERN.fullmatch(key):
        raise ValueError("INDEXNOW_KEY must contain 8-128 letters, numbers, or dashes")
    if any(urlsplit(url).netloc != host for url in urls):
        raise ValueError("All submitted URLs must use the configured public host")
    payload = json.dumps(
        {
            "host": host,
            "key": key,
            "keyLocation": f"{base_url}/{key}.txt",
            "urlList": urls[:10_000],
        }
    ).encode()
    request = Request(
        INDEXNOW_ENDPOINT,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        return response.status


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit the public sitemap URLs to IndexNow")
    parser.add_argument(
        "--base-url",
        default=os.getenv("PUBLIC_BASE_URL", ""),
        help="Canonical site origin; defaults to PUBLIC_BASE_URL",
    )
    parser.add_argument(
        "--key",
        default=os.getenv("INDEXNOW_KEY", ""),
        help="IndexNow key; defaults to INDEXNOW_KEY",
    )
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    if not base_url or not args.key:
        parser.error("both --base-url/PUBLIC_BASE_URL and --key/INDEXNOW_KEY are required")

    urls = sitemap_urls(base_url)
    if not urls:
        print("No URLs found in sitemap", file=sys.stderr)
        return 1
    status = submit(base_url, args.key, urls)
    print(f"IndexNow accepted {len(urls)} URLs with HTTP {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
