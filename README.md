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

```
사용자 질문 + 프로필 + 대화기록
    ↓
[Retriever (Chroma + BGE-M3)]
    ↓ top-3 chunks
[Format Docs]
    ↓
[Prompt Template]
    ↓
[LLM (Claude Sonnet 4.6)]
    ↓
[Output Parser]
    ↓
응답 → 대화 메모리에 저장
```

### Component Details

- **Embedding Model**: BAAI/bge-m3 (다국어, 한국어 retrieval에 적합)
- **Chunking**: RecursiveCharacterTextSplitter (chunk_size=500, overlap=50)
- **Vector Store**: Chroma (persistent local storage)
- **Retrieval**: top-k=3 cosine similarity
- **LLM**: Claude Sonnet 4.6 via Anthropic API
- **Orchestration**: LangChain LCEL (pipe operator chains)

### Design Decisions

- **왜 BGE-M3인가**: 다국어 모델 중 한국어 retrieval 성능이 검증된 모델. (Block 5에서 KURE-v1과 비교 평가 예정)
- **왜 chunk_size=500인가**: 도메인 문서가 짧고 주제별로 구조화되어 있어, 작은 청크로도 의미 단위 보존 가능. 500이면 한국어로 약 300-400자 수준.
- **왜 LCEL인가**: 파이프 연산자 기반 선언적 구조로 체인 변경/디버깅이 용이. LangSmith 트레이싱과 자연 호환.

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

## Tech Stack

- LangChain (LCEL)
- Anthropic Claude (Sonnet 4.6)
- Chroma (vector store)
- BGE-M3 / KURE-v1 (Korean embeddings, 비교 평가 예정)

## Status

개발 진행 중 (Block 4 완료: streaming 출력 + LangSmith 트레이싱)

## Disclaimer

본 프로젝트는 LLM 엔지니어링 학습 및 면접 준비 목적의 프로토타입이며, 의료 자문 도구가 아닙니다.
