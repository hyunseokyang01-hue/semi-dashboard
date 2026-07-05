"""
semi_fetch.py — 반도체 미국 종목 시세·공매도 지표 수집 (Step A)
용도: run_semi.py에서 호출 → 결과 반환 → build_semi.py로 전달
설계: krx-automation/step1_fetch.py와 동일 역할 (순수 수집 함수만. 저장·발송 없음)
     시세 소스는 crypto-dashboard에서 검증된 yfinance 사용.
실패 시 예외를 그대로 raise → 상위 오케스트레이터에서 재시도/스킵 판단

★ 브리핑할 티커는 아래 TICKERS에 적으면 됨 (KRX의 종목코드 입력에 해당)
"""
import datetime
import yfinance as yf

# ── 브리핑 대상 티커 (원하는 종목을 여기에 추가/삭제) ─────────
TICKERS = [
    "NVDA",   # NVIDIA — L1 컴퓨트
    "INTC",   # Intel — 파운드리·리쇼어링 가설 핵심
    "AMD",    # AMD
    "MU",     # Micron — 메모리/HBM
    "AVGO",   # Broadcom — ASIC·네트워킹
    "TSM",    # TSMC ADR
    "AMAT",   # Applied Materials — 장비
    "LRCX",   # Lam Research — 장비
    "ASML",   # ASML ADR — EUV
    "MRVL",   # Marvell
    "GFS",    # GlobalFoundries
    "AMKR",   # Amkor — OSAT
]


def _pct(series, n):
    """n 거래일 전 대비 변동률(%). 데이터 부족 시 None."""
    if len(series) <= n:
        return None
    prev = series.iloc[-1 - n]
    if prev == 0:
        return None
    return (series.iloc[-1] / prev - 1) * 100


def fetch_one_briefing(ticker):
    """한 종목 브리핑 데이터 수집.
    KRX 대응: 시세/등락(12009·12022 대응) + 공매도(31001 대응, yfinance 공시치).
    국민연금 등 한국 전용 지표는 제외(대상 아님)."""
    tk = yf.Ticker(ticker)
    h = tk.history(period="1y", auto_adjust=True)
    if h.empty:
        raise ValueError(f"{ticker}: 가격 이력 없음 (야후 응답 비어있음)")
    close = h["Close"]
    vol = h["Volume"]
    last_date = close.index[-1].strftime("%Y-%m-%d")
    last = float(close.iloc[-1])

    # 연초 대비 (YTD)
    this_year = close.index[-1].year
    ytd_series = close[close.index.year == this_year]
    ytd = (last / float(ytd_series.iloc[0]) - 1) * 100 if len(ytd_series) > 1 else None

    hi52 = float(close.max())
    off_high = (last / hi52 - 1) * 100 if hi52 else None

    vol_last = int(vol.iloc[-1]) if len(vol) else None
    vol_avg21 = float(vol.tail(21).mean()) if len(vol) >= 5 else None
    vol_ratio = (vol_last / vol_avg21 * 100) if (vol_last and vol_avg21) else None

    # 공매도 지표 — yfinance info는 필드 누락이 잦음 → 개별 try, 없으면 None
    short_pct_float = None
    short_ratio = None
    name = ticker
    try:
        info = tk.info
        name = info.get("shortName") or ticker
        spf = info.get("shortPercentOfFloat")
        short_pct_float = spf * 100 if spf is not None else None
        short_ratio = info.get("shortRatio")
    except Exception:
        pass  # 시세만으로 브리핑 진행 (공매도는 '수집 불가' 표기)

    return {
        "ticker": ticker,
        "name": name,
        "date": last_date,
        "price": round(last, 2),
        "d1": _pct(close, 1),
        "d7": _pct(close, 5),      # 5거래일 ≈ 7일
        "d30": _pct(close, 21),    # 21거래일 ≈ 30일
        "ytd": ytd,
        "offHigh52w": off_high,
        "volume": vol_last,
        "volRatioPct": vol_ratio,          # 최근일 거래량 / 21일 평균 (%)
        "shortPctFloat": short_pct_float,  # 유통주식 대비 공매도 잔고 (%)
        "shortRatio": short_ratio,         # days-to-cover
    }


if __name__ == "__main__":
    import json
    b = fetch_one_briefing("NVDA")
    print(json.dumps(b, ensure_ascii=False, indent=2))
