"""
Đấu Thầu & Chào Giá Y Tế Bot - Phiên bản đầy đủ
Nguồn 1: muasamcong.gov.vn (đấu thầu + chào giá/mua sắm trực tiếp)
Nguồn 2: Website bệnh viện tỉnh từ Lâm Đồng → Cà Mau + TP.HCM
"""

import requests
from bs4 import BeautifulSoup
import json, os, time, hashlib
from datetime import datetime, timezone, timedelta
import logging

# ============================================================
# CẤU HÌNH
# ============================================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8975462967:AAHTXD_yOZXpDfFDK9Elh_byI0ZIpEailwk")
TELEGRAM_CHAT_IDS  = [
    os.environ.get("TELEGRAM_CHAT_ID", "767989979"),    # Chat riêng
    os.environ.get("TELEGRAM_GROUP_ID", "-5151512262"), # Group sale 1
    "-5117296331",                                       # Group sale 2
]

# Từ khóa tìm kiếm trên muasamcong (đấu thầu chính thức)
KEYWORDS = [
    "trang thiết bị y tế",
    "thiết bị y tế",
    "vật tư y tế",
    "máy móc thiết bị y tế",
    "thiết bị vật lý trị liệu",
    "thiết bị phục hồi chức năng",
    "thiết bị phcn",
    "máy thận nhân tạo",
    "máy siêu âm điều trị",
    "máy điện trị liệu",
    "máy kéo giãn cột sống",
    "máy sóng ngắn",
    "máy laser trị liệu",
    "nén ép trị liệu",
]

# Từ khóa lọc bài trên website bệnh viện (chào giá/báo giá)
# Bài phải chứa ít nhất 1 từ nhóm A VÀ 1 từ nhóm B
QUOTE_KEYWORDS_A = [
    "chào giá", "báo giá", "yêu cầu báo giá", "mời chào giá",
    "chỉ định thầu", "mời thầu", "thông báo mời thầu",
    "kết quả chỉ định thầu", "kế hoạch lựa chọn nhà thầu",
]

QUOTE_KEYWORDS_B = [
    "trang thiết bị y tế", "thiết bị y tế", "vật tư y tế",
    "thiết bị vật lý trị liệu", "phục hồi chức năng", "thiết bị phcn",
    "thận nhân tạo", "siêu âm điều trị", "điện trị liệu",
    "máy móc y tế", "thiết bị điều trị",
]

# Dùng chung cho filter cuối
QUOTE_KEYWORDS = QUOTE_KEYWORDS_A + QUOTE_KEYWORDS_B

