# Product Price Monitor

Monitor public Japanese shopping/search pages for product prices and send optional notifications. The script is standalone and uses only the Python standard library.

Default providers:

- PriceRank
- Yahoo Shopping
- Rakuten
- Mercari
- Yahoo Auctions
- HardOff NetMall
- Janpara

Optional reference source:

- Goofish / 闲鱼, shown as a China CNY reference only

The monitor reads public pages only. It does not log in, place orders, or store marketplace credentials.

## Quick Start

Create a local config on first run:

```bash
python3 product_price_monitor.py --watch "RTX 5080" --target-price 200000 --min-price 120000 --once
```

Or copy the example config:

```bash
cp product_monitor_config.example.json product_monitor_config.json
```

`product_monitor_config.json` is local runtime configuration and is ignored by git.

## Windows

监视一个商品一次：

```powershell
python .\product_price_monitor.py --watch "RTX 5080" --target-price 200000 --min-price 120000 --once
```

Loop:

```powershell
python .\product_price_monitor.py --watch "RTX 5080" --target-price 200000 --min-price 120000 --loop --interval 120
```

Wrapper:

```powershell
.\run-product-monitor.ps1 -Product "RTX 5080" -TargetPrice 200000 -MinPrice 120000 -Loop -IntervalSeconds 120
```

## Ubuntu

```bash
chmod +x ./run-product-monitor.sh
./run-product-monitor.sh --watch "RTX 5080" --target-price 200000 --min-price 120000 --loop --interval 120
```

Install a user-level systemd timer:

```bash
chmod +x ./install-product-monitor-systemd.sh
./install-product-monitor-systemd.sh --interval-minutes 2
```

The timer reads notification secrets from `~/.config/product-price-monitor.env`.

## Notifications

Copy the environment example:

```powershell
Copy-Item .\product_price_monitor.env.example .\.product_price_monitor.env
notepad .\.product_price_monitor.env
```

On Linux you can keep secrets outside the repository:

```bash
install -m 600 product_price_monitor.env.example ~/.config/product-price-monitor.env
editor ~/.config/product-price-monitor.env
```

Gmail SMTP requires an app password. A normal Google account password will fail:

```text
PRICE_SMTP_HOST=smtp.gmail.com
PRICE_SMTP_USERNAME=your@gmail.com
PRICE_SMTP_PASSWORD=your_gmail_app_password
PRICE_SMTP_FROM=your@gmail.com
PRICE_SMTP_TO=recipient@example.com
```

Test notification:

```powershell
python .\product_price_monitor.py --test-notify
```

## Auto Baseline

Without `--target-price`, the script records the first observed low price and alerts on later new lows:

- at least `1000 JPY` lower by default
- or at least `5%` lower by default

For expensive products, set `--min-price` to avoid page noise such as shipping fees, accessories, and unrelated search-result text:

```powershell
python .\product_price_monitor.py --watch "RTX 5080" --min-price 120000 --drop-percent 3 --drop-jpy 5000 --loop
```

Use `--no-alert-first-seen` if you only want alerts after a baseline has already been recorded.

## Filtering

The default filters reject high-risk terms such as `ジャンク`, `訳あり`, `動作未確認`, `箱のみ`, and `for parts`.
Accessory terms such as `cable`, `adapter`, `case`, `cover`, `ケーブル`, and `ケース` are also filtered by default.
Yahoo Auctions results use item links and `即決` / buy-now prices only; current bid prices are ignored because they are not direct purchase prices.
Enabled providers require a parsed item URL by default, so alerts should link to product pages instead of search pages.

Allow risky listings:

```powershell
python .\product_price_monitor.py --watch "RTX 4090" --allow-risky --once
```

Allow accessories:

```powershell
python .\product_price_monitor.py --watch "RTX 5080 cable" --allow-accessory --once
```

## China Reference

The report and alert messages can include a China-market reference from Goofish / 闲鱼. This is informational only:

- it is shown in CNY as `China Ref`
- it does not affect JPY target checks or alert decisions
- it uses public search data and never logs in or places orders

If Goofish rate limits or anti-bot checks block an unauthenticated request, the monitor records the reference error and continues checking the Japanese providers. You can optionally provide a browser cookie through an environment variable if the public request needs it; keep that value local and do not commit or share it:

```text
PRICE_GOOFISH_COOKIE=_m_h5_tk=...; other_public_cookie=...
```

For products whose China listing titles differ from the Japanese watch name, add watch-level fields in your local config:

```json
{
  "name": "Meta Quest 3",
  "china_reference_query": "Quest3",
  "china_reference_terms": ["quest", "3"],
  "china_reference_min_price_cny": 500,
  "china_reference_require_query_sequence": false
}
```

## Runtime Files

- `product_price_report.md`: latest report
- `product_price_log.csv`: historical checks
- `.product_price_state.json`: price baseline and alert state
- `product_monitor_config.json`: local watch configuration

These files are ignored by git so secrets, local watch lists, and generated reports do not get published accidentally.

## Checks

```bash
python3 -m py_compile product_price_monitor.py
python3 -m unittest discover -s tests
```
