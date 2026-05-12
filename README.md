# Welda RAG Chatbot Prototype

LangChain LCEL 기반의 헬스케어 도메인 RAG 챗봇 프로토타입입니다. 혈당 관리 도메인 지식 베이스에서 사용자 질문에 맞는 정보를 검색해 응답을 생성합니다.

## Why This Project

대웅제약 디지털헬스AI연구소 LLM 엔지니어 포지션 면접 준비 과정에서, 웰다 도메인 (혈당 관리 기반 다이어트)을 가정한 RAG 시스템을 직접 설계 및 구현하기 위해 만들었습니다.

## Features

- LCEL RAG 체인 (retrieval / generation 분리, 단일 retrieval 보장)
- LangGraph state machine: intent routing + 5단계 라이프사이클
- Neo4j 도메인 그래프 GraphRAG (multi-hop traversal, 43 노드/92 관계)
- Anthropic server-side `web_search` fallback (closed-world 한계 보완)
- 사용자 발화 규칙 영구화 (`extract_constraints` 노드, Haiku 4.5 + add reducer 누적)
- 의료 게이트: emergency 즉시 우회 + medical_advice 의료진 권유 강제
- 사용자 프로필 기반 개인화 (Pydantic 검증)
- 멀티턴 대화 메모리 (sliding window, max 10턴)
- 토큰 단위 streaming 응답 (`stream_mode=["messages", "values"]`)
- LangSmith 자동 트레이싱 (단계별 입출력, 토큰 사용량, latency)
- 한국어 도메인 지식 베이스 (혈당 관리 7개 문서, 한국 식단 그래프)
- CLI 데모 (프로필 입력, lifecycle stage 선택, history/reset/profile/stage 명령)

## Architecture

전체 시스템은 두 층으로 구성됩니다. **LangGraph state machine 이 바깥 wrapper** 로 의도 분류·라이프사이클 단계별 분기·사용자 규칙 누적을 담당하고, **LCEL RAG 체인이 그래프 노드 내부에서 retrieval 도구로 호출**됩니다. Block 7 부터 Neo4j 도메인 그래프와 Anthropic web_search 가 `generate_or_fallback` 노드에 통합됐고, Block 8 부터는 `classify_intent` 와 fan-out 사이에 `extract_constraints` 노드가 박혀 사용자가 명시한 표준 규칙을 매 턴 누적 후 모든 LLM 프롬프트 최상단에 주입합니다.

전체 흐름은 아래 GraphRAG Flow 섹션 다이어그램을 참고하시고, 이 절에서는 RAG 체인 내부와 컴포넌트 선택을 다룹니다.

### LCEL RAG Chain Internals

체인은 `RAGChainComponents`로 retrieval과 generation 두 단계로 분리되어 있습니다. retrieval은 단발 호출(`.invoke()`)에 적합하고 generation은 점진적 출력(`.stream()`)에 적합하다는 차이를 반영한 구조입니다.

```
사용자 질문 + 프로필 + 대화기록
    ↓
[Retrieval Chain]  (.invoke 단발 호출)
    ├ Retriever (Chroma + BGE-M3) — top-3 chunks
    ├ format_docs / extract_sources
    └ RunnablePassthrough.assign 으로 state 누적
    ↓
state dict { question, context, sources, chat_history, user_context, retrieved_docs }
    ↓
[Generation Chain]  (.stream 토큰 단위)
    ├ Prompt Template
    ├ LLM (Claude Sonnet 4.6)
    └ Output Parser
    ↓ 토큰 스트림
응답 → 대화 메모리에 저장
```

`build_rag_chain()`은 retrieval, generation, 그리고 둘을 합친 full 체인을 모두 반환합니다. LangGraph 의 `rag` 노드는 retrieval 만 호출해 state 에 context/sources 를 누적시키고, generate 노드(또는 generate_or_fallback)가 그 위에서 LLM 응답을 생성합니다.

### Component Details