# ─── DANH SÁCH BỆNH VIỆN (Lâm Đồng → Cà Mau + TP.HCM) ───────
HOSPITAL_SITES = [
    # ── TÂY NGUYÊN ──
    {"name": "BV ĐK tỉnh Lâm Đồng",        "url": "https://bvdakhoalamdong.vn/thong-bao",             "base": "https://bvdakhoalamdong.vn"},
    {"name": "BV ĐK vùng Tây Nguyên (Đắk Lắk)", "url": "https://benhvienvungtaynguyen.vn/thong-bao",  "base": "https://benhvienvungtaynguyen.vn"},
    {"name": "BV ĐK tỉnh Đắk Nông",         "url": "https://bvdkdaknong.vn/thong-bao",                "base": "https://bvdkdaknong.vn"},
    # ── ĐÔNG NAM BỘ ──
    {"name": "BV ĐK tỉnh Bình Phước",       "url": "https://bvdkbinhphuoc.vn/thong-bao",              "base": "https://bvdkbinhphuoc.vn"},
    {"name": "BV ĐK tỉnh Tây Ninh",         "url": "https://bvdktayninh.vn/thong-bao",                "base": "https://bvdktayninh.vn"},
    {"name": "BV ĐK tỉnh Bình Dương",       "url": "http://benhvienbinhduong.org.vn/thong-bao",       "base": "http://benhvienbinhduong.org.vn"},
    {"name": "BV ĐK Đồng Nai",              "url": "https://bvdkdongnai.gov.vn/thong-bao",            "base": "https://bvdkdongnai.gov.vn"},
    {"name": "BV Bà Rịa (BR-VT)",           "url": "https://bvbaria.vn/thong-bao",                    "base": "https://bvbaria.vn"},
    {"name": "BV ĐK tỉnh BR-VT",            "url": "https://bvdkbrvt.vn/thong-bao",                   "base": "https://bvdkbrvt.vn"},
    # ── TP.HCM ──
    {"name": "BV Chợ Rẫy",                  "url": "https://choray.vn/tin-tuc/thong-bao-moi-thau",    "base": "https://choray.vn"},
    {"name": "BV Nhân Dân Gia Định",        "url": "https://bvndgiadinh.org.vn/thong-bao-moi-thau",  "base": "https://bvndgiadinh.org.vn"},
    {"name": "BV Nhân Dân 115",             "url": "https://www.bv115.org.vn/thong-bao-moi-thau",    "base": "https://www.bv115.org.vn"},
    {"name": "BV Bình Dân",                 "url": "https://bvbinhdan.com.vn/thong-bao",              "base": "https://bvbinhdan.com.vn"},
    {"name": "BV Phú Nhuận",                "url": "https://bvphunhuan.vn/thong-bao",                 "base": "https://bvphunhuan.vn"},
    {"name": "BV Thống Nhất",               "url": "https://bvthongnhat.org.vn/thong-bao",            "base": "https://bvthongnhat.org.vn"},
    {"name": "BV Từ Dũ",                    "url": "https://tudu.com.vn/vn/tin-tuc/thong-bao",        "base": "https://tudu.com.vn"},
    {"name": "BV Nhi Đồng 1",              "url": "https://nhidong.org.vn/thong-bao",                 "base": "https://nhidong.org.vn"},
    {"name": "BV Nhi Đồng 2",              "url": "https://bvnhidong2.org.vn/thong-bao",              "base": "https://bvnhidong2.org.vn"},
    {"name": "BV ĐK Sài Gòn",              "url": "https://bvsaigon.gov.vn/thong-bao",               "base": "https://bvsaigon.gov.vn"},
    # ── ĐỒNG BẰNG SÔNG CỬU LONG ──
    {"name": "BV ĐK tỉnh Long An",          "url": "https://bvdkla.vn/thong-bao",                     "base": "https://bvdkla.vn"},
    {"name": "BV ĐK tỉnh Tiền Giang",       "url": "https://bvdktiengiang.vn/thong-bao",              "base": "https://bvdktiengiang.vn"},
    {"name": "BV ĐK tỉnh Bến Tre",          "url": "https://bvdkbentre.vn/thong-bao",                 "base": "https://bvdkbentre.vn"},
    {"name": "BV ĐK tỉnh Vĩnh Long",        "url": "https://bvdkvinhlong.vn/thong-bao",               "base": "https://bvdkvinhlong.vn"},
    {"name": "BV ĐK tỉnh Trà Vinh",         "url": "https://bvdktravinh.vn/thong-bao",                "base": "https://bvdktravinh.vn"},
    {"name": "BV ĐK TP Cần Thơ",            "url": "https://bvdkcantho.vn/thong-bao",                 "base": "https://bvdkcantho.vn"},
    {"name": "BV Đa khoa TW Cần Thơ",       "url": "https://bvdktwct.vn/thong-bao",                   "base": "https://bvdktwct.vn"},
    {"name": "BV ĐK tỉnh Hậu Giang",        "url": "https://bvdkhaugiang.vn/thong-bao",               "base": "https://bvdkhaugiang.vn"},
    {"name": "BV ĐK tỉnh Sóc Trăng",        "url": "https://bvdksoctrang.vn/thong-bao",               "base": "https://bvdksoctrang.vn"},
    {"name": "BV ĐK tỉnh Bạc Liêu",         "url": "https://bvdkbaclieu.vn/thong-bao",                "base": "https://bvdkbaclieu.vn"},
    {"name": "BV ĐK tỉnh Cà Mau",           "url": "https://bvdkcamau.vn/thong-bao",                  "base": "https://bvdkcamau.vn"},
    {"name": "BV ĐK tỉnh Đồng Tháp",        "url": "https://bvdkdonthap.vn/thong-bao",                "base": "https://bvdkdonthap.vn"},
    {"name": "BV ĐK tỉnh An Giang",         "url": "https://bvdkangiang.vn/thong-bao",                "base": "https://bvdkangiang.vn"},
    {"name": "BV ĐK tỉnh Kiên Giang",       "url": "https://bvdkkiengiang.vn/thong-bao",              "base": "https://bvdkkiengiang.vn"},
    # ── SỞ Y TẾ các tỉnh (thường đăng thông báo mời thầu tập trung) ──
    {"name": "Sở YT TP.HCM",               "url": "https://medinet.hochiminhcity.gov.vn/thong-bao-moi-thau", "base": "https://medinet.hochiminhcity.gov.vn"},
    {"name": "Sở YT Cần Thơ",              "url": "https://syt.cantho.gov.vn/thong-bao-moi-thau",    "base": "https://syt.cantho.gov.vn"},
    {"name": "Sở YT Lâm Đồng",             "url": "https://syt.lamdong.gov.vn/thong-bao-moi-thau",   "base": "https://syt.lamdong.gov.vn"},
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


# ─────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────

def send_telegram(message: str) -> bool:
    success = False
    for chat_id in TELEGRAM_CHAT_IDS:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            r = requests.post(url, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            }, timeout=15)
            r.raise_for_status()
            success = True
        except Exception as e:
            log.error(f"Telegram error [{chat_id}]: {e}")
    return success


