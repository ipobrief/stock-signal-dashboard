import os
import json

# 두 페이지가 관심종목 파일 공유
WATCHLIST_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "watchlist.json"
)


def load_watchlist() -> list:
    if not os.path.exists(WATCHLIST_PATH):
        return []
    try:
        with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_watchlist(items: list):
    os.makedirs(os.path.dirname(WATCHLIST_PATH), exist_ok=True)
    with open(WATCHLIST_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def add_stock(stock_name: str, stock_code: str = None):
    items = load_watchlist()
    if any(it["stock_name"] == stock_name for it in items):
        return False
    items.append({"stock_name": stock_name, "stock_code": stock_code})
    save_watchlist(items)
    return True


def remove_stock(stock_name: str):
    items = load_watchlist()
    items = [it for it in items if it["stock_name"] != stock_name]
    save_watchlist(items)


def is_in_watchlist(stock_name: str) -> bool:
    return any(it["stock_name"] == stock_name for it in load_watchlist())