- **Vector Store**: Chroma (local persistent, `chroma_db/`)
- **Embedding Model**: BAAI/bge-m3 (다국어, 한국어 retrieval 검증됨)
- **Chunking**: RecursiveCharacterTextSplitter (chunk_size=500, overlap=50)
- **Retrieval**: top-k=3 cosine similarity
- **Graph DB**: Neo4j 5.20 + APOC, 도메인 그래프 4개 서브그래프 (`docs/graph_schema.md`)
- **LLM**: Claude Sonnet 4.6 via Anthropic API, fallback LLM 에 server-side `web_search` tool attached
- **Orchestration**: LangChain LCEL (RAG 체인) + LangGraph (state machine, intent routing)
- **Memory**: 자체 `ConversationManager` (sliding window, in-memory)

### Design Decisions

- **왜 BGE-M3인가**: 다국어 모델 중 한국어 retrieval 성능이 검증된 모델. KURE-v1과의 정량 비교는 아래 Embedding Model Evaluation 섹션 참고.
- **왜 chunk_size=500인가**: 도메인 문서가 짧고 주제별로 구조화되어 있어, 작은 청크로도 의미 단위 보존 가능. 500이면 한국어로 약 300-400자 수준.
- **왜 LCEL인가**: 파이프 연산자 기반 선언적 구조로 체인 변경/디버깅이 용이. LangSmith 트레이싱과 자연 호환.

### Retrieval Optimization

초기 구현에서 `stream_with_sources` 헬퍼가 retriever를 2회 호출하는 비효율이 있었습니다 (소스 캡처용 1회 + 체인 내부 1회). 단순히 retrieval 결과를 입력 dict로 미리 주입하는 우회도 가능했지만, 그 경우 체인이 외부 호출자에게 의존하게 되어 자체 완결성이 깨집니다.

대신 `RunnablePassthrough.assign` 패턴으로 retrieval 결과(`retrieved_docs`, `context`, `sources`)를 체인 state에 누적시키고, 체인을 retrieval과 generation 두 단계로 분리하여 노출했습니다. retrieval은 단발 호출(`.invoke()`)에 최적화된 단계, generation은 토큰 단위 streaming에 최적화된 단계라는 점을 코드 구조로 드러냈습니다.

이 리팩터링으로 쿼리당 임베딩/벡터 검색이 1회로 감소하고 LangSmith trace에서도 retrieval과 generation이 독립된 root run으로 분리되어 관찰 가능합니다.

### Setup & Run

처음 셋업이거나 새 머신에서 복구하는 경우 아래 순서를 그대로 따라가십시오.

```bash
# 1. 코드 clone + venv + dependency 설치
git clone https://github.com/JO-HEEJIN/welda-rag-chatbot-prototype.git
cd welda-rag-chatbot-prototype
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. .env 파일 생성 (.env.example 참고)
cp .env.example .env
# 그 후 ANTHROPIC_API_KEY, LANGSMITH_API_KEY 를 본인 키로 채우십시오.
# NEO4J_* 변수는 아래 Docker 명령과 일치시키면 그대로 사용 가능합니다.
```

**필요 환경변수 (`.env`)**

```
ANTHROPIC_API_KEY=sk-ant-...
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_pt_...
LANGSMITH_PROJECT=welda-rag-chatbot
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=weldapassword
```

```bash
# 3. Neo4j 컨테이너 띄우기
#    APOC 플러그인은 현재 코드에서 직접 호출하지는 않지만, 향후 graph
#    import/export 와 advanced traversal 확장을 대비해 활성화해 둡니다.
docker run --name welda-neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/weldapassword \
  -e NEO4J_PLUGINS='["apoc"]' \
  -d neo4j:5.20

# 4. 도메인 그래프 데이터 로드 (init + normalize 순서로)
docker cp scripts/init_graph.cypher welda-neo4j:/tmp/init_graph.cypher && \
docker cp scripts/normalize_graph.cypher welda-neo4j:/tmp/normalize_graph.cypher && \
docker exec -e LANG=C.UTF-8 -e LC_ALL=C.UTF-8 -e JAVA_TOOL_OPTIONS="-Dfile.encoding=UTF-8" \
  welda-neo4j cypher-shell -u neo4j -p weldapassword -f /tmp/init_graph.cypher && \
docker exec -e LANG=C.UTF-8 -e LC_ALL=C.UTF-8 -e JAVA_TOOL_OPTIONS="-Dfile.encoding=UTF-8" \
  welda-neo4j cypher-shell -u neo4j -p weldapassword -f /tmp/normalize_graph.cypher
```

