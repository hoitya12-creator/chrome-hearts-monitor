import requests
import re
import json
import os

NAV_URL = "https://www.chromehearts.com/socks"
STATE_FILE = "state.json"
WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                  "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
}

EXCLUDE_SLUGS = {
    "locations", "magazine", "login", "cart", "terms", "privacy",
    "disclosure", "general", "contact", "checkout", "search",
}

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)

def send_discord(message):
    try:
        requests.post(WEBHOOK_URL, json={"content": message}, timeout=10)
    except Exception as e:
        print(f"웹훅 전송 실패: {e}")

def fetch(url):
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text

def extract_categories(html):
    pattern = re.compile(r'href="https://www\.chromehearts\.com/([a-z0-9\-]+)"')
    cats = set()
    for slug in pattern.findall(html):
        if slug in EXCLUDE_SLUGS:
            continue
        cats.add(f"https://www.chromehearts.com/{slug}")
    return cats

def extract_products(html):
    link_pattern = re.compile(
        r'href="(https://www\.chromehearts\.com/[a-z0-9\-]+/[a-z0-9\-]+/[A-Z0-9]+\.html)(?:\?[^"]*)?"'
    )
    matches = list(link_pattern.finditer(html))
    products = {}
    for i, m in enumerate(matches):
        url = m.group(1)
        if url in products:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else min(len(html), start + 2000)
        chunk = html[start:end]
        out_of_stock = "OUT OF STOCK" in chunk.upper()
        products[url] = {"out_of_stock": out_of_stock}
    return products

def check_categories(state):
    try:
        nav_html = fetch(NAV_URL)
    except Exception as e:
        print(f"내비게이션 페이지 요청 실패: {e}")
        return None

    current_cats = extract_categories(nav_html)
    prev_cats = set(state.get("nav_categories", []))
    is_first_run_nav = "nav_categories" not in state

    new_cats = current_cats - prev_cats
    if new_cats and not is_first_run_nav:
        lines = "\n".join(f"- {u}" for u in sorted(new_cats))
        send_discord(f"🆕 **새 카테고리 발견!**\n{lines}")

    state["nav_categories"] = sorted(current_cats)
    return current_cats

def check_products_in_category(url, state):
    try:
        html = fetch(url)
    except Exception as e:
        print(f"{url} 요청 실패: {e}")
        return

    products = state.setdefault("products", {})
    prev = products.get(url, {})
    is_first_run = url not in products

    current = extract_products(html)

    new_items = []
    restocked_items = []
    for purl, info in current.items():
        if purl not in prev:
            new_items.append(purl)
        else:
            was_oos = prev[purl].get("out_of_stock", False)
            if was_oos and not info["out_of_stock"]:
                restocked_items.append(purl)

    if not is_first_run:
        if new_items:
            lines = "\n".join(f"- {u}" for u in new_items)
            send_discord(f"🆕 **신상품 발견!**\n{url}\n{lines}")
        if restocked_items:
            lines = "\n".join(f"- {u}" for u in restocked_items)
            send_discord(f"♻️ **재입고 발견!**\n{url}\n{lines}")

    products[url] = current

def main():
    state = load_state()
    categories = check_categories(state)
    if categories:
        for url in categories:
            check_products_in_category(url, state)
    save_state(state)

if __name__ == "__main__":
    main()
