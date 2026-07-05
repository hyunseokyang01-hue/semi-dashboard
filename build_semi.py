"""
build_semi.py — data.json 갱신 + 대시보드 HTML 생성 (Step B)
용도: run_semi.py에서 Step A 결과를 받아 호출
설계: krx-automation/update_html.py와 동일 역할 (데이터 → HTML. 수집·발송 없음)

동작:
1. data.json이 있으면 읽어서 '정성 섹션' 키는 그대로 보존
   (summary, scenarioProbs, hypothesis, cycleSignals, customChipSignal, intelScenario, topNews
    → Claude API/수동으로 갱신하는 영역. 이 스크립트는 건드리지 않음)
2. 정량 키만 덮어씀: updatedAt, tickers(종목 브리핑), autoNews(RSS 헤드라인)
3. template.html의 /*__INLINE_DATA__*/ null 자리에 data.json을 인라인
   → semi_dashboard.html (이메일 첨부용 단일 파일. fetch 불필요)
"""
import json
import os
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE, "data.json")
TEMPLATE_PATH = os.path.join(BASE, "template.html")
OUT_PATH = os.path.join(BASE, "index.html")  # GitHub Pages 서빙 + 이메일 첨부 겸용

# 이 스크립트가 절대 덮어쓰지 않는 키 (정성 섹션 — 수동/Claude 갱신 영역)
QUALITATIVE_KEYS = ("summary", "scenarioProbs", "hypothesis",
                    "cycleSignals", "customChipSignal", "intelScenario", "topNews")


def load_existing():
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, encoding="utf-8-sig") as f:
            return json.load(f)
    return {}


def build(briefings, macro_news):
    data = load_existing()

    # 정량 키 갱신 (정성 키는 load_existing() 값 그대로 유지)
    data["updatedAt"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    data["tickers"] = briefings
    data["autoNews"] = macro_news

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"저장: {DATA_PATH}  (tickers {len(briefings)}종목 / autoNews {len(macro_news)}건)")

    # 템플릿에 데이터 인라인 → 단일 HTML
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        tpl = f.read()
    marker = "/*__INLINE_DATA__*/ null"
    if marker not in tpl:
        raise RuntimeError("template.html에 /*__INLINE_DATA__*/ null 마커가 없음 — 템플릿 확인 필요")
    html = tpl.replace(marker, json.dumps(data, ensure_ascii=False))

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"생성: {OUT_PATH}")

    kept = [k for k in QUALITATIVE_KEYS if k in data]
    print(f"정성 섹션 보존: {kept if kept else '없음(아직 미작성)'}")
    return OUT_PATH


if __name__ == "__main__":
    # 단독 실행: 기존 data.json만으로 HTML 재생성 (수집 없이)
    data = load_existing()
    build(data.get("tickers", []), data.get("autoNews", []))
