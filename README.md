# Welda RAG Chatbot Prototype

LangChain LCEL 기반의 헬스케어 도메인 RAG 챗봇 프로토타입입니다. 혈당 관리 도메인 지식 베이스에서 사용자 질문에 맞는 정보를 검색해 응답을 생성합니다.

## Why This Project

대웅제약 디지털헬스AI연구소 LLM 엔지니어 포지션 면접 준비 과정에서, 웰다 도메인 (혈당 관리 기반 다이어트)을 가정한 RAG 시스템을 직접 설계 및 구현하기 위해 만들었습니다.

## Features

- LCEL 기반 RAG 파이프라인
- 사용자 프로필 기반 개인화 (Pydantic 검증)
- 멀티턴 대화 메모리 (sliding window, max 10턴)
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

## Tech Stack

- LangChain (LCEL)
- Anthropic Claude (Sonnet 4.6)
- Chroma (vector store)
- BGE-M3 / KURE-v1 (Korean embeddings, 비교 평가 예정)

## Status

개발 진행 중 (Block 3 완료: 사용자 프로필 개인화 + 대화 메모리 추가)

## Disclaimer

본 프로젝트는 LLM 엔지니어링 학습 및 면접 준비 목적의 프로토타입이며, 의료 자문 도구가 아닙니다.
