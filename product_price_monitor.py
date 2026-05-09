#!/usr/bin/env python3
"""Generic Japan product price monitor.

This script monitors public search result pages for any product name. It is
standalone, cross-platform, and uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html
import json
import os
import re
import smtplib
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from pathlib import Path
from typing import Any


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36 ProductPriceMonitor/1.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.8,en;q=0.6,zh-CN;q=0.5",
}

DEFAULT_RISKY_TERMS = [
    "junk",
    "ジャンク",
    "訳あり",
    "わけあり",
    "動作未確認",
    "未確認",
    "故障",
    "破損",
    "部品取り",
    "箱のみ",
    "空箱",
    "as-is",
    "untested",
    "for parts",
]

DEFAULT_ACCESSORY_TERMS = [
    "accessory",
    "accessories",
    "adapter",
    "adaptor",
    "cable",
    "case",
    "cover",
    "holder",
    "mount",
    "stand",
    "protector",
    "sticker",
    "skin",
    "ケーブル",
    "アダプタ",
    "変換",
    "ケース",
    "カバー",
    "保護",
    "スタンド",
    "ホルダー",
    "フィルム",
    "ステッカー",
    "延長",
    "電源ケーブル",
    "箱のみ",
]

DEFAULT_PROVIDERS = [
    {
        "name": "PriceRank",
        "source_type": "aggregator",
        "condition": "all",
        "url_template": "https://price-rank.com/search?keyword={query_plus}",
        "enabled": False,
    },
    {
        "name": "Yahoo Shopping",
        "source_type": "shop search",
        "condition": "new",
        "url_template": "https://shopping.yahoo.co.jp/search?p={query_plus}",
        "enabled": True,
        "require_item_url": True,
    },
    {
        "name": "Rakuten",
        "source_type": "shop search",
        "condition": "new",
        "url_template": "https://search.rakuten.co.jp/search/mall/{query_path}/",
        "enabled": True,
        "require_item_url": True,
    },
    {
        "name": "Mercari",
        "source_type": "flea market",
        "condition": "used",
        "url_template": "https://jp.mercari.com/search?keyword={query_plus}&sort=price&order=asc",
        "enabled": True,
        "require_item_url": True,
    },
    {
        "name": "Yahoo Auctions",
        "source_type": "auction",
        "condition": "used",
        "url_template": "https://auctions.yahoo.co.jp/search/search?p={query_plus}&n=50&s1=cbids&o1=a",
        "enabled": True,
        "require_item_url": True,
    },
    {
        "name": "HardOff NetMall",
        "source_type": "shop used",
        "condition": "used",
        "url_template": "https://netmall.hardoff.co.jp/search/?q={query_plus}",
        "enabled": True,
        "require_item_url": True,
    },
    {
        "name": "Janpara",
        "source_type": "shop used",
        "condition": "used",
        "url_template": "https://www.janpara.co.jp/sale/search/result/?KEYWORDS={query_plus}",
        "enabled": True,
        "require_item_url": True,
    },
]

DEFAULT_CHINA_REFERENCE = {
    "enabled": True,
    "provider": "Goofish",
    "currency": "CNY",
    "url_template": "https://www.goofish.com/search?q={query_plus}",
    "api_url_template": "https://h5api.m.goofish.com/h5/mtop.taobao.idlemtopsearch.pc.search/1.0/",
    "app_key": "34839810",
    "api": "mtop.taobao.idlemtopsearch.pc.search",
    "rows_per_page": 30,
    "timeout_seconds": 12,
    "min_price_cny": 100,
    "max_price_cny": 200_000,
    "cookie": "env:PRICE_GOOFISH_COOKIE",
}

DEFAULT_CHINA_RISKY_TERMS = [
    "故障",
    "坏",
    "维修",
    "拆机",
    "尸体",
    "无显示",
    "花屏",
    "不能用",
    "不亮",
    "报废",
    "空盒",
    "盒子",
    "包装盒",
]

DEFAULT_CHINA_ACCESSORY_TERMS = [
    "配件",
    "保护",
    "保护壳",
    "保护套",
    "线",
    "数据线",
    "转接线",
    "供电线",
    "支架",
    "底座",
    "收纳",
    "收纳包",
    "贴膜",
    "镜片",
    "头带",
    "电池头带",
    "面罩",
    "手柄",
]


class ConfigError(Exception):
    """Raised when a configuration or state JSON file cannot be loaded."""


def local_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"Invalid JSON in {path}: {exc.msg} at line {exc.lineno}, column {exc.colno}"
        ) from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Invalid JSON in {path}: expected a top-level object")
    return data


def save_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_notification_env(config_path: Path, env_file: str | None) -> None:
    if env_file:
        load_env_file(Path(env_file).expanduser().resolve())
        return

    load_env_file(config_path.parent / ".product_price_monitor.env")
    load_env_file(Path.home() / ".config" / "product-price-monitor.env")


def resolve_path(base_dir: Path, value: str | None, fallback: str) -> Path:
    raw = Path(value or fallback)
    return raw if raw.is_absolute() else base_dir / raw


def configured(value: Any) -> bool:
    return value is not None and value != "" and value != []


def secret_value(value: Any) -> Any:
    if isinstance(value, str) and value.startswith("env:"):
        return os.environ.get(value[4:], "")
    if isinstance(value, list):
        return [secret_value(item) for item in value]
    if isinstance(value, dict):
        return {key: secret_value(item) for key, item in value.items()}
    return value


def notify_value(notify: dict[str, Any], key: str, default: Any = "") -> Any:
    return secret_value(notify.get(key, default))


def strip_html(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    text = html.unescape(raw)
    return re.sub(r"\s+", " ", text).strip()


def fetch_text(url: str, timeout: int, headers: dict[str, str] | None = None) -> str:
    request = urllib.request.Request(url, headers={**DEFAULT_HEADERS, **(headers or {})})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
        encoding = response.headers.get_content_charset() or "utf-8"
    return body.decode(encoding, errors="replace")


def render_url(template: str, query: str) -> str:
    query_plus = urllib.parse.quote_plus(query)
    query_path = urllib.parse.quote(query, safe="")
    return template.format(query=query_plus, query_plus=query_plus, query_path=query_path)


def watch_key(name: str) -> str:
    normalized = re.sub(r"\s+", " ", name.strip()).lower()
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:10]
    return f"{normalized}:{digest}"


def terms_for_query(query: str) -> list[str]:
    lowered = query.lower()
    terms = re.findall(r"[a-z]+|\d+|[\u3040-\u30ff\u3400-\u9fff]{2,}", lowered)
    cleaned: list[str] = []
    for term in terms:
        if len(term) < 2 and not term.isdigit():
            continue
        if term not in cleaned:
            cleaned.append(term)
    return cleaned


def text_terms(text: str) -> list[str]:
    return terms_for_query(strip_html(text))


def default_min_matched_terms(query_terms: list[str]) -> int:
    if len(query_terms) <= 4:
        return len(query_terms)
    return max(4, int(len(query_terms) * 0.75))


def has_consecutive_terms(needle: list[str], haystack: list[str]) -> bool:
    if not needle:
        return True
    if len(needle) > len(haystack):
        return False
    width = len(needle)
    return any(haystack[index : index + width] == needle for index in range(len(haystack) - width + 1))


def has_required_query_sequence(query_terms: list[str], snippet: str, watch: dict[str, Any]) -> bool:
    if not bool(watch.get("require_query_sequence", True)):
        return True
    if len(query_terms) < 2:
        return True
    if not all(re.fullmatch(r"[a-z]+|\d+", term) for term in query_terms):
        return True
    return has_consecutive_terms(query_terms, text_terms(snippet))


def parse_price(value: str) -> int:
    return int(value.replace(",", ""))


def accepted_candidate(
    price: int,
    snippet: str,
    watch: dict[str, Any],
    provider: dict[str, Any],
    query_terms: list[str],
    min_matched_terms: int,
) -> dict[str, Any] | None:
    min_price = int(watch.get("min_price_jpy", 500))
    max_price = int(watch.get("max_price_jpy", 2_000_000))
    if not (min_price <= price <= max_price):
        return None

    lower_snippet = snippet.lower()
    risky_terms = watch.get("exclude_terms", DEFAULT_RISKY_TERMS)
    accessory_terms = watch.get("accessory_terms", DEFAULT_ACCESSORY_TERMS)
    allow_risky = bool(watch.get("allow_risky", False))
    allow_accessory = bool(watch.get("allow_accessory", False))

    if not allow_risky and any(term.lower() in lower_snippet for term in risky_terms):
        return None
    if not allow_accessory and any(term.lower() in lower_snippet for term in accessory_terms):
        return None

    matched_terms = [term for term in query_terms if term.lower() in lower_snippet]
    if len(matched_terms) < min_matched_terms:
        return None
    if not has_required_query_sequence(query_terms, snippet, watch):
        return None

    score = len(matched_terms)
    if provider.get("condition") == "new":
        score += 1
    if provider.get("source_type") == "shop used":
        score += 1

    return {"score": score, "matched_terms": matched_terms}


ITEM_URL_PATTERNS = [
    re.compile(r"https?://(?:page\.)?auctions\.yahoo\.co\.jp/jp/auction/[A-Za-z0-9_-]+"),
    re.compile(r"https?://jp\.mercari\.com/item/[A-Za-z0-9_-]+"),
    re.compile(r"https?://item\.rakuten\.co\.jp/[^\"'<>\s\\]+"),
    re.compile(r"https?://store\.shopping\.yahoo\.co\.jp/[^\"'<>\s\\]+"),
    re.compile(r"https?://netmall\.hardoff\.co\.jp/[^\"'<>\s\\]+"),
    re.compile(r"https?://www\.janpara\.co\.jp/[^\"'<>\s\\]+"),
]


def extract_item_url(raw_window: str, base_url: str) -> str:
    normalized = html.unescape(raw_window).replace("\\/", "/")
    hrefs = re.findall(r"""href\s*=\s*["']([^"']+)["']""", normalized, flags=re.IGNORECASE)
    urls = [urllib.parse.urljoin(base_url, href) for href in hrefs]
    for pattern in ITEM_URL_PATTERNS:
        urls.extend(match.group(0) for match in pattern.finditer(normalized))
    for url in urls:
        clean_url = url.split("#", 1)[0]
        if any(pattern.fullmatch(clean_url) for pattern in ITEM_URL_PATTERNS):
            return clean_url
    return ""


def min_matched_terms_for_watch(watch: dict[str, Any], query_terms: list[str]) -> int:
    min_matched_terms = watch.get("min_matched_terms")
    if min_matched_terms is None:
        return default_min_matched_terms(query_terms)
    return int(min_matched_terms)


PRICE_PATTERNS = [
    re.compile(r"(?:¥|￥)\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,8})"),
    re.compile(r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,8})\s*円"),
]


def extract_yahoo_auction_prices(
    raw: str,
    watch: dict[str, Any],
    provider: dict[str, Any],
    base_url: str,
) -> list[dict[str, Any]]:
    query_terms = watch.get("include_terms") or terms_for_query(watch["name"])
    min_matched_terms = min_matched_terms_for_watch(watch, query_terms)
    candidates: list[dict[str, Any]] = []
    product_blocks = re.findall(r'(?is)<li class="Product\b.*?</li>', raw)

    for block in product_blocks:
        item_url = extract_item_url(block, base_url)
        if not item_url:
            continue

        price: int | None = None
        buy_now_label = re.search(
            r'(?is)<span class="Product__label">\s*即決\s*</span>\s*'
            r'<span class="Product__priceValue[^"]*">\s*([0-9,]+)\s*円\s*</span>',
            block,
        )
        if buy_now_label:
            price = parse_price(buy_now_label.group(1))
        else:
            buy_now_match = re.search(r'data-auction-buynowprice="([0-9]+)"', block)
            if buy_now_match:
                price = parse_price(buy_now_match.group(1))
        if price is None:
            continue

        snippet = strip_html(block)
        accepted = accepted_candidate(price, snippet, watch, provider, query_terms, min_matched_terms)
        if not accepted:
            continue

        candidates.append(
            {
                "price_jpy": price,
                "snippet": snippet[:260],
                "url": item_url,
                **accepted,
            }
        )

    return dedupe_candidates(candidates)


def dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates.sort(key=lambda item: (item["price_jpy"], -item["score"]))
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for item in candidates:
        identity = (item["price_jpy"], item.get("url", ""))
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(item)
    return deduped[:10]


def extract_prices(raw: str, watch: dict[str, Any], provider: dict[str, Any], base_url: str = "") -> list[dict[str, Any]]:
    query_terms = watch.get("include_terms") or terms_for_query(watch["name"])
    min_matched_terms = min_matched_terms_for_watch(watch, query_terms)
    if provider.get("name") == "Yahoo Auctions":
        return extract_yahoo_auction_prices(raw, watch, provider, base_url)
    require_item_url = bool(provider.get("require_item_url", provider.get("name") == "Yahoo Auctions"))
    candidates: list[dict[str, Any]] = []

    for pattern in PRICE_PATTERNS:
        for match in pattern.finditer(raw):
            price = parse_price(match.group(1))

            left = max(0, match.start() - 700)
            right = min(len(raw), match.end() + 700)
            raw_window = raw[left:right]
            snippet = strip_html(raw[left:right])

            accepted = accepted_candidate(price, snippet, watch, provider, query_terms, min_matched_terms)
            if not accepted:
                continue
            item_url = extract_item_url(raw_window, base_url)
            if require_item_url and not item_url:
                continue

            candidates.append(
                {
                    "price_jpy": price,
                    "snippet": snippet[:260],
                    "url": item_url,
                    **accepted,
                }
            )

    return dedupe_candidates(candidates)


def merged_china_reference_config(config: dict[str, Any]) -> dict[str, Any]:
    reference = dict(DEFAULT_CHINA_REFERENCE)
    reference.update(config.get("china_reference") or {})
    return reference


def parse_cny_price(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, dict):
        for path in (
            ("price",),
            ("value",),
            ("amount",),
            ("integer",),
            ("priceInfo",),
        ):
            price = parse_cny_price(first_nested_value(value, [path]))
            if price is not None:
                return price
        integer = first_nested_value(value, [("integer", "text"), ("integer", "value")])
        decimal = first_nested_value(value, [("decimal", "text"), ("decimal", "value")])
        if integer is not None:
            raw = f"{integer}.{decimal}" if decimal is not None else str(integer)
            return parse_cny_price(raw)
        return None
    if isinstance(value, list):
        for item in value:
            price = parse_cny_price(item)
            if price is not None:
                return price
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        price = float(value)
        if price <= 0:
            return None
        # Several Alibaba/Goofish payloads carry prices in cents as plain integers.
        if isinstance(value, int) and value >= 100_000:
            price = price / 100
        return price

    text = html.unescape(str(value))
    match = re.search(r"(?:¥|￥|rmb|cny)?\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)\s*(?:元)?", text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def first_nested_value(data: Any, paths: list[tuple[str, ...]]) -> Any:
    for path in paths:
        cursor = data
        for key in path:
            if not isinstance(cursor, dict) or key not in cursor:
                cursor = None
                break
            cursor = cursor[key]
        if cursor not in (None, ""):
            return cursor
    return None


def text_from_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return strip_html(value)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        for key in ("text", "title", "content", "value"):
            text = text_from_value(value.get(key))
            if text:
                return text
    return ""


def goofish_item_payload(row: dict[str, Any]) -> dict[str, Any]:
    for key in ("data", "cardData", "exContent", "main"):
        value = row.get(key)
        if isinstance(value, dict):
            return value
    return row


def goofish_title(item: dict[str, Any]) -> str:
    value = first_nested_value(
        item,
        [
            ("title",),
            ("titleSummary", "text"),
            ("itemTextDTO", "title"),
            ("main", "title"),
            ("exContent", "title"),
        ],
    )
    return text_from_value(value)


def goofish_item_id(item: dict[str, Any]) -> str:
    value = first_nested_value(
        item,
        [
            ("id",),
            ("itemId",),
            ("item_id",),
            ("main", "itemId"),
            ("exContent", "itemId"),
        ],
    )
    return str(value) if value is not None else ""


def goofish_category_id(item: dict[str, Any]) -> str:
    value = first_nested_value(
        item,
        [
            ("categoryId",),
            ("trackParams", "cateId"),
            ("clickParam", "args", "cCatId"),
            ("main", "categoryId"),
            ("exContent", "categoryId"),
        ],
    )
    return str(value) if value is not None else "0"


def goofish_price(item: dict[str, Any]) -> float | None:
    value = first_nested_value(
        item,
        [
            ("price",),
            ("priceInfo",),
            ("priceText",),
            ("main", "price"),
            ("exContent", "price"),
        ],
    )
    return parse_cny_price(value)


def goofish_location(item: dict[str, Any]) -> str:
    value = first_nested_value(
        item,
        [
            ("city",),
            ("area",),
            ("userInfo", "city"),
            ("seller", "sellerNick"),
            ("exContent", "area"),
        ],
    )
    return text_from_value(value)


def list_from_config(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item.strip().lower() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip().lower() for item in value if str(item).strip()]
    return []


def unique_terms(*groups: list[str]) -> list[str]:
    terms: list[str] = []
    for group in groups:
        for term in group:
            cleaned = str(term).strip().lower()
            if cleaned and cleaned not in terms:
                terms.append(cleaned)
    return terms


def china_reference_query(watch: dict[str, Any]) -> str:
    return str(watch.get("china_reference_query") or watch["name"]).strip()


def china_reference_terms(watch: dict[str, Any], query: str) -> list[str]:
    configured_terms = list_from_config(watch.get("china_reference_terms"))
    if configured_terms:
        return configured_terms
    include_terms = list_from_config(watch.get("include_terms"))
    if include_terms:
        return include_terms
    return terms_for_query(query)


def accepted_china_reference_candidate(
    price_cny: float,
    snippet: str,
    watch: dict[str, Any],
    reference: dict[str, Any],
    query_terms: list[str],
) -> dict[str, Any] | None:
    min_price = float(watch.get("china_reference_min_price_cny", reference.get("min_price_cny", 100)))
    max_price = float(watch.get("china_reference_max_price_cny", reference.get("max_price_cny", 200_000)))
    if not (min_price <= price_cny <= max_price):
        return None

    lower_snippet = snippet.lower()
    risky_terms = unique_terms(
        list_from_config(watch.get("exclude_terms")),
        [term.lower() for term in DEFAULT_RISKY_TERMS],
        [term.lower() for term in DEFAULT_CHINA_RISKY_TERMS],
    )
    accessory_terms = unique_terms(
        list_from_config(watch.get("accessory_terms")),
        [term.lower() for term in DEFAULT_ACCESSORY_TERMS],
        [term.lower() for term in DEFAULT_CHINA_ACCESSORY_TERMS],
    )
    if not bool(watch.get("allow_risky", False)) and any(term in lower_snippet for term in risky_terms):
        return None
    if not bool(watch.get("allow_accessory", False)) and any(term in lower_snippet for term in accessory_terms):
        return None

    matched_terms = [term for term in query_terms if term.lower() in lower_snippet]
    min_matched_terms = int(
        watch.get("china_reference_min_matched_terms", default_min_matched_terms(query_terms))
    )
    if len(matched_terms) < min_matched_terms:
        return None

    require_sequence = bool(watch.get("china_reference_require_query_sequence", watch.get("require_query_sequence", True)))
    if require_sequence and not has_required_query_sequence(query_terms, snippet, watch):
        return None

    return {"score": len(matched_terms), "matched_terms": matched_terms}


def goofish_search_url(reference: dict[str, Any], query: str) -> str:
    return render_url(str(reference.get("url_template") or DEFAULT_CHINA_REFERENCE["url_template"]), query)


def goofish_token_from_cookie(cookie: str) -> str:
    match = re.search(r"(?:^|;\s*)_m_h5_tk=([^_;]+)", cookie)
    return match.group(1) if match else ""


def build_goofish_api_url(reference: dict[str, Any], query: str) -> str:
    app_key = str(reference.get("app_key") or DEFAULT_CHINA_REFERENCE["app_key"])
    api = str(reference.get("api") or DEFAULT_CHINA_REFERENCE["api"])
    data = {
        "pageNumber": 1,
        "keyword": query,
        "fromFilter": False,
        "rowsPerPage": int(reference.get("rows_per_page", 30)),
        "sortValue": "",
        "sortField": "",
        "customDistance": "",
        "gps": "",
        "propValueStr": {},
        "customGps": "",
        "searchReqFromPage": "pcSearch",
        "extraFilterValue": {},
        "userPositionJson": "",
    }
    data_json = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    timestamp = str(int(time.time() * 1000))
    cookie = str(secret_value(reference.get("cookie", "")) or "")
    token = goofish_token_from_cookie(cookie)
    sign = hashlib.md5(f"{token}&{timestamp}&{app_key}&{data_json}".encode("utf-8")).hexdigest() if token else ""
    params = {
        "jsv": "2.7.3",
        "appKey": app_key,
        "t": timestamp,
        "sign": sign,
        "v": "1.0",
        "type": "originaljson",
        "dataType": "json",
        "api": api,
        "data": data_json,
    }
    return f"{reference.get('api_url_template') or DEFAULT_CHINA_REFERENCE['api_url_template']}?{urllib.parse.urlencode(params)}"


def goofish_response_error(payload: dict[str, Any]) -> str:
    ret = payload.get("ret")
    if not ret:
        return ""
    values = ret if isinstance(ret, list) else [ret]
    for value in values:
        text = str(value)
        if not text.startswith("SUCCESS"):
            return text.split("::", 1)[0]
    return ""


def extract_goofish_reference_candidates(
    payload: dict[str, Any],
    watch: dict[str, Any],
    reference: dict[str, Any],
) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    rows = data.get("resultList") if isinstance(data.get("resultList"), list) else []
    query = china_reference_query(watch)
    query_terms = china_reference_terms(watch, query)
    candidates: list[dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        item = goofish_item_payload(row)
        if not isinstance(item, dict):
            continue
        title = goofish_title(item)
        price = goofish_price(item)
        item_id = goofish_item_id(item)
        if not title or price is None or not item_id:
            continue
        category_id = goofish_category_id(item)
        location = goofish_location(item)
        raw_snippet = json.dumps(item, ensure_ascii=False)
        snippet = strip_html(" ".join(part for part in [title, location, raw_snippet] if part))
        accepted = accepted_china_reference_candidate(price, snippet, watch, reference, query_terms)
        if not accepted:
            continue
        url = f"https://www.goofish.com/item?id={urllib.parse.quote(item_id)}&categoryId={urllib.parse.quote(category_id)}"
        candidates.append(
            {
                "reference_provider": str(reference.get("provider", "Goofish")),
                "reference_price_cny": price,
                "reference_title": title,
                "reference_url": url,
                "reference_location": location,
                "reference_snippet": snippet[:260],
                **accepted,
            }
        )

    candidates.sort(key=lambda item: (item["reference_price_cny"], -item["score"]))
    return candidates[:10]


def check_china_reference(watch: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    reference = merged_china_reference_config(config)
    provider = str(reference.get("provider", "Goofish"))
    if not bool(reference.get("enabled", False)):
        return {}
    if provider.lower() != "goofish":
        return {
            "reference_provider": provider,
            "reference_error": f"Unsupported reference provider: {provider}",
        }

    query = china_reference_query(watch)
    search_url = goofish_search_url(reference, query)
    cookie = str(secret_value(reference.get("cookie", "")) or "")
    headers = {
        "Accept": "application/json,text/plain,*/*",
        "Origin": "https://www.goofish.com",
        "Referer": search_url,
    }
    if cookie:
        headers["Cookie"] = cookie

    try:
        api_url = build_goofish_api_url(reference, query)
        raw = fetch_text(api_url, int(reference.get("timeout_seconds", 12)), headers)
        payload = json.loads(raw)
        error = goofish_response_error(payload)
        if error:
            return {
                "reference_provider": provider,
                "reference_search_url": search_url,
                "reference_error": error,
            }
        candidates = extract_goofish_reference_candidates(payload, watch, reference)
        if not candidates:
            return {
                "reference_provider": provider,
                "reference_search_url": search_url,
                "reference_error": "No relevant Goofish reference found",
            }
        best = candidates[0]
        best["reference_search_url"] = search_url
        return best
    except json.JSONDecodeError:
        return {
            "reference_provider": provider,
            "reference_search_url": search_url,
            "reference_error": "Invalid Goofish response",
        }
    except urllib.error.HTTPError as exc:
        return {
            "reference_provider": provider,
            "reference_search_url": search_url,
            "reference_error": f"HTTP {exc.code}: {exc.reason}",
        }
    except urllib.error.URLError as exc:
        return {
            "reference_provider": provider,
            "reference_search_url": search_url,
            "reference_error": f"Network error: {exc.reason}",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "reference_provider": provider,
            "reference_search_url": search_url,
            "reference_error": str(exc),
        }


def attach_reference(results: list[dict[str, Any]], reference: dict[str, Any]) -> None:
    if not reference:
        return
    for result in results:
        result.update(reference)


def format_cny_price(price: Any) -> str:
    if not isinstance(price, (int, float)):
        return "-"
    if float(price).is_integer():
        return f"{int(price):,} CNY"
    return f"{price:,.2f} CNY"


def format_reference_short(item: dict[str, Any]) -> str:
    provider = item.get("reference_provider")
    if not provider:
        return ""
    price = item.get("reference_price_cny")
    if isinstance(price, (int, float)):
        title = item.get("reference_title") or ""
        return f"{format_cny_price(price)} via {provider}" + (f" / {title}" if title else "")
    error = item.get("reference_error")
    return f"{provider}: {error}" if error else ""


def format_reference_report(item: dict[str, Any]) -> str:
    provider = item.get("reference_provider")
    if not provider:
        return "-"
    price = item.get("reference_price_cny")
    if isinstance(price, (int, float)):
        label = f"{format_cny_price(price)} {provider}"
        url = item.get("reference_url") or item.get("reference_search_url")
        return f"[{label}]({url})" if url else label
    error = item.get("reference_error")
    search_url = item.get("reference_search_url")
    label = f"{provider}: {error}" if error else str(provider)
    return f"[{label}]({search_url})" if search_url else label


def condition_allowed(watch: dict[str, Any], provider: dict[str, Any]) -> bool:
    desired = watch.get("condition", "all")
    if desired == "all":
        return True
    provider_condition = provider.get("condition", "all")
    return provider_condition == desired or provider_condition == "all"


def check_provider(watch: dict[str, Any], provider: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    url = render_url(provider["url_template"], watch["name"])
    result: dict[str, Any] = {
        "checked_at": local_iso(),
        "watch_name": watch["name"],
        "provider": provider["name"],
        "source_type": provider.get("source_type", ""),
        "condition": provider.get("condition", ""),
        "url": url,
        "price_jpy": None,
        "target_price_jpy": watch.get("target_price_jpy"),
        "snippet": "",
        "error": "",
        "hit": False,
    }

    try:
        timeout = int(provider.get("timeout_seconds", config.get("monitor", {}).get("timeout_seconds", 30)))
        raw = fetch_text(url, timeout)
        candidates = extract_prices(raw, watch, provider, url)
        if not candidates:
            result["error"] = "No relevant price found"
            return result
        best = candidates[0]
        result["price_jpy"] = best["price_jpy"]
        result["snippet"] = best["snippet"]
        result["url"] = best.get("url") or url
    except urllib.error.HTTPError as exc:
        result["error"] = f"HTTP {exc.code}: {exc.reason}"
    except urllib.error.URLError as exc:
        result["error"] = f"Network error: {exc.reason}"
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    return result


def enabled_providers(config: dict[str, Any], watch: dict[str, Any]) -> list[dict[str, Any]]:
    providers = config.get("providers") or DEFAULT_PROVIDERS
    allowed_names = set(watch.get("providers", []))
    selected = []
    for provider in providers:
        if not provider.get("enabled", True):
            continue
        if allowed_names and provider["name"] not in allowed_names:
            continue
        if not condition_allowed(watch, provider):
            continue
        selected.append(provider)
    return selected


def evaluate_hits(
    watch: dict[str, Any],
    results: list[dict[str, Any]],
    state: dict[str, Any],
    repeat_hours: float,
) -> list[dict[str, Any]]:
    valid = [r for r in results if isinstance(r.get("price_jpy"), int)]
    if not valid:
        return []
    valid.sort(key=lambda row: row["price_jpy"])
    best = valid[0]

    key = watch_key(watch["name"])
    state.setdefault("watches", {})
    watch_state = state["watches"].setdefault(key, {})
    previous_best = watch_state.get("best_price_jpy")
    target = watch.get("target_price_jpy")
    now = utc_now()

    hit_reason = ""
    if isinstance(target, int) and best["price_jpy"] <= target:
        hit_reason = f"price <= target {target:,} JPY"
    elif previous_best is None and watch.get("alert_first_seen", True):
        hit_reason = "first observed low price"
    elif isinstance(previous_best, int):
        drop_jpy = int(watch.get("drop_jpy", 1000))
        drop_percent = float(watch.get("drop_percent", 5.0))
        required_drop = max(drop_jpy, int(previous_best * drop_percent / 100))
        if best["price_jpy"] <= previous_best - required_drop:
            hit_reason = f"new low by at least {required_drop:,} JPY"

    if previous_best is None or best["price_jpy"] < previous_best:
        watch_state["best_price_jpy"] = best["price_jpy"]
        watch_state["best_provider"] = best["provider"]
        watch_state["best_url"] = best["url"]
        watch_state["best_seen_at"] = now.isoformat()

    watch_state["last_price_jpy"] = best["price_jpy"]
    watch_state["last_provider"] = best["provider"]
    watch_state["last_seen_at"] = now.isoformat()

    if not hit_reason:
        return []

    last_alert_at = watch_state.get("last_alert_at")
    if last_alert_at:
        try:
            last_alert = dt.datetime.fromisoformat(last_alert_at)
            if last_alert.tzinfo is None:
                last_alert = last_alert.replace(tzinfo=dt.UTC)
            if (now - last_alert).total_seconds() < repeat_hours * 3600:
                last_alert_price = watch_state.get("last_alert_price_jpy")
                min_price = int(watch.get("min_price_jpy", 0))
                old_alert_is_valid = isinstance(last_alert_price, int) and last_alert_price >= min_price
                if old_alert_is_valid and best["price_jpy"] >= last_alert_price:
                    return []
        except ValueError:
            pass

    best["hit"] = True
    best["hit_reason"] = hit_reason
    watch_state["last_alert_at"] = now.isoformat()
    watch_state["last_alert_price_jpy"] = best["price_jpy"]
    return [best]


def send_http_request(
    url: str,
    payload: bytes,
    content_type: str,
    headers: dict[str, str] | None = None,
) -> None:
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": content_type, **(headers or {}), **DEFAULT_HEADERS},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        response.read()


def send_email_notification(notify: dict[str, Any], subject: str, message: str) -> None:
    smtp = notify.get("smtp") or {}
    host = secret_value(smtp.get("host"))
    username = secret_value(smtp.get("username"))
    password = secret_value(smtp.get("password"))
    recipients = secret_value(smtp.get("to")) or []
    if isinstance(recipients, str):
        recipients = [recipients]

    if not host or not username or not password or not recipients:
        return

    port = int(smtp.get("port", 465))
    sender = secret_value(smtp.get("from")) or username
    use_ssl = bool(smtp.get("ssl", port == 465))
    use_starttls = bool(smtp.get("starttls", not use_ssl))

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content(message)

    context = ssl.create_default_context()
    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=20, context=context) as server:
            server.login(username, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=20) as server:
            if use_starttls:
                server.starttls(context=context)
            server.login(username, password)
            server.send_message(msg)


def send_notifications(config: dict[str, Any], message: str) -> list[str]:
    notify = config.get("notify", {})
    errors: list[str] = []
    subject = notify_value(notify, "title", "Product price alert")

    if configured(secret_value((notify.get("smtp") or {}).get("host"))):
        try:
            send_email_notification(notify, subject, message[:8000])
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Email notification failed: {exc}")

    token = notify_value(notify, "telegram_bot_token")
    chat_id = notify_value(notify, "telegram_chat_id")
    if token and chat_id:
        payload = urllib.parse.urlencode(
            {"chat_id": chat_id, "text": message[:3900], "disable_web_page_preview": "true"}
        ).encode("utf-8")
        try:
            send_http_request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                payload,
                "application/x-www-form-urlencoded",
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Telegram notification failed: {exc}")

    bark_key = notify_value(notify, "bark_device_key")
    bark_url = notify_value(notify, "bark_url")
    if bark_key or bark_url:
        bark_server = notify_value(notify, "bark_server", "https://api.day.app")
        url = bark_url or f"{bark_server.rstrip('/')}/{bark_key}"
        payload = json.dumps(
            {
                "title": subject,
                "body": message[:3900],
                "group": notify_value(notify, "bark_group", "Price Monitor"),
                "level": notify_value(notify, "bark_level", "timeSensitive"),
            }
        ).encode("utf-8")
        try:
            send_http_request(url, payload, "application/json; charset=utf-8")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Bark notification failed: {exc}")

    ntfy_topic = notify_value(notify, "ntfy_topic")
    if ntfy_topic:
        ntfy_server = notify_value(notify, "ntfy_server", "https://ntfy.sh").rstrip("/")
        headers = {
            "Title": subject,
            "Priority": str(notify_value(notify, "ntfy_priority", "high")),
            "Tags": notify_value(notify, "ntfy_tags", "shopping"),
        }
        ntfy_token = notify_value(notify, "ntfy_token")
        if ntfy_token:
            headers["Authorization"] = f"Bearer {ntfy_token}"
        try:
            send_http_request(
                f"{ntfy_server}/{ntfy_topic}",
                message[:3900].encode("utf-8"),
                "text/plain; charset=utf-8",
                headers=headers,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"ntfy notification failed: {exc}")

    pushplus_token = notify_value(notify, "pushplus_token")
    if pushplus_token:
        payload = json.dumps(
            {
                "token": pushplus_token,
                "title": subject,
                "content": message.replace("\n", "<br>"),
                "template": notify_value(notify, "pushplus_template", "html"),
                "channel": notify_value(notify, "pushplus_channel", "wechat"),
            }
        ).encode("utf-8")
        try:
            send_http_request("https://www.pushplus.plus/send", payload, "application/json")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"PushPlus notification failed: {exc}")

    if notify.get("desktop_beep", True):
        try:
            import winsound

            winsound.Beep(988, 180)
            winsound.Beep(1319, 220)
        except Exception:
            pass

    return errors


def format_alert(alerts: list[dict[str, Any]]) -> str:
    lines = [f"Product price alert: {len(alerts)} match(es) at {local_iso()}"]
    for item in alerts:
        price = item.get("price_jpy")
        target = item.get("target_price_jpy")
        reference = format_reference_short(item)
        lines.extend(
            [
                "",
                f"Product: {item['watch_name']}",
                f"Provider: {item['provider']} ({item.get('source_type', '')}, {item.get('condition', '')})",
                f"Price: {price:,} JPY" if isinstance(price, int) else "Price: -",
                f"Target: {target:,} JPY" if isinstance(target, int) else "Target: auto baseline",
                f"China Ref: {reference}" if reference else "China Ref: -",
                f"Reason: {item.get('hit_reason', '')}",
                f"URL: {item['url']}",
                f"China Ref URL: {item.get('reference_url') or item.get('reference_search_url', '')}",
                f"Snippet: {item.get('snippet', '')}",
            ]
        )
    return "\n".join(lines)


def append_log(path: Path, results: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "checked_at",
                "watch_name",
                "provider",
                "source_type",
                "condition",
                "price_jpy",
                "target_price_jpy",
                "hit",
                "error",
                "url",
                "reference_provider",
                "reference_price_cny",
                "reference_url",
                "reference_title",
                "reference_error",
                "snippet",
            ],
        )
        if not exists:
            writer.writeheader()
        for result in results:
            writer.writerow({key: result.get(key, "") for key in writer.fieldnames or []})


def md_cell(value: Any) -> str:
    return str(value).replace("\n", " ").replace("|", "\\|")


def write_report(path: Path, config: dict[str, Any], results: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Product Price Monitor Report",
        "",
        f"- Generated: {local_iso()}",
        f"- Watches: {len(config.get('watches', []))}",
        "",
        "| Signal | Product | Provider | Source | Condition | Price | Target | China Ref | Notes |",
        "| --- | --- | --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    sorted_results = sorted(
        results,
        key=lambda r: (not r.get("hit", False), r.get("price_jpy") if isinstance(r.get("price_jpy"), int) else 10**12),
    )
    for result in sorted_results:
        signal = "BUY" if result.get("hit") else "watch"
        price = f"{result['price_jpy']:,} JPY" if isinstance(result.get("price_jpy"), int) else "-"
        target = (
            f"{result['target_price_jpy']:,} JPY"
            if isinstance(result.get("target_price_jpy"), int)
            else "auto"
        )
        note = result.get("hit_reason") or result.get("error") or result.get("snippet", "")[:120]
        item_link = f"[{result['provider']}]({result['url']})"
        reference = format_reference_report(result)
        lines.append(
            f"| {md_cell(signal)} | {md_cell(result['watch_name'])} | {item_link} | "
            f"{md_cell(result.get('source_type', ''))} | {md_cell(result.get('condition', ''))} | "
            f"{md_cell(price)} | {md_cell(target)} | {md_cell(reference)} | {md_cell(note)} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def default_config() -> dict[str, Any]:
    return {
        "state_file": ".product_price_state.json",
        "log_file": "product_price_log.csv",
        "report_file": "product_price_report.md",
        "monitor": {
            "interval_seconds": 120,
            "timeout_seconds": 30,
            "repeat_alert_hours": 12,
        },
        "notify": {
            "title": "Product deal alert",
            "desktop_beep": True,
            "telegram_bot_token": "env:PRICE_TELEGRAM_BOT_TOKEN",
            "telegram_chat_id": "env:PRICE_TELEGRAM_CHAT_ID",
            "bark_device_key": "env:PRICE_BARK_DEVICE_KEY",
            "bark_server": "https://api.day.app",
            "ntfy_server": "https://ntfy.sh",
            "ntfy_topic": "env:PRICE_NTFY_TOPIC",
            "ntfy_token": "env:PRICE_NTFY_TOKEN",
            "pushplus_token": "env:PRICE_PUSHPLUS_TOKEN",
            "smtp": {
                "host": "env:PRICE_SMTP_HOST",
                "port": 465,
                "ssl": True,
                "starttls": False,
                "username": "env:PRICE_SMTP_USERNAME",
                "password": "env:PRICE_SMTP_PASSWORD",
                "from": "env:PRICE_SMTP_FROM",
                "to": ["env:PRICE_SMTP_TO"],
            },
        },
        "providers": DEFAULT_PROVIDERS,
        "china_reference": DEFAULT_CHINA_REFERENCE,
        "watches": [],
    }


def load_or_create_config(path: Path) -> dict[str, Any]:
    if path.exists():
        config = load_json(path)
    else:
        config = default_config()
        save_json_atomic(path, config)
    config.setdefault("providers", DEFAULT_PROVIDERS)
    config.setdefault("china_reference", DEFAULT_CHINA_REFERENCE)
    config.setdefault("watches", [])
    return config


def add_or_update_watch(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any] | None:
    name = args.add or args.watch
    if not name:
        return None
    key = watch_key(name)
    for watch in config.get("watches", []):
        if watch.get("key") == key:
            target = args.target_price
            if target is not None:
                watch["target_price_jpy"] = target
                if int(watch.get("min_price_jpy", 0)) <= 500:
                    watch["min_price_jpy"] = max(500, int(target * 0.35))
            if args.min_price is not None:
                watch["min_price_jpy"] = args.min_price
            if args.max_price is not None:
                watch["max_price_jpy"] = args.max_price
            if args.no_alert_first_seen:
                watch["alert_first_seen"] = False
            watch.setdefault("exclude_terms", DEFAULT_RISKY_TERMS)
            watch.setdefault("accessory_terms", DEFAULT_ACCESSORY_TERMS)
            watch.setdefault("allow_accessory", bool(args.allow_accessory))
            return watch

    defaults = config.get("default_watch", {})
    min_price = args.min_price or defaults.get("min_price_jpy")
    if min_price is None and args.target_price:
        min_price = max(500, int(args.target_price * 0.35))

    watch = {
        "key": key,
        "name": name.strip(),
        "condition": args.condition or defaults.get("condition", "all"),
        "target_price_jpy": args.target_price,
        "min_price_jpy": min_price if min_price is not None else 500,
        "max_price_jpy": args.max_price or defaults.get("max_price_jpy", 2_000_000),
        "drop_jpy": args.drop_jpy or defaults.get("drop_jpy", 1000),
        "drop_percent": args.drop_percent or defaults.get("drop_percent", 5.0),
        "alert_first_seen": not args.no_alert_first_seen,
        "exclude_terms": DEFAULT_RISKY_TERMS,
        "accessory_terms": DEFAULT_ACCESSORY_TERMS,
        "allow_risky": bool(args.allow_risky),
        "allow_accessory": bool(args.allow_accessory),
        "created_at": local_iso(),
    }
    if args.include:
        watch["include_terms"] = [item.strip().lower() for item in args.include.split(",") if item.strip()]
    if args.exclude:
        watch["exclude_terms"] = [item.strip().lower() for item in args.exclude.split(",") if item.strip()]
    config.setdefault("watches", []).append(watch)
    return watch


def normalize_watch(watch: dict[str, Any]) -> None:
    watch.setdefault("condition", "all")
    watch.setdefault("exclude_terms", DEFAULT_RISKY_TERMS)
    watch.setdefault("accessory_terms", DEFAULT_ACCESSORY_TERMS)
    watch.setdefault("allow_risky", False)
    watch.setdefault("allow_accessory", False)
    target = watch.get("target_price_jpy")
    if isinstance(target, int) and int(watch.get("min_price_jpy", 0)) <= 500:
        watch["min_price_jpy"] = max(500, int(target * 0.35))
    watch.setdefault("min_price_jpy", 500)
    watch.setdefault("max_price_jpy", 2_000_000)
    watch.setdefault("drop_jpy", 1000)
    watch.setdefault("drop_percent", 5.0)
    watch.setdefault("alert_first_seen", True)


def run_once(config_path: Path, args: argparse.Namespace) -> int:
    config = load_or_create_config(config_path)
    added = add_or_update_watch(config, args)
    for watch in config.get("watches", []):
        normalize_watch(watch)
    save_json_atomic(config_path, config)

    base_dir = config_path.parent
    state_path = resolve_path(base_dir, args.state, config.get("state_file", ".product_price_state.json"))
    log_path = resolve_path(base_dir, args.log, config.get("log_file", "product_price_log.csv"))
    report_path = resolve_path(base_dir, args.report, config.get("report_file", "product_price_report.md"))

    try:
        state = load_json(state_path)
    except FileNotFoundError:
        state = {"watches": {}}

    all_results: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []
    repeat_hours = float(config.get("monitor", {}).get("repeat_alert_hours", 12))

    for watch in config.get("watches", []):
        watch_results = [
            check_provider(watch, provider, config)
            for provider in enabled_providers(config, watch)
        ]
        attach_reference(watch_results, check_china_reference(watch, config))
        alerts.extend(evaluate_hits(watch, watch_results, state, repeat_hours))
        all_results.extend(watch_results)

    append_log(log_path, all_results)
    write_report(report_path, config, all_results)
    save_json_atomic(state_path, state)

    reference_printed: set[str] = set()
    for result in all_results:
        price = f"{result['price_jpy']:,} JPY" if isinstance(result.get("price_jpy"), int) else "-"
        marker = "BUY" if result.get("hit") else "..."
        error = f" ({result['error']})" if result.get("error") else ""
        reference = ""
        if result["watch_name"] not in reference_printed:
            reference_printed.add(result["watch_name"])
            reference_summary = format_reference_short(result)
            reference = f" | CN ref: {reference_summary}" if reference_summary else ""
        print(f"[{marker}] {result['watch_name']} / {result['provider']}: {price}{error}{reference}")

    if alerts:
        message = format_alert(alerts)
        print()
        print(message)
        for error in send_notifications(config, message):
            print(error, file=sys.stderr)

    print(f"\nReport: {report_path}")
    return 0


def list_watches(config_path: Path) -> int:
    config = load_or_create_config(config_path)
    watches = config.get("watches", [])
    if not watches:
        print("No watches configured.")
        return 0
    for index, watch in enumerate(watches, 1):
        target = watch.get("target_price_jpy")
        target_label = f"{target:,} JPY" if isinstance(target, int) else "auto baseline"
        print(f"{index}. {watch['name']} | {watch.get('condition', 'all')} | target: {target_label}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Monitor prices for any product name.")
    parser.add_argument("--config", default="product_monitor_config.json", help="Path to config JSON.")
    parser.add_argument("--env-file", default=None, help="Optional KEY=VALUE env file for notification secrets.")
    parser.add_argument("--add", help="Add a product watch by name.")
    parser.add_argument("--watch", help="Add the product if needed, then run checks.")
    parser.add_argument("--target-price", type=int, help="Alert when price is at or below this JPY value.")
    parser.add_argument("--min-price", type=int, help="Ignore prices below this JPY value.")
    parser.add_argument("--max-price", type=int, help="Ignore prices above this JPY value.")
    parser.add_argument("--condition", choices=["all", "new", "used"], help="Provider condition filter.")
    parser.add_argument("--include", help="Comma-separated terms that improve result matching.")
    parser.add_argument("--exclude", help="Comma-separated terms to reject from snippets.")
    parser.add_argument("--allow-risky", action="store_true", help="Allow junk/as-is/untested listings.")
    parser.add_argument("--allow-accessory", action="store_true", help="Allow accessory/cable/case listings.")
    parser.add_argument("--drop-jpy", type=int, help="Auto-baseline alert drop amount in JPY.")
    parser.add_argument("--drop-percent", type=float, help="Auto-baseline alert drop percentage.")
    parser.add_argument(
        "--no-alert-first-seen",
        action="store_true",
        help="Do not alert on the first observed price when using auto baseline.",
    )
    parser.add_argument("--once", action="store_true", help="Run one check and exit. This is the default.")
    parser.add_argument("--loop", action="store_true", help="Run continuously.")
    parser.add_argument("--interval", type=int, default=None, help="Seconds between checks in loop mode.")
    parser.add_argument("--list", action="store_true", help="List configured watches.")
    parser.add_argument("--test-notify", action="store_true", help="Send a test notification and exit.")
    parser.add_argument("--state", default=None, help="Override state file path.")
    parser.add_argument("--log", default=None, help="Override CSV log path.")
    parser.add_argument("--report", default=None, help="Override Markdown report path.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    load_notification_env(config_path, args.env_file)

    try:
        if args.list:
            return list_watches(config_path)

        if args.test_notify:
            config = load_or_create_config(config_path)
            errors = send_notifications(
                config,
                "Product price monitor test notification\n\n"
                f"Config: {config_path.name}\n"
                f"Time: {local_iso()}\n"
                "If you received this, alerts are wired correctly.",
            )
            if errors:
                print("\n".join(errors), file=sys.stderr)
                return 1
            print("Test notification sent.")
            return 0

        if not args.add and not args.watch and not load_or_create_config(config_path).get("watches"):
            try:
                entered = input("请输入要监视的商品名称: ").strip()
            except EOFError:
                entered = ""
            if not entered:
                print("No product name provided.", file=sys.stderr)
                return 2
            args.watch = entered
            args.loop = True

        if args.loop:
            config = load_or_create_config(config_path)
            interval = args.interval or int(config.get("monitor", {}).get("interval_seconds", 120))
            while True:
                exit_code = run_once(config_path, args)
                if exit_code:
                    return exit_code
                time.sleep(interval)

        return run_once(config_path, args)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