> **UTF-8 locale 변수는 필수입니다.** 빠뜨리면 컨테이너의 POSIX/ASCII locale 위에서 JVM이 한국어 입력을 `U+FFFD` 로 손상시켜 Nutrient 두 개가 같은 name으로 저장되고 관계 카운트가 부풀어 오릅니다. 자세한 진단 과정은 `learning_log.md` 두 번째 항목 참조.

데이터 검증 (선택, 총 43 노드 / 92 관계여야 정상):

```bash
docker exec -e LANG=C.UTF-8 welda-neo4j cypher-shell -u neo4j -p weldapassword \
  "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count ORDER BY label;"
docker exec -e LANG=C.UTF-8 welda-neo4j cypher-shell -u neo4j -p weldapassword \
  "MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS count ORDER BY count DESC;"
```

```bash
# 5. Chroma vector index 빌드 (BGE-M3 첫 다운로드 약 2.27GB)
python scripts/ingest.py

# 6. 챗봇 실행
python scripts/chat.py
# 사용자 프로필을 설정하시겠습니까? (y/n): y
# 나이(1-120): 32
# 성별 (1=male, 2=female, 3=other): 2
# ...
# 현재 어느 단계에 계신가요? (1-5): 2
# >>> 흰쌀밥 먹어도 돼요?         (graph hit, ~12초)
# >>> 두쫀쿠 먹어도 돼요?         (graph miss + web_search, ~26초)
# >>> 어지러워서 의식 잃을 것 같아요  (emergency, 즉시)
# >>> history / profile / stage / reset / exit

# 7. 테스트 (Neo4j 컨테이너 실행 중이어야 일부 통과)
pytest tests/
# 실제 LLM/web_search 호출까지 포함한 integration 테스트는 비용이 발생하므로
# 다음과 같이 별도 실행:
RUN_INTEGRATION=1 pytest tests/ -v
```

## Streaming Response (LangGraph)

LangGraph state machine으로 전환한 뒤에도 토큰 단위 스트리밍을 유지하기 위해 `stream_mode=["messages", "values"]` 듀얼 모드를 사용합니다. `messages` 스트림은 그래프 내부 LLM 노드(generate / medical_disclaimer)에서 발생하는 AIMessageChunk를 토큰 단위로 yield하고, `values` 스트림은 각 노드 종료 시점의 전체 state를 yield해 `sources` 와 (LLM을 거치지 않는 emergency 경로의) `final_answer` 를 캡처할 수 있게 합니다.

```python
from langchain_core.messages import AIMessageChunk

for stream_mode, payload in graph.stream(state, stream_mode=["messages", "values"]):
    if stream_mode == "messages":
        chunk, _metadata = payload
        if isinstance(chunk, AIMessageChunk) and chunk.content:
            print(chunk.content, end="", flush=True)
    elif stream_mode == "values":
        final_state = payload  # sources / emergency fallback final_answer 추출용
```

`scripts/chat.py`의 `stream_graph_response()` 헬퍼가 이 패턴을 구현합니다. 토큰을 스트리밍하지 않는 emergency 노드는 `final_state["final_answer"]` 를 fallback으로 한 번에 출력해 UX 일관성을 유지합니다.

## Observability (LangSmith Tracing)

LCEL 체인의 각 단계를 LangSmith로 자동 추적합니다. 환경변수 설정만으로 활성화되며, 다음 정보를 단계별로 기록합니다.

- Retriever input/output (검색된 청크 미리보기)
- Prompt template 변수 채우기
- Claude API 호출 (input/output 토큰, latency)
- 최종 응답 파싱

설정:

```bash
# .env에 추가
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_pt_...
LANGSMITH_PROJECT=welda-rag-chatbot
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
```

이 구조 덕분에 LLM 응답 품질 문제가 발생했을 때 retriever 결과 / prompt 채우기 / LLM 응답 중 어느 단계가 원인인지 즉시 식별할 수 있습니다.

## GraphRAG Flow (Block 7 + Block 8)