def format_message(tender: dict) -> str:
    t = tender.get("type", "gói thầu")
    icon  = "💬" if t == "chào giá" else "🏥"
    label = "YÊU CẦU CHÀO GIÁ" if t == "chào giá" else "GÓI THẦU MỚI"
    lines = [
        f"{icon} <b>{label} - Thiết bị Y tế</b>",
        f"",
        f"📋 <b>{tender.get('title', 'N/A')}</b>",
        f"🏛 {tender.get('investor', tender.get('source', 'N/A'))}",
    ]
    if tender.get("value", "N/A") != "N/A":
        lines.append(f"💰 {tender['value']}")
    if tender.get("deadline", "N/A") != "N/A":
        lines.append(f"📅 Hạn: {tender['deadline']}")
    lines += [
        f"🌐 {tender.get('source','N/A')}",
        f"🔗 <a href=\"{tender.get('url','#')}\">Xem chi tiết</a>",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────
# SEEN
# ─────────────────────────────────────────────

def load_seen() -> set:
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except:
        return set()

def save_seen(seen: set):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen), f, ensure_ascii=False)

def make_id(t: dict) -> str:
    return hashlib.md5(f"{t.get('title','')}{t.get('url','')}".encode()).hexdigest()


# ─────────────────────────────────────────────
# SCRAPER: muasamcong.gov.vn
# ─────────────────────────────────────────────

def scrape_muasamcong(keyword: str, method_id: str = "2", tender_type: str = "gói thầu") -> list[dict]:
    results = []
    # method_id: 2=đang mời thầu, thêm selectionMethodId cho chào giá
    urls_to_try = [
        (
            f"https://muasamcong.mpi.gov.vn/web/guest/package"
            f"?p_p_id=packagelistportlet_WAR_qlhsportlet"
            f"&searchValue={requests.utils.quote(keyword)}"
            f"&statusId={method_id}"
        ),
    ]
    # Thêm url cho chào giá / mua sắm trực tiếp
    if tender_type == "chào giá":
        urls_to_try.append(
            f"https://muasamcong.mpi.gov.vn/web/guest/package"
            f"?p_p_id=packagelistportlet_WAR_qlhsportlet"
            f"&searchValue={requests.utils.quote(keyword)}"
            f"&statusId=2&selectionMethodId=4"
        )
    try:
        for url in urls_to_try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            soup = BeautifulSoup(r.text, "html.parser")
            for row in soup.select("table.table tbody tr"):
                cols = row.find_all("td")
                if len(cols) < 4:
                    continue
                tag = cols[1].find("a")
                if not tag:
                    continue
                title = tag.get_text(strip=True)
                href  = tag.get("href", "")
                if href and not href.startswith("http"):
                    href = "https://muasamcong.mpi.gov.vn" + href
                results.append({
                    "title":    title,
                    "investor": cols[2].get_text(strip=True) if len(cols) > 2 else "N/A",
                    "value":    cols[3].get_text(strip=True) if len(cols) > 3 else "N/A",
                    "deadline": cols[4].get_text(strip=True) if len(cols) > 4 else "N/A",
                    "url":      href,
                    "source":   "muasamcong.gov.vn",
                    "type":     tender_type,
                })
    except Exception as e:
        log.warning(f"[muasamcong/{tender_type}] '{keyword}': {e}")
    return results


