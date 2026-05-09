# Welda RAG Chatbot Prototype

LangChain LCEL 기반의 헬스케어 도메인 RAG 챗봇 프로토타입입니다. 혈당 관리 도메인 지식 베이스에서 사용자 질문에 맞는 정보를 검색해 응답을 생성합니다.

## Why This Project

대웅제약 디지털헬스AI연구소 LLM 엔지니어 포지션 면접 준비 과정에서, 웰다 도메인 (혈당 관리 기반 다이어트)을 가정한 RAG 시스템을 직접 설계 및 구현하기 위해 만들었습니다.

## Features

- LCEL 기반 RAG 파이프라인
- 사용자 프로필 기반 개인화 (Pydantic 검증)
- 멀티턴 대화 메모리 (sliding window, max 10턴)
- 토큰 단위 streaming 응답 출력
- LangSmith 자동 트레이싱 (단계별 입출력, 토큰 사용량, latency)
- 한국어 도메인 지식 베이스 (혈당 관리)
- CLI 데모 (프로필 입력, history/reset/profile 명령 지원)

## Architecture

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

`build_rag_chain()`은 retrieval, generation, 그리고 둘을 합친 full 체인을 모두 반환합니다. CLI streaming은 retrieval/generation 분리 호출을, 단순 invoke 사용처(테스트 등)는 full 체인을 사용합니다.

### Component Details

- **Embedding Model**: BAAI/bge-m3 (다국어, 한국어 retrieval에 적합)
- **Chunking**: RecursiveCharacterTextSplitter (chunk_size=500, overlap=50)
- **Vector Store**: Chroma (persistent local storage)
- **Retrieval**: top-k=3 cosine similarity
- **LLM**: Claude Sonnet 4.6 via Anthropic API
- **Orchestration**: LangChain LCEL (pipe operator chains)

### Design Decisions

- **왜 BGE-M3인가**: 다국어 모델 중 한국어 retrieval 성능이 검증된 모델. KURE-v1과의 정량 비교는 아래 Embedding Model Evaluation 섹션 참고.
- **왜 chunk_size=500인가**: 도메인 문서가 짧고 주제별로 구조화되어 있어, 작은 청크로도 의미 단위 보존 가능. 500이면 한국어로 약 300-400자 수준.
- **왜 LCEL인가**: 파이프 연산자 기반 선언적 구조로 체인 변경/디버깅이 용이. LangSmith 트레이싱과 자연 호환.

### Retrieval Optimization

초기 구현에서 `stream_with_sources` 헬퍼가 retriever를 2회 호출하는 비효율이 있었습니다 (소스 캡처용 1회 + 체인 내부 1회). 단순히 retrieval 결과를 입력 dict로 미리 주입하는 우회도 가능했지만, 그 경우 체인이 외부 호출자에게 의존하게 되어 자체 완결성이 깨집니다.

대신 `RunnablePassthrough.assign` 패턴으로 retrieval 결과(`retrieved_docs`, `context`, `sources`)를 체인 state에 누적시키고, 체인을 retrieval과 generation 두 단계로 분리하여 노출했습니다. retrieval은 단발 호출(`.invoke()`)에 최적화된 단계, generation은 토큰 단위 streaming에 최적화된 단계라는 점을 코드 구조로 드러냈습니다.

이 리팩터링으로 쿼리당 임베딩/벡터 검색이 1회로 감소하고 LangSmith trace에서도 retrieval과 generation이 독립된 root run으로 분리되어 관찰 가능합니다.

### Setup & Run

```bash
# 1. venv 활성화
source venv/bin/activate

# 2. 인덱스 빌드 (최초 1회)
python scripts/ingest.py

# 3. 챗봇 실행
python scripts/chat.py
# 사용자 프로필을 설정하시겠습니까? (y/n): y
# 나이(1-120): 32
# 성별 (1=male, 2=female, 3=other): 2
# ...
# >>> 아침에 흰쌀밥 먹어도 되나요?
# >>> history     (이전 대화 기록 보기)
# >>> profile     (현재 프로필 보기)
# >>> reset       (대화 메모리 초기화)
# >>> exit        (종료)

# 4. 테스트
pytest tests/
```

## Streaming Response

응답을 토큰 단위로 스트리밍합니다. LCEL 체인은 `.stream()` 메서드를 자동으로 제공하므로 별도 구현 없이 즉시 활용했습니다.

```python
for chunk in chain.stream({"question": q, "chat_history": h}):
    print(chunk, end="", flush=True)
```

`scripts/chat.py`는 위 패턴을 `stream_with_sources()` 헬퍼로 감싸 토큰을 흘려보낸 뒤 마지막에 검색된 소스 파일 목록을 함께 출력합니다.

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

## Tech Stack

- LangChain (LCEL)
- Anthropic Claude (Sonnet 4.6)
- Chroma (vector store)
- BGE-M3 (다국어 임베딩, KURE-v1과 비교 평가 후 채택)

## Status

개발 진행 중 (Block 5 Part 2 완료: BGE-M3 vs KURE-v1 정량 비교 평가, BGE-M3 유지 결정)

## Disclaimer

본 프로젝트는 LLM 엔지니어링 학습 및 면접 준비 목적의 프로토타입이며, 의료 자문 도구가 아닙니다.