LangGraph state machine이 intent에 따라 분기하고, 식단 의도일 때 Neo4j 도메인 그래프 + Chroma vector RAG + (필요 시) Anthropic web_search 를 결합합니다. Block 8 부터는 모든 분기 앞에 `extract_constraints` 노드가 박혀 사용자가 명시한 규칙을 매 턴 누적합니다.

```
                       classify_intent  (rule-based)
                              |
                     extract_constraints  (Haiku 4.5, append to state["user_constraints"])
                              |
        +---------------------+-------------------+
        |                     |                   |
   emergency      medical_disclaimer       food_extraction
        |                     |                   |   (diet_advice / general 공통 수렴)
       END                   END             graph_lookup
                                                  |
                                                 rag
                                                  |
                                            generate_or_fallback
                                                  |
                                                 END
```

- `classify_intent` 는 룰 기반 키워드 분류 (emergency > medical > diet > general 우선순위).
- `extract_constraints` 는 매 사용자 발화에서 명시적 표준 규칙 (`"앞으로 X 쓰지마"` 등) 만 추출해 `state["user_constraints"]` 에 누적합니다. AgentState 의 `add` reducer 가 턴 간 누적을 보장하고, 모든 하위 LLM 프롬프트(`medical_disclaimer`, `generate_or_fallback`) 최상단에 `[사용자가 명시한 규칙 — 반드시 따르세요]` 섹션으로 렌더링됩니다.
- `diet_advice` 와 `general` intent 는 동일 fan-in 으로 `food_extraction` 에 수렴합니다 (conditional edge 가 두 값 모두 같은 노드를 가리킴).
- `generate_or_fallback` 내부의 LLM 에는 Anthropic server-side `web_search` tool 이 attach 되어 있어, 그래프/RAG 컨텍스트가 부족하다고 모델이 판단하면 자동으로 web 검색을 호출합니다 (closed-world 한계 보완).
- 응답에 disclaimer 가 누락되면 코드 레벨에서 강제 주입됩니다.

### Why GraphRAG

- **Multi-hop 추론**: vector RAG 단독으로는 "흰쌀밥 → 정제 탄수화물 → 급격한 혈당 스파이크 → SPIKE_CONTROL 단계에서 주의" 같은 인과 체인을 일관되게 만들기 어렵습니다. Neo4j traversal은 이 chain을 한 번의 쿼리로 가져옵니다.
- **Closed-world의 한계**: 도메인 그래프는 등록된 음식만 인식합니다. 신조어/트렌드 음식(두쫀쿠, 엽떡 등)은 web_search 로 보완합니다.
- **Heuristic-free routing**: 클라이언트에서 trend 신호를 휴리스틱으로 분류하지 않습니다. 그래프 컨텍스트와 사용자 질문을 함께 LLM 에게 넘기고 LLM 이 web_search 호출 여부를 자체 판단합니다. false-positive 가 줄고 모델 업그레이드 시 자동 개선됩니다.

### Latency Profile (실측)

| 시나리오 | 경로 | 측정 wall time |
|---|---|---|
| emergency | classify → emergency → END | 0.003s |
| diet_advice + graph hit | classify → food_ext → graph_lookup → rag → generate | ~12s |
| diet_advice + graph miss (web_search) | 위 흐름 + web_search 호출 | ~26s |
| medical_advice | classify → medical_disclaimer | ~7s |

응답에 자동 출처 표시:
- 그래프 hit: `graph:food:white_rice` 같은 식별자
- RAG: 마크다운 파일명 (e.g. `04_korean_foods_glucose.md`)
- web_search: citation URL (namu.wiki, foodpengu.in 등)

## User-Stated Constraints (Block 8)

시연 중 발생한 회귀를 직접 해결한 기능입니다. 사용자가 "앞으로 GI 라는 단어 쓰지마" 같은 표준 규칙을 한 번 지시하면, 이후 모든 턴에서 그 규칙이 LLM 프롬프트에 반드시 포함되어 모델이 규칙을 잊지 않도록 강제합니다.

### Problem