# ─────────────────────────────────────────────
# SCRAPER: Website bệnh viện
# ─────────────────────────────────────────────

def scrape_hospital(hospital: dict) -> list[dict]:
    results = []
    try:
        r = requests.get(hospital["url"], headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")

        # Thử nhiều selector phổ biến của CMS bệnh viện VN
        candidates = soup.select(
            "a, .news-item a, .post-title a, .item-title a, "
            "article h2 a, article h3 a, .list-news a, "
            "ul.news li a, table tbody tr td a"
        )
        seen_hrefs = set()
        for link in candidates:
            title = link.get_text(strip=True)
            href  = link.get("href", "")
            if len(title) < 15 or href in seen_hrefs:
                continue
            title_lower = title.lower()
            has_action = any(kw in title_lower for kw in QUOTE_KEYWORDS_A)
            has_device = any(kw in title_lower for kw in QUOTE_KEYWORDS_B)
            if not (has_action and has_device):
                continue
            seen_hrefs.add(href)
            if href and not href.startswith("http"):
                href = hospital["base"].rstrip("/") + "/" + href.lstrip("/")
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
        log.warning(f"[{hospital['name']}] {e}")
    return results


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def run_once():
    VN_TZ = timezone(timedelta(hours=7))
    now = datetime.now(VN_TZ).strftime("%d/%m/%Y %H:%M")
    log.info("═" * 60)
    log.info(f"Bắt đầu quét lúc {now}")
    send_telegram(
        f"🤖 <b>Bot đang chạy...</b>\n"
        f"🕐 {now}\n"
        f"🔍 Quét muasamcong + {len(HOSPITAL_SITES)} bệnh viện/sở y tế\n"
        f"📍 Vùng: Lâm Đồng → Cà Mau + TP.HCM"
    )

    seen      = load_seen()
    new_count = 0
    all_items = []

    # 1. muasamcong — đấu thầu thông thường
    log.info("📋 Quét muasamcong (đấu thầu)...")
    for kw in KEYWORDS:
        all_items += scrape_muasamcong(kw, tender_type="gói thầu")
        time.sleep(0.8)

    # 2. muasamcong — chào giá / mua sắm trực tiếp
    log.info("💬 Quét muasamcong (chào giá)...")
    for kw in KEYWORDS:
        all_items += scrape_muasamcong(kw, tender_type="chào giá")
        time.sleep(0.8)

    # 3. Website từng bệnh viện
    for hospital in HOSPITAL_SITES:
        log.info(f"🏥 Quét {hospital['name']}...")
        all_items += scrape_hospital(hospital)
        time.sleep(1.5)

    # Gửi cái mới
    for item in all_items:
        tid = make_id(item)
        if tid in seen:
            continue
        title_lower = item["title"].lower()
        # Lọc: phải liên quan đến thiết bị y tế thực sự
        has_device_kw = any(kw in title_lower for kw in KEYWORDS + QUOTE_KEYWORDS_B)
        if not has_device_kw:
            continue
        if send_telegram(format_message(item)):
            seen.add(tid)
            new_count += 1
            log.info(f"  ✅ [{item['type']}] {item['title'][:60]}")
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
            time.sleep(6 * 3600)
    else:
        run_once()
