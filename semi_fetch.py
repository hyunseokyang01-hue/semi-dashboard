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
    "ARM",    # Arm Holdings — 서버 CPU 구조변화(x86→ARM) 축
    "SMCI",   # Super Micro — AI·일반 서버 OEM (CPU 수요 최종 수요처)
    "DELL",   # Dell — 서버 OEM (일반 서버 교체 사이클)
    "VRT",    # Vertiv — 데이터센터 전력·냉각 (capex 사이클 확인용)
]

# ── AI·CPU 상관 추적 바스켓 (대시보드 08 탭용) ─────────────────
# 질문: AI 기술 발달(GPU 중심 투자)이 CPU 수요 증가로 이어지는가
GPU_BASKET = ["NVDA", "AVGO", "MRVL"]   # AI 가속기·ASIC 진영
CPU_BASKET = ["INTC", "AMD", "ARM"]     # CPU 진영


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


def fetch_ai_cpu_metrics():
    """AI·CPU 상관 정량 지표 (주간, 최근 6개월).
    - GPU/CPU 바스켓: 각 티커 종가를 첫 주=100으로 지수화 후 동일가중 평균
    - AMD/INTC 비율: x86 서버 점유율 이동 프록시 (가격 비율이라 기간 무관 비교 가능)
    실패 시 예외 raise → run_semi에서 재시도/스킵 (기존 aiCpu 값은 build가 보존)."""
    tickers = sorted(set(GPU_BASKET + CPU_BASKET))
    df = yf.download(tickers, period="6mo", interval="1wk",
                     auto_adjust=True, progress=False)["Close"]
    df = df.dropna(how="all").ffill().dropna()
    if df.empty or len(df) < 2:
        raise ValueError("AI·CPU 바스켓: 주간 종가 다운로드 실패/부족")
    idx = df / df.iloc[0] * 100
    gpu = idx[GPU_BASKET].mean(axis=1)
    cpu = idx[CPU_BASKET].mean(axis=1)
    ratio = df["AMD"] / df["INTC"]
    return {
        "dates": [d.strftime("%Y-%m-%d") for d in df.index],
        "gpuIdx": [round(float(v), 2) for v in gpu],
        "cpuIdx": [round(float(v), 2) for v in cpu],
        "amdIntcRatio": [round(float(v), 3) for v in ratio],
        "gpuBasket": GPU_BASKET,
        "cpuBasket": CPU_BASKET,
    }


if __name__ == "__main__":
    import json
    b = fetch_one_briefing("NVDA")
    print(json.dumps(b, ensure_ascii=False, indent=2))
    m = fetch_ai_cpu_metrics()
    print(json.dumps({k: (v[-3:] if isinstance(v, list) else v) for k, v in m.items()},
                     ensure_ascii=False, indent=2))