기존 메모리는 단순 sliding window (`ConversationManager`, max 10턴) 였습니다. 사용자 발화는 그대로 history 에 누적되지만, LLM 이 그 안에서 *어떤 발화가 표준 규칙인지* 알아서 식별·준수해야 하는 구조였습니다. 실제 시연에서 모델이 다음 턴에 규칙을 무시하는 회귀가 관찰되었습니다.

> 시연 사례: 1턴 "앞으로 GI 라는 단어 쓰지마" → 2턴 "흰쌀밥 먹어도 돼요?" → 응답에 GI 다시 등장.

### Design

별도 노드로 구조적 게이트를 만듭니다.

1. `extract_user_constraints_node` (`src/nodes.py`): Haiku 4.5 structured output 으로 사용자 발화에서 **표준 규칙만** 추출 (`"앞으로 X 하지마"`, `"항상 Y 형식으로"` 등). 일회성 요청 (`"이번엔 표로"`) 은 제외하도록 프롬프트로 지시.
2. `AgentState.user_constraints: Annotated[list[str], add]`: LangGraph `add` reducer 가 턴 간 누적을 자동 처리. 노드는 *추가* 만 반환하고 누적 책임은 framework 가 짐.
3. 모든 LLM 프롬프트(`MEDICAL_DISCLAIMER_PROMPT_TEMPLATE`, fallback prompt) 최상단에 `[사용자가 명시한 규칙 — 반드시 따르세요]` 섹션과 강조 instruction `"사용자가 한 번이라도 'X 쓰지마' 라고 했으면 X 를 다시 쓰지 마세요"` 박힘.

### Why an LLM extractor (not regex)

`"GI"`, `"GL"`, `"인슐린"` 등 도메인 용어 + 한국어 어순 변형 + 완곡 표현 (`"~ 안 썼으면 좋겠어"`) 까지 커버하려면 regex 가 폭발합니다. Haiku 4.5 호출 비용이 매 턴 약 $0.0001 수준이라 trade-off 가 명확합니다.

### Verification

`test_constraints_accumulate_across_turns` 한 테스트가 핵심 가치를 직접 측정합니다.

```python
# 1턴: 규칙 명시
result1 = graph.invoke({"user_question": "앞으로 GI 라는 단어 쓰지마. 알겠지?", ...})
constraints_after_t1 = result1["user_constraints"]
assert any("GI" in c for c in constraints_after_t1)

# 2턴: 직전 규칙을 state 에 보존한 채 새 질문
result2 = graph.invoke({
    "user_question": "흰쌀밥 먹어도 돼요?",
    "user_constraints": constraints_after_t1,  # 누적된 규칙 주입
    ...
})
assert "GI" not in result2["final_answer"]  # 회귀 재발 방지
```

### Known Limitations

`learning_log.md` 에 명시:

1. **False negative**: 암묵적 지시 (`"이거 너무 어려워"` 같은 톤 시그널) 는 추출되지 않습니다. 명시적 지시만 잡습니다.
2. **False positive**: 일회성 요청 (`"이번엔 표로 정리해줘"`) 을 영구 규칙으로 잘못 분류할 가능성. 프롬프트로 완화했지만 100% 보장하지 않습니다.
3. **충돌/stale**: 사용자가 시간이 지나며 규칙을 바꾸면 list 가 모순된 항목을 동시에 담을 수 있습니다. resolver 노드는 향후 작업으로 남겨뒀습니다.

### Cost

매 사용자 발화당 Haiku 4.5 호출 1회 (입력 ~150 tok, 출력 ~50 tok) ≈ $0.0001 미만. CLI 시연 빈도에서 무시 가능.

## Embedding Model Evaluation

도메인이 한국어(혈당 관리, 한국 식단)이라는 점에서 다국어 모델 BGE-M3와 한국어 특화 모델 KURE-v1을 비교 평가했습니다.

### 평가 방법

- 평가 데이터셋: 도메인 관련 한국어 쿼리 15개, 각 쿼리에 ground truth 관련 파일 라벨링 (primary-source 기준)
- 두 모델 모두 동일한 청킹/검색 파라미터로 인덱스 빌드 (chunk_size=500, overlap=50, top-k=3)
- 각 쿼리당 5개 retrieval metric + 평균 query latency 측정

### 결과

