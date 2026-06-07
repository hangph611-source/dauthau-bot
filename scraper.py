"""
Đấu Thầu Y Tế Bot - Tự động tìm gói thầu thiết bị y tế
Các trang: muasamcong.gov.vn, dauthau.asia, dauthau.net
Thông báo qua Telegram
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import time
import hashlib
from datetime import datetime
import logging

# ============================================================
# CẤU HÌNH - Điền thông tin của bạn vào đây
# ============================================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8975462967:AAHTXDyOZXpDfFDK9Elh_byI0ZIpEailwk")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "767989979")

# Từ khóa tìm kiếm (có thể thêm/bớt)
KEYWORDS = [
    "thiết bị y tế",
    "vật lý trị liệu",
    "phục hồi chức năng",
    "thận nhân tạo",
    "siêu âm điều trị",
    "máy điện trị liệu",
    "thiết bị phcn",
]

# File lưu các gói thầu đã thông báo (tránh spam)
SEEN_FILE = "seen_tenders.json"
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("scraper.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
}


# ─────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────

def send_telegram(message: str) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        return True
    except Exception as e:
        log.error(f"Telegram error: {e}")
        return False


def format_tender_message(tender: dict) -> str:
    icon = "🏥"
    lines = [
        f"{icon} <b>Gói thầu mới - Thiết bị Y tế</b>",
        f"",
        f"📋 <b>{tender.get('title', 'N/A')}</b>",
        f"🏛 Chủ đầu tư: {tender.get('investor', 'N/A')}",
        f"💰 Giá trị: {tender.get('value', 'N/A')}",
        f"📅 Hạn nộp: {tender.get('deadline', 'N/A')}",
        f"🌐 Nguồn: {tender.get('source', 'N/A')}",
        f"🔗 <a href=\"{tender.get('url', '#')}\">Xem chi tiết</a>",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────
# QUẢN LÝ DANH SÁCH ĐÃ THẤY
# ─────────────────────────────────────────────

def load_seen() -> set:
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen), f, ensure_ascii=False)


def make_id(tender: dict) -> str:
    raw = f"{tender.get('title','')}{tender.get('url','')}"
    return hashlib.md5(raw.encode()).hexdigest()


# ─────────────────────────────────────────────
# SCRAPER 1: muasamcong.gov.vn
# ─────────────────────────────────────────────

def scrape_muasamcong(keyword: str) -> list[dict]:
    results = []
    try:
        url = (
            "https://muasamcong.mpi.gov.vn/web/guest/package"
            f"?p_p_id=packagelistportlet_WAR_qlhsportlet"
            f"&searchValue={requests.utils.quote(keyword)}"
            f"&statusId=2"   # 2 = đang mời thầu
        )
        r = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")

        rows = soup.select("table.table tbody tr")
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 4:
                continue
            title_tag = cols[1].find("a")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            href  = title_tag.get("href", "")
            if href and not href.startswith("http"):
                href = "https://muasamcong.mpi.gov.vn" + href

            results.append({
                "title":    title,
                "investor": cols[2].get_text(strip=True) if len(cols) > 2 else "N/A",
                "value":    cols[3].get_text(strip=True) if len(cols) > 3 else "N/A",
                "deadline": cols[4].get_text(strip=True) if len(cols) > 4 else "N/A",
                "url":      href,
                "source":   "muasamcong.gov.vn",
            })
    except Exception as e:
        log.warning(f"[muasamcong] lỗi khi tìm '{keyword}': {e}")
    return results


# ─────────────────────────────────────────────
# SCRAPER 2: dauthau.asia
# ─────────────────────────────────────────────

def scrape_dauthau_asia(keyword: str) -> list[dict]:
    results = []
    try:
        url = f"https://dauthau.asia/tim-kiem?q={requests.utils.quote(keyword)}&status=open"
        r = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")

        # Cấu trúc thẻ có thể thay đổi theo thời gian - điều chỉnh selector nếu cần
        cards = soup.select(".tender-item, .result-item, article.post, .package-row")
        for card in cards:
            title_tag = card.find("a", class_=lambda c: c and "title" in c) or card.find("h3") or card.find("h2")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            href  = title_tag.get("href") or (title_tag.find("a") and title_tag.find("a").get("href")) or ""
            if href and not href.startswith("http"):
                href = "https://dauthau.asia" + href

            investor = ""
            inv_tag  = card.find(class_=lambda c: c and ("investor" in c or "chu-dau-tu" in c))
            if inv_tag:
                investor = inv_tag.get_text(strip=True)

            deadline = ""
            dl_tag   = card.find(class_=lambda c: c and ("deadline" in c or "han-nop" in c or "date" in c))
            if dl_tag:
                deadline = dl_tag.get_text(strip=True)

            results.append({
                "title":    title,
                "investor": investor or "N/A",
                "value":    "N/A",
                "deadline": deadline or "N/A",
                "url":      href,
                "source":   "dauthau.asia",
            })
    except Exception as e:
        log.warning(f"[dauthau.asia] lỗi khi tìm '{keyword}': {e}")
    return results


# ─────────────────────────────────────────────
# SCRAPER 3: dauthau.net
# ─────────────────────────────────────────────

def scrape_dauthau_net(keyword: str) -> list[dict]:
    results = []
    try:
        url = f"https://dauthau.net/search?keyword={requests.utils.quote(keyword)}&status=active"
        r = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")

        rows = soup.select(".bid-list .bid-item, table.tbl-bid tbody tr, .search-result-item")
        for row in rows:
            title_tag = row.find("a")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            href  = title_tag.get("href", "")
            if href and not href.startswith("http"):
                href = "https://dauthau.net" + href

            results.append({
                "title":    title,
                "investor": _extract_text(row, ["investor", "chu-dau-tu", "owner"]),
                "value":    _extract_text(row, ["value", "gia-tri", "price"]),
                "deadline": _extract_text(row, ["deadline", "han-nop", "date", "time"]),
                "url":      href,
                "source":   "dauthau.net",
            })
    except Exception as e:
        log.warning(f"[dauthau.net] lỗi khi tìm '{keyword}': {e}")
    return results


def _extract_text(tag, class_hints: list) -> str:
    """Tìm text trong thẻ con có class chứa một trong các từ gợi ý."""
    for hint in class_hints:
        el = tag.find(class_=lambda c: c and hint in c)
        if el:
            return el.get_text(strip=True)
    return "N/A"


# ─────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────

def run_once():
    log.info("═" * 50)
    log.info(f"Bắt đầu quét lúc {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    send_telegram(
        f"🤖 <b>Bot đang chạy...</b>\n"
        f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
        f"🔍 Đang quét {len(KEYWORDS)} từ khóa trên 3 trang đấu thầu..."
    )
    seen       = load_seen()
    new_count  = 0

    all_tenders = []
    for kw in KEYWORDS:
        log.info(f"  🔍 Từ khóa: '{kw}'")
        all_tenders += scrape_muasamcong(kw)
        time.sleep(1)
        all_tenders += scrape_dauthau_asia(kw)
        time.sleep(1)
        all_tenders += scrape_dauthau_net(kw)
        time.sleep(1)

    # Lọc trùng và thông báo cái mới
    for tender in all_tenders:
        tid = make_id(tender)
        if tid in seen:
            continue
        # Lọc thêm: title phải chứa ít nhất 1 từ khóa y tế
        if not any(kw.lower() in tender["title"].lower() for kw in KEYWORDS):
            continue
        msg = format_tender_message(tender)
        if send_telegram(msg):
            seen.add(tid)
            new_count += 1
            log.info(f"  ✅ Đã gửi: {tender['title'][:60]}...")
            time.sleep(0.5)   # tránh flood Telegram

    save_seen(seen)
    log.info(f"Hoàn thành: {new_count} gói thầu mới được gửi.")
    send_telegram(
        f"✅ <b>Quét xong!</b>\n"
        f"📊 Tìm thấy <b>{new_count}</b> gói thầu mới\n"
        f"{'🏥 Kiểm tra tin nhắn phía trên!' if new_count > 0 else '😴 Chưa có gói thầu mới, sẽ quét lại sau.'}"
    )


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--loop":
        # Chạy liên tục mỗi 6 tiếng
        while True:
            run_once()
            log.info("Nghỉ 6 tiếng... (Ctrl+C để dừng)")
            time.sleep(6 * 3600)
    else:
        run_once()
