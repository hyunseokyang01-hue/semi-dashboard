"""
run_semi.py — 반도체 대시보드 오케스트레이터 (Step A → B → C)
설계: krx-automation/run_daily.py와 동일 패턴
  Step A: semi_fetch(시세·공매도) + semi_news(헤드라인) — 종목 실패는 1회 재시도 후 스킵
  Step B: build_semi(data.json 갱신 + HTML 생성)
  Step C: send_email_semi(이메일 발송) — --no-email 로 생략 가능

사용:
  python run_semi.py                → semi_fetch.TICKERS 전체
  python run_semi.py NVDA INTC MU  → 지정 티커만
  python run_semi.py --no-email    → 이메일 생략
"""
import sys
import time

from semi_fetch import TICKERS, fetch_one_briefing
from semi_news import fetch_macro_news, fetch_ticker_news


def _with_retry(fn, *args, label="", retries=1, wait=3):
    """krx-automation/run_daily.py의 _with_retry와 동일: 실패 시 1회 재시도 후 스킵."""
    last = None
    for attempt in range(retries + 1):
        try:
            return fn(*args), None
        except Exception as e:
            last = e
            if attempt < retries:
                print(f"  [재시도] {label} 실패({type(e).__name__}: {e}) → {wait}초 후 1회 재시도")
                time.sleep(wait)
            else:
                print(f"  [스킵] {label} 재시도 후에도 실패: {type(e).__name__}: {e}")
    return None, last


def run_all(tickers):
    failed = []
    briefings = []
    print(f"=== Step A: 종목 브리핑 수집 시작: {len(tickers)}종목 {tickers} ===")
    for i, t in enumerate(tickers, 1):
        print(f"\n[{i}/{len(tickers)}] {t}")
        b, err = _with_retry(fetch_one_briefing, t, label=t)
        if err is not None:
            failed.append((t, f"{type(err).__name__}: {err}"))
            continue
        # 종목 뉴스 (실패해도 브리핑은 유지)
        news, nerr = _with_retry(fetch_ticker_news, t, b["name"], label=f"{t} 뉴스")
        b["news"] = news or []
        briefings.append(b)
        print(f"  수집: {b['name']} ${b['price']} | 뉴스 {len(b['news'])}건")

    print(f"\n[매크로 뉴스]")
    macro, merr = _with_retry(fetch_macro_news, label="매크로 뉴스 RSS")
    if merr is not None:
        failed.append(("매크로뉴스", f"{type(merr).__name__}: {merr}"))
    macro = macro or []
    print(f"  수집: {len(macro)}건")

    print("\n=== 결과 요약 ===")
    print(f"종목 성공: {len(briefings)}/{len(tickers)}")
    if failed:
        print("실패 목록:")
        for who, why in failed:
            print(f"  - {who}: {why}")
    else:
        print("전부 성공")
    return briefings, macro, failed


if __name__ == "__main__":
    args = sys.argv[1:]
    no_email = "--no-email" in args
    arg_tickers = [a.upper() for a in args if not a.startswith("--")]
    tickers = arg_tickers if arg_tickers else TICKERS

    briefings, macro, failed = run_all(tickers)

    if briefings:
        print(f"\n=== Step B: HTML 갱신 시작 → {[b['ticker'] for b in briefings]} ===")
        from build_semi import build
        out_path = build(briefings, macro)
        print("=== Step B 완료 ===")

        if no_email:
            print("\n(--no-email) Step C 생략")
        else:
            try:
                from send_email_semi import send_semi_email
                print("\n=== Step C: 이메일 발송 시작 ===")
                send_semi_email(out_path)
                print("=== Step C 완료 ===")
            except Exception as e:
                print(f"!!! Step C 실패: {type(e).__name__}: {e} — 이메일 미발송 !!!")
    else:
        print("\n수집 성공 종목 없음 → HTML 갱신 건너뜀")