| Metric | BGE-M3 | KURE-v1 | Winner |
|---|---|---|---|
| Precision@3 | 0.8222 | 0.8222 | Tie |
| Recall@3 | 0.9333 | 0.9333 | Tie |
| MRR | 1.0000 | 1.0000 | Tie |
| Hit@1 | 1.0000 | 1.0000 | Tie |
| Hit@3 | 1.0000 | 1.0000 | Tie |
| Avg Latency (ms) | 66.67 | 18.11 | KURE-v1 |

15 쿼리 중 8 쿼리는 두 모델이 동일한 청크 3개를 반환했고, 5 쿼리는 다른 청크를 반환했지만 metric 단위로는 상쇄되어 동률입니다.

### 결과 해석

평가 결과 5개 품질 metrics에서 두 모델이 모두 ceiling에 도달했습니다 (MRR 1.0, Hit@1 1.0). 이는 두 모델의 능력이 정말 동일해서가 아니라, 평가 디자인의 다음 한계 때문으로 분석됩니다:

1. **평가셋 규모**: 15 쿼리는 통계적으로 모델 차이를 드러낼 power가 부족
2. **도메인 문서 크기**: 7 파일 25 청크의 후보 풀이 작아 실수 여지 적음
3. **쿼리-문서 키워드 직접 매칭**: 다수 쿼리가 ground truth 파일의 핵심 용어를 직접 포함

진정한 모델 차이를 측정하려면 더 큰 평가셋, 도메인 외 distractor 쿼리, paraphrase 처리가 어려운 쿼리 등이 필요합니다.

### 결정: BGE-M3 유지

다음 이유로 BGE-M3을 유지합니다:

1. 품질 동률 (ceiling effect 한계 내에서)
2. Latency 차이 49ms는 챗봇 전체 응답 시간(약 9초) 대비 0.5% 수준으로 사용자 인지 임계 미만
3. **다국어 확장성**: 웰다의 장기 비전이 "아시아 전반의 식습관 개선"이고 영어 의학 논문/가이드라인 직접 인덱싱 시나리오가 있는 만큼 다국어 모델이 전략적으로 유리

### Limitations

- 평가셋 15개로 ceiling effect 발생, 실제 모델 능력 차이 측정 불가
- Ground truth 라벨링이 단일 평가자 기준 (inter-annotator agreement 미측정)
- 두 모델 모두 사전학습 가중치만 사용, 도메인 fine-tuning 미적용

### Future Work

평가 신뢰도 향상을 위한 다음 단계:

- 평가셋 100개 이상 확장
- Distractor 쿼리 추가 (도메인 외 의학 토픽)
- Paraphrase 쿼리 추가 (같은 의도 다른 표현)
- LLM-as-judge로 retrieval relevance 정성 평가

### Reproduction

```bash
python evaluation/run_eval.py
```

상세 per-query 결과는 `evaluation/eval_results.json`에서 확인 가능합니다.

## Lifecycle State Machine

웰다의 5단계 사용자 라이프사이클을 LangGraph state 의 `lifecycle_stage` 필드로 명시적으로 추적합니다. `generate` 노드가 단계 메타데이터를 프롬프트에 주입해 같은 질문이라도 단계에 따라 다른 톤·중점 영역·금지 주제를 반영합니다. 그래프 전체 다이어그램은 위 GraphRAG Flow 섹션을 참고하십시오.

### Lifecycle Stages

1. **UNDERSTANDING** — 내 몸 이해하기 (웰다 시작 직후)
2. **SPIKE_CONTROL** — 혈당 스파이크 조절 (식후 급상승 줄이기)
3. **HUNGER_CONTROL** — 배고픔 조절 (가짜 배고픔 식별)
4. **FAT_BURN** — 체지방 연소 (대사 유연성 회복 후)
5. **MAINTENANCE** — 감량 유지 (요요 방지)

각 단계는 `description`, `focus_areas`, `tone_guideline`, `prohibited_topics` 메타데이터를 가집니다 (`src/lifecycle.py`).

### Why LangGraph

LCEL은 직선 파이프라인에 적합한 반면, 라이프사이클·의도별 라우팅은 분기와 조건부 흐름이 필요합니다. LangGraph state machine으로 사용자 stage·intent·대화 이력을 명시적으로 추적하고, 의료 도메인에 필수적인 응급/의학 자문 게이트를 conditional edges로 분리해 구조적으로 강제했습니다.

