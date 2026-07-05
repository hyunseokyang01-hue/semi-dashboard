"""
semi_qual.py — 정성 섹션 자동 갱신 (Step A-3, 주간)
용도: Claude API(웹검색 포함)로 data.json의 정성 키를 갱신
  갱신 키: summary, scenarioProbs, hypothesis, cycleSignals,
           customChipSignal, intelScenario, topNews
  (정량 키 tickers/autoNews는 건드리지 않음 — build_semi.py 관할)

실행: run_semi.py 이후 실행 (data.json의 정량 데이터를 컨텍스트로 사용)
  python semi_qual.py

환경변수: ANTHROPIC_API_KEY (GitHub Secrets 또는 .env)
비용 참고: 주 1회 Opus 4.8 호출 + 웹검색 수 회 — 회당 수십 센트 수준.
프롬프트 캐싱은 주 1회 단발 호출(5분 TTL)이라 적용 실익 없음 → 미사용.
"""
import json
import os
import datetime

import anthropic

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE, "data.json")

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(BASE, ".env"))
except ImportError:
    pass

MODEL = "claude-opus-4-8"

QUAL_KEYS = ("summary", "scenarioProbs", "hypothesis", "cycleSignals",
             "customChipSignal", "intelScenario", "topNews")

# 대시보드의 작업가설 프레임 (template.html 종합 탭과 동일한 관점 유지용)
FRAME = """작업가설: '미국이 아시아에 빼앗긴 반도체 제조 패권을 회복하려 한다.' — 결론이 아니라 검증 대상.
6개 축: 미·중 수출통제 / 대만·TSMC / 한반도 메모리(HBM) / 유럽·러 / 동맹(관세·Chip4) / 핵심광물.
핵심 종목: INTC(리쇼어링 가설 핵심), NVDA, AMD, MU, TSM, AMAT/LRCX/ASML(장비), GFS, AMKR."""

SCHEMA_DESC = """{
  "summary": "이번 주 반도체 시황 3~4문장 요약 (한국어)",
  "scenarioProbs": {"Base": 45, "Bull": 20, "Bear": 25, "BlackSwan": 10},  // 정수, 합계 100
  "hypothesis": [  // 이번 주 가설 뒷받침/반박 신호 각각 1~3개 (새 정보만)
    {"dir": "up"|"down", "w": "강"|"중"|"약", "txt": "한 줄 신호", "tag": "실제"|"추정", "note": "부연", "isNew": true}
  ],
  "cycleSignals": [  // 사이클 선행지표 3개: HBM/메모리 가격, WFE/장비 수주, AI capex
    {"name": "지표명", "status": "red"|"amber"|"green", "summary": "현황 1~2문장", "tag": "실제"|"추정"}
  ],
  "customChipSignal": {"name": "자체칩(ASIC) 동향", "status": "red"|"amber"|"green", "summary": "...", "tag": "실제"|"추정"},
  "intelScenario": {"current": "Bull|Base|Bear|Breakup 중 현재 판단", "rationale": "근거 2~3문장", "keyTrigger": "이번 주 주목할 트리거 1개"},
  "topNews": [  // 이번 주 핵심 뉴스 3개
    {"headline": "제목(한국어)", "summary": "2~3문장 요약", "implication": "투자 시사점 1문장", "tag": "실제"|"추정"}
  ]
}"""


def build_prompt(data):
    """data.json의 정량 데이터(티커 등락)를 컨텍스트로 프롬프트 구성."""
    today = datetime.date.today().isoformat()
    lines = []
    for b in data.get("tickers", []):
        d7 = f"{b['d7']:+.1f}%" if b.get("d7") is not None else "?"
        d30 = f"{b['d30']:+.1f}%" if b.get("d30") is not None else "?"
        lines.append(f"- {b['ticker']}: ${b['price']} (7D {d7}, 30D {d30})")
    quant = "\n".join(lines) if lines else "(정량 데이터 없음)"

    return f"""오늘은 {today}입니다. 당신은 반도체 산업 투자 분석가입니다.

{FRAME}

[이번 주 주가 스냅샷 — 로컬 수집 데이터]
{quant}

웹검색으로 최근 7일의 반도체·지정학 핵심 동향(수출통제, TSMC/대만, HBM/메모리 가격, Intel 파운드리 진척, 관세, 하이퍼스케일러 capex)을 확인한 뒤,
아래 스키마의 JSON **하나만** 출력하세요. 코드펜스·설명 없이 순수 JSON만 출력합니다.
모든 텍스트 값은 한국어. 확인된 사실은 tag "실제", 애널리스트 추정은 "추정"으로 구분하세요.
scenarioProbs 합계는 반드시 100.

{SCHEMA_DESC}"""


def extract_json(text):
    """응답에서 JSON 오브젝트만 추출 (코드펜스 등 방어적 처리)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("응답에서 JSON을 찾지 못함")
    return json.loads(text[start:end + 1])


def run():
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError("data.json 없음 — 먼저 run_semi.py를 실행하세요")
    with open(DATA_PATH, encoding="utf-8-sig") as f:
        data = json.load(f)

    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 환경변수 사용
    print(f"[semi_qual] {MODEL} 호출 (웹검색 최대 8회)...")

    with client.messages.stream(
        model=MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 8}],
        messages=[{"role": "user", "content": build_prompt(data)}],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "refusal":
        raise RuntimeError("모델이 요청을 거부함 (stop_reason=refusal)")

    text = "".join(b.text for b in response.content if b.type == "text")
    qual = extract_json(text)

    missing = [k for k in QUAL_KEYS if k not in qual]
    if missing:
        raise ValueError(f"응답 JSON에 필수 키 누락: {missing}")
    probs = qual["scenarioProbs"]
    total = sum(int(v) for v in probs.values())
    if total != 100:
        print(f"  [경고] 시나리오 확률 합계 {total} ≠ 100 — 그대로 저장")

    for k in QUAL_KEYS:
        data[k] = qual[k]
    data["qualUpdatedAt"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"저장: {DATA_PATH} (정성 키 {len(QUAL_KEYS)}개 갱신)")
    print(f"  사용량: in={response.usage.input_tokens} out={response.usage.output_tokens}")

    # HTML 재생성 (정량 데이터는 기존 값 그대로)
    from build_semi import build
    build(data.get("tickers", []), data.get("autoNews", []))
    print("[semi_qual] 완료")


if __name__ == "__main__":
    run()
