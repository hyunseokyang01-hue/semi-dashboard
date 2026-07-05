"""
semi_news.py — 반도체 뉴스 헤드라인 수집 (Step A-2)
용도: run_semi.py에서 호출 → 헤드라인 반환 → build_semi.py로 전달
설계: crypto-dashboard/crypto_news.py와 동일 (Google News RSS, 무료·키 불필요)
"""
import requests
import urllib.parse
import datetime
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

# ── 매크로 추적 키워드 (대시보드 축 대응) ──────────────────
KEYWORDS = {
    "수출통제·미중": ["BIS export control semiconductor", "chip export ban China", "Nvidia China chip"],
    "대만·TSMC":    ["TSMC Arizona", "Taiwan strait semiconductor", "TSMC N2"],
    "메모리·HBM":   ["HBM4 memory", "DRAM price", "SK hynix HBM Micron"],
    "관세·정책":    ["Section 232 semiconductor tariff", "CHIPS Act", "Intel foundry government"],
}

LANGS = {
    "영어":   ("en-US", "US", "US:en"),
    "한국어": ("ko", "KR", "KR:ko"),
}

PER_QUERY = 3    # (항목·언어)당 최신 헤드라인 수
RECENT_DAYS = 7  # 최근 N일 이내 기사만
TIMEOUT = 10
HEADERS = {"User-Agent": "Mozilla/5.0"}


def _is_recent(pub_date_str, days=RECENT_DAYS):
    if not pub_date_str:
        return False
    try:
        pub = parsedate_to_datetime(pub_date_str)
    except (TypeError, ValueError):
        return False
    now = datetime.datetime.now(datetime.timezone.utc)
    return (now - pub).days < days


def _fetch_one(query, lang_cfg, limit=PER_QUERY):
    hl, gl, ceid = lang_cfg
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    items = []
    for item in root.findall(".//item"):
        pub = item.findtext("pubDate")
        if not _is_recent(pub):
            continue
        items.append({
            "title": item.findtext("title"),
            "link": item.findtext("link"),
            "pub": pub,
            "source": item.findtext("source"),
        })
        if len(items) >= limit:
            break
    return items


def fetch_macro_news(keywords=KEYWORDS, langs=LANGS):
    """매크로 헤드라인 — 대시보드 '주간 뉴스' 탭 하단 자동 수집 섹션용."""
    out = []
    seen = set()
    for category, words in keywords.items():
        query = " OR ".join(words)
        for lang_name, lang_cfg in langs.items():
            for art in _fetch_one(query, lang_cfg):
                if art["link"] in seen:
                    continue
                seen.add(art["link"])
                art["category"] = category
                art["lang"] = lang_name
                out.append(art)
    return out


def fetch_ticker_news(ticker, name=None, limit=3):
    """종목별 헤드라인 — 브리핑 카드용. 영어 뉴스만."""
    q = f'"{name}" stock' if name else f"{ticker} stock"
    return _fetch_one(q, LANGS["영어"], limit=limit)


if __name__ == "__main__":
    news = fetch_macro_news()
    print(f"=== 매크로 {len(news)}건 (최근 {RECENT_DAYS}일) ===")
    for n in news[:8]:
        print(f"[{n['category']}/{n['lang']}] {n['title']}")
    print("\n=== NVDA 종목 뉴스 ===")
    for n in fetch_ticker_news("NVDA", "NVIDIA"):
        print(f"- {n['title']}")