### Stage-Aware Response Example

같은 질문 "흰쌀밥 먹어도 돼요?"에 대해 단계별 응답이 달라집니다.

- **UNDERSTANDING**: "지금 당장 식단을 바꾸실 필요는 없습니다. 평소처럼 드시면서 CGM 데이터를 통해 혈당 곡선이 어떻게 그려지는지 살펴보십시오." (관찰·교육 톤)
- **SPIKE_CONTROL**: 식사 순서, 잡곡 비율, 식후 산책 등 즉시 적용 팁 3가지를 GI 수치와 함께 제시. (실용·구체 톤, Block 7 Part 3 실측 응답 기반)
- **FAT_BURN**: 인슐린 저감 시간, TRE 타이밍, 양/조합/타이밍 표 형식 정리. 기초 설명 생략. (실행·전략 톤)

`prohibited_topics` 도 작동합니다. 예를 들어 UNDERSTANDING 단계에서는 체지방 감량 압박이나 단식 권유가 응답에 등장하지 않도록 프롬프트가 차단합니다.

### Source Files

| 파일 | 역할 |
|---|---|
| `src/lifecycle.py` | `LifecycleStage` enum, `LifecycleMeta` dataclass, 5단계 메타데이터 |
| `src/agent_state.py` | LangGraph `AgentState` TypedDict (`messages` + `user_constraints` add reducer + Block 7 GraphRAG 필드) |
| `src/nodes.py` | classify_intent, **extract_user_constraints**, food_extraction, graph_lookup, rag, generate_or_fallback, emergency, medical_disclaimer |
| `src/graph.py` | `build_lifecycle_graph()` factory, conditional edges 정의 (Block 8 에서 `extract_constraints` 노드 추가) |
| `src/graph_db.py` | Neo4j 어댑터 (`WeldaGraphDB` context manager) |
| `src/graph_fallback.py` | `create_fallback_llm()` (web_search tool 활성화), `build_fallback_prompt` (chat_history + user_constraints 주입) |
| `src/rag_chain.py` | LCEL 체인 + `MEDICAL_DISCLAIMER_PROMPT_TEMPLATE` (`{user_constraints}` placeholder 포함) |
| `tests/test_lifecycle_graph.py` | intent 분류 + 라우팅 단위 테스트 |
| `tests/test_graph_db.py` | Neo4j lookup + fallback 헬퍼 + integration 테스트 |
| `tests/test_graphrag_integration.py` | food_extraction/graph_lookup + 그래프 end-to-end integration |
| `tests/test_user_constraints.py` | 규칙 추출 단위 5 + 누적·준수 integration 4 (`test_constraints_accumulate_across_turns` 핵심) |
| `scripts/simulate_block6.py` | 5단계 라이프사이클 시뮬레이션 (감독 출력) |
| `scripts/init_graph.cypher` / `scripts/normalize_graph.cypher` | Neo4j 도메인 그래프 데이터 |

## Tech Stack

- LangChain LCEL (retrieval / generation 체인)
- LangGraph (state machine, intent routing, 라이프사이클 단계)
- Anthropic Claude Sonnet 4.6 (Chat + server-side `web_search` tool)
- Chroma (local persistent vector store)
- BGE-M3 (다국어 임베딩, KURE-v1 비교 평가 후 채택 — 동률 + 다국어 확장성)
- Neo4j 5.20 (도메인 그래프, 43 노드 / 92 관계)
- LangSmith (자동 트레이싱)
- Pydantic v2 (사용자 프로필 검증)

## Status

개발 진행 중 (Block 8 완료: 사용자 발화 규칙 영구화 — `extract_constraints` 노드 + `user_constraints` add reducer + 모든 LLM 프롬프트 최상단 규칙 박스. 시연 회귀(`"앞으로 GI 쓰지마"` 미준수) 재발 방지 테스트 통과.)

## Disclaimer

본 프로젝트는 LLM 엔지니어링 학습 및 면접 준비 목적의 프로토타입이며, 의료 자문 도구가 아닙니다.
