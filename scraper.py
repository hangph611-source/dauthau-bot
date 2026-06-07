"""
Đấu Thầu & Chào Giá Y Tế Bot
Tìm: gói thầu + yêu cầu báo giá/chào giá thiết bị y tế
Nguồn: muasamcong.gov.vn, dauthau.asia, dauthau.net + websites bệnh viện TP.HCM
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
# CẤU HÌNH
# ============================================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8975462967:AAHTXDyOZXpDfFDK9Elh_byI0ZIpEailwk")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "767989979")

KEYWORDS = [
    "thiết bị y tế",
    "vật lý trị liệu",
    "phục hồi chức năng",
    "thận nhân tạo",
    "siêu âm điều trị",
    "máy điện trị liệu",
    "thiết bị phcn",
    "chào giá thiết bị",
    "báo giá thiết bị y tế",
    "mua sắm thiết bị y tế",
]

# Websites bệnh viện cần theo dõi mục chào giá/báo giá
HOSPITAL_SITES = [
    {
        "name": "BV Phú Nhuận",
        "url": "https://bvphunhuan.vn/thong-bao",
        "base": "https://bvphunhuan.vn",
    },
    {
        "name": "BV Nhân Dân Gia Định",
        "url": "https://bvndgiadinh.org.vn/thong-bao-moi-thau",
        "base": "https://bvndgiadinh.org.vn",
    },
    {
        "name": "BV Nhân Dân 115",
        "url": "https://www.bv115.org.vn/thong-bao-moi-thau",
        "base": "https://www.bv115.org.vn",
    },
    {
        "name": "BV Chợ Rẫy",
        "url": "https://choray.vn/tin-tuc/thong-bao-moi-thau",
        "base": "https://choray.vn",
    },
    {
        "name": "BV Thống Nhất",
        "url": "https://bvthongnhat.org.vn/thong-bao",
        "base": "https://bvthongnhat.org.vn",
    },
    {
        "name": "BV Bình Dân",
        "url": "https://binhdan.org.vn/thong-bao",
        "base": "https://binhdan.org.vn",
    },
]

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

# Từ khóa nhận dạng bài chào giá/báo giá trên website bệnh viện
QUOTE_KEYWORDS = [
    "chào giá", "báo giá", "yêu cầu báo giá", "mời chào giá",
    "chỉ định thầu", "mua sắm", "thiết bị y tế", "vật tư y tế",
    "vật lý trị liệu", "phục hồi chức năng", "thận nhân tạo",
]


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
    type_label = tender.get("type", "gói thầu")
    icon = "💬" if type_label == "chào giá" else "🏥"
    type_str = "YÊU CẦU CHÀO GIÁ" if type_label == "chào giá" else "GÓI THẦU MỚI"

    lines = [
        f"{icon} <b>{type_str} - Thiết bị Y tế</b>",
        f"",
        f"📋 <b>{tender.get('title', 'N/A')}</b>",
        f"🏛 Nguồn: {tender.get('investor', tender.get('source', 'N/A'))}",
    ]
    if tender.get("value") and tender.get("value") != "N/A":
        lines.append(f"💰 Giá trị: {tender.get('value')}")
    if tender.get("deadline") and tender.get("deadline") != "N/A":
        lines.append(f"📅 Hạn nộp: {tender.get('deadline')}")
    lines.append(f"🌐 Trang: {tender.get('source', 'N/A')}")
    lines.append(f"🔗 <a href=\"{tender.get('url', '#')}\">Xem chi tiết</a>")
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
# SCRAPER 1: muasamcong.gov.vn — đấu thầu
# ─────────────────────────────────────────────

def scrape_muasamcong(keyword: str) -> list[dict]:
    results = []
    try:
        url = (
            "https://muasamcong.mpi.gov.vn/web/guest/package"
            f"?p_p_id=packagelistportlet_WAR_qlhsportlet"
            f"&searchValue={requests.utils.quote(keyword)}"
            f"&statusId=2"
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
                "type":     "gói thầu",
            })
    except Exception as e:
        log.warning(f"[muasamcong] lỗi khi tìm '{keyword}': {e}")
    return results


# ─────────────────────────────────────────────
# SCRAPER 2: muasamcong.gov.vn — chào giá
# ─────────────────────────────────────────────

def scrape_muasamcong_chaogía(keyword: str) -> list[dict]:
    """Tìm yêu cầu báo giá/chào giá trên muasamcong (hình thức mua sắm trực tiếp)"""
    results = []
    try:
        # Hình thức: mua sắm trực tiếp / chỉ định thầu
        url = (
            "https://muasamcong.mpi.gov.vn/web/guest/package"
            f"?p_p_id=packagelistportlet_WAR_qlhsportlet"
            f"&searchValue={requests.utils.quote(keyword)}"
            f"&statusId=2"
            f"&selectionMethodId=4"   # 4 = mua sắm trực tiếp/chào giá
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
                "type":     "chào giá",
            })
    except Exception as e:
        log.warning(f"[muasamcong-chaogía] lỗi khi tìm '{keyword}': {e}")
    return results


# ─────────────────────────────────────────────
# SCRAPER 3: dauthau.asia
# ─────────────────────────────────────────────

def scrape_dauthau_asia(keyword: str) -> list[dict]:
    results = []
    try:
        url = f"https://dauthau.asia/tim-kiem?q={requests.utils.quote(keyword)}&status=open"
        r = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select(".tender-item, .result-item, article.post, .package-row")
        for card in cards:
            title_tag = card.find("a", class_=lambda c: c and "title" in c) or card.find("h3") or card.find("h2")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            href  = title_tag.get("href") or ""
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
                "type":     "gói thầu",
            })
    except Exception as e:
        log.warning(f"[dauthau.asia] lỗi khi tìm '{keyword}': {e}")
    return results


# ─────────────────────────────────────────────
# SCRAPER 4: dauthau.net
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
                "type":     "gói thầu",
            })
    except Exception as e:
        log.warning(f"[dauthau.net] lỗi khi tìm '{keyword}': {e}")
    return results


# ─────────────────────────────────────────────
# SCRAPER 5: Website bệnh viện — chào giá
# ─────────────────────────────────────────────

def scrape_hospital_site(hospital: dict) -> list[dict]:
    """Quét trang thông báo/mời thầu của từng bệnh viện"""
    results = []
    try:
        r = requests.get(hospital["url"], headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")

        # Tìm tất cả link trong trang
        links = soup.find_all("a", href=True)
        for link in links:
            title = link.get_text(strip=True)
            if len(title) < 10:
                continue
            # Chỉ lấy bài có từ khóa chào giá/thiết bị
            if not any(kw in title.lower() for kw in QUOTE_KEYWORDS):
                continue
            href = link["href"]
            if not href.startswith("http"):
                href = hospital["base"] + href
            results.append({
                "title":    title,
                "investor": hospital["name"],
                "value":    "N/A",
                "deadline": "N/A",
                "url":      href,
                "source":   hospital["name"],
                "type":     "chào giá",
            })
    except Exception as e:
        log.warning(f"[{hospital['name']}] lỗi: {e}")
    return results


def _extract_text(tag, class_hints: list) -> str:
    for hint in class_hints:
        el = tag.find(class_=lambda c: c and hint in c)
        if el:
            return el.get_text(strip=True)
    return "N/A"


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def run_once():
    log.info("═" * 50)
    log.info(f"Bắt đầu quét lúc {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    send_telegram(
        f"🤖 <b>Bot đang chạy...</b>\n"
        f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
        f"🔍 Quét đấu thầu + chào giá trên {3 + len(HOSPITAL_SITES)} nguồn..."
    )
    seen      = load_seen()
    new_count = 0

    all_tenders = []

    # 1. Các trang đấu thầu chính
    for kw in KEYWORDS:
        log.info(f"  🔍 Từ khóa: '{kw}'")
        all_tenders += scrape_muasamcong(kw)
        time.sleep(1)
        all_tenders += scrape_muasamcong_chaogía(kw)
        time.sleep(1)
        all_tenders += scrape_dauthau_asia(kw)
        time.sleep(1)
        all_tenders += scrape_dauthau_net(kw)
        time.sleep(1)

    # 2. Website từng bệnh viện
    for hospital in HOSPITAL_SITES:
        log.info(f"  🏥 Quét {hospital['name']}...")
        all_tenders += scrape_hospital_site(hospital)
        time.sleep(2)

    # Lọc trùng và gửi
    for tender in all_tenders:
        tid = make_id(tender)
        if tid in seen:
            continue
        title_lower = tender["title"].lower()
        if not any(kw.lower() in title_lower for kw in KEYWORDS + QUOTE_KEYWORDS):
            continue
        msg = format_tender_message(tender)
        if send_telegram(msg):
            seen.add(tid)
            new_count += 1
            log.info(f"  ✅ [{tender['type']}] {tender['title'][:60]}...")
            time.sleep(0.5)

    save_seen(seen)
    log.info(f"Hoàn thành: {new_count} mới.")
    send_telegram(
        f"✅ <b>Quét xong!</b>\n"
        f"📊 Tìm thấy <b>{new_count}</b> gói thầu/chào giá mới\n"
        f"{'🏥 Kiểm tra tin nhắn phía trên!' if new_count > 0 else '😴 Chưa có thông báo mới, sẽ quét lại sau.'}"
    )


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--loop":
        while True:
            run_once()
            log.info("Nghỉ 6 tiếng...")
            time.sleep(6 * 3600)
    else:
        run_once()
