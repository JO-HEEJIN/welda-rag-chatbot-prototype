# Learning Log

면접 준비 과정에서 직접 부딪힌 버그와 해결 방법을 시간순으로 기록합니다. 각 항목은 증상 → 진단 → 근본 원인 → 해결 → 교훈 순서입니다.

---

## 2026-05-09 — Cypher 변수 binding이 세미콜론으로 끊긴 statement 사이에서 전달되지 않음

### 발생 위치
`scripts/init_graph.cypher` (Block 7 Part 1, Neo4j 도메인 그래프 초기화 스크립트)

### 증상

`MATCH (n) RETURN labels(n) AS label, count(*) AS count` 쿼리에서 라벨이 비어 있는 노드 `[]` 가 **13개**나 등장했습니다.

```
label, count
[], 13
["Food"], 10
["LifecycleStage"], 5
...
```

기대값: 라벨 없는 노드 0개.

### 진단 과정

1. 13이라는 숫자가 우연이 아닐 거라 보고, Cypher 스크립트에서 어떤 패턴이 13번 반복되는지 역추적했습니다.
2. 스크립트의 관계 생성 블록 2곳 (인슐린 저항성 사이클, 대사 지표 hub-and-spoke) 에서 변수가 등장하는 distinct 개수를 셌습니다.
   - Cycle 블록: `b1, h2, m3, e4, s5, s6, b7` = **7개**
   - Metabolic 블록: `mi_glucose, mha, mi_bp, mi_tg, mi_hdl, ao` = **6개**
   - 합계 7 + 6 = **13** → 관찰된 빈 라벨 카운트와 정확히 일치.

이 일치가 결정적 단서였습니다.

### 근본 원인

Cypher의 변수 scope는 **단일 statement 내부**로 제한됩니다. 세미콜론으로 statement를 끊는 순간 변수 binding이 모두 폐기됩니다.

원래 스크립트는 다음 패턴이었습니다.

```cypher
CREATE (b1:Behavior {name: "잘못된 생활 습관", stage: 1, ...});  // 여기서 b1 binding 종료
CREATE (h2:HormoneState {name: "인슐린 과잉 분비", stage: 2, ...}); // 여기서 h2 binding 종료
// ... 나머지 5개 노드 CREATE도 각각 세미콜론으로 끊김

CREATE
  (b1)-[:TRIGGERS]->(h2),  // <- 여기서 b1, h2는 이전 binding이 아니라 NEW 익명 변수
  (h2)-[:CAUSES]->(m3),
  ...
```

마지막 CREATE 블록에서 `b1`, `h2` 등은 직전 statement의 라벨 노드를 가리키는 것이 아니라, **이 statement 안에서 처음 등장하는 익명 변수** 로 해석됩니다. Cypher는 익명 변수의 노드를 자동 생성하므로 라벨도 속성도 없는 빈 노드 7개 + 6개 = 13개가 새로 만들어진 것입니다.

원래 7개의 라벨 노드는 그대로 존재하지만, 관계는 그 노드들이 아니라 빈 노드 13개 사이에 그려졌습니다. 결과적으로 의도한 사이클/허브 구조가 전혀 형성되지 않았습니다.

### 해결

관계 생성 statement를 모두 `MATCH ... CREATE` 패턴으로 통일했습니다. 노드 속성으로 매칭하므로 이전 statement의 변수 binding에 의존하지 않습니다.

```cypher
MATCH (b1:Behavior {stage: 1}), (h2:HormoneState {stage: 2})
CREATE (b1)-[:TRIGGERS]->(h2);

MATCH (mi:MetabolicIndicator {name: "고혈당"}),
      (mha:MetabolicHealthAbnormality {name: "대사 건강 이상"})
CREATE (mi)-[:INDICATES]->(mha);
```

대안으로 노드 생성과 관계 생성을 하나의 거대한 `CREATE` statement로 묶는 방법도 있지만(`CREATE (b1:Behavior {...}), (h2:HormoneState {...}), (b1)-[:TRIGGERS]->(h2), ...`), 노드 수가 늘어날수록 가독성이 빠르게 떨어지고 디버깅이 어려워집니다. `MATCH ... CREATE` 패턴은 한 줄 = 한 관계 라 idempotent 디버깅에 유리합니다.

### 교훈

1. **Cypher 변수 scope = 한 statement**: 세미콜론으로 끊은 순간 binding은 모두 사라집니다. SQL의 트랜잭션 변수와 다릅니다.
2. **익명 변수가 노드를 만든다**: `CREATE (a)-[:R]->(b)` 에서 a, b 가 정의되지 않은 변수면 새 노드 2개가 생성됩니다. 에러가 아니라 silent insertion이라 더 위험합니다.
3. **숫자 단서로 역추적**: 빈 노드 카운트가 "13"이라는 구체적 숫자였기 때문에 변수 개수 세기로 원인을 찾을 수 있었습니다. 추상적 증상(예: "관계가 이상해요")보다 정량 단서를 먼저 확인해야 합니다.

---

## 2026-05-09 — cypher-shell stdin 파이프라인에서 한국어 UTF-8이 U+FFFD로 깨짐

### 발생 위치
같은 `scripts/init_graph.cypher` 실행 단계. 위 변수 binding 버그를 잡은 직후 발생.

### 증상

수정된 스크립트를 다시 실행하니 노드 카운트는 정상이지만 관계 카운트가 기대값과 어긋났습니다.

| 관계 | 기대 | 실제 | 차이 |
|---|---|---|---|
| CONTAINS | 16 | **23** | +7 |
| INDICATES | 5 | **7** | +2 |
| MANIFESTS_AS | 4 | **6** | +2 |
| 나머지 | (각각 맞음) | (각각 맞음) | 0 |

특히 추가 11개 관계가 모두 한국어 이름 노드 (Nutrient `정제 탄수화물`, `복합 탄수화물`, MetabolicIndicator `고혈당` 등) 와 연결된 패턴이었습니다.

### 진단 과정

1. 중복 관계가 어떤 (food, nutrient) 쌍에서 발생하는지 그룹화 쿼리로 분석했습니다.
   ```cypher
   MATCH (f:Food)-[r:CONTAINS]->(n:Nutrient)
   RETURN f.name, n.name, count(r) ORDER BY count(r) DESC;
   ```
2. 결과: **7개의 Food** (apple, brown_rice, mixed_grain_rice, ramen, rice_cake, sweet_potato, white_rice) 가 모두 동일한 carb 영양소 노드에 대해 `count=2` 를 기록.
3. Nutrient 노드를 `n.name, n.type, count(n)` 로 그룹화하니 결과가 **4 row**, 한 row 의 `type=carb` 가 `count=2`. 기대는 5 row (정제 탄수화물, 복합 탄수화물 따로) 였습니다.
4. `elementId(n)` 로 직접 보니 carb 타입 Nutrient는 실제로 **2개의 독립 노드** 가 맞았습니다. 그런데 GROUP BY가 둘을 한 row로 합쳤다는 뜻은 **두 노드의 `n.name` 값이 동일하다**는 것이었습니다.
5. Python neo4j driver로 raw bytes를 직접 출력했습니다.

```python
for record in s.run("MATCH (n:Nutrient) RETURN n.name AS name").data():
    print(record["name"].encode("utf-8").hex())
```

출력:
```
efbfbdefbfbdefbfbdefbfbdefbfbdefbfbd20efbfbdefbfbd...
efbfbdefbfbdefbfbdefbfbdefbfbdefbfbd20efbfbdefbfbd...
```

`U+FFFD` (UTF-8 replacement character, `� = ef bf bd`) 가 모든 한국어 글자 자리에 들어가 있었습니다. 둘은 byte 단위로 완전히 동일했습니다.

소스 파일은 정상이었습니다 (`grep "정제 탄수화물" scripts/init_graph.cypher` 정상 출력).

### 근본 원인

`cat scripts/init_graph.cypher | docker exec -i welda-neo4j cypher-shell ...` 명령은 호스트 stdin을 컨테이너 stdin으로 그대로 파이프합니다. 이 stdin을 읽는 cypher-shell (JVM 기반) 의 기본 charset은 컨테이너의 `LANG` 환경변수를 따라갑니다.

컨테이너 locale을 확인하니:
```
LANG=
LC_CTYPE="POSIX"
```

`POSIX` locale은 ASCII-only로 해석합니다. JVM이 stdin을 ASCII 디코더로 읽으려 하니 모든 non-ASCII 바이트가 디코딩 실패 → `U+FFFD` 로 대체됐습니다.

`정제 탄수화물` 과 `복합 탄수화물` 의 한국어 글자 수가 같았기 때문에 (각각 6자) 두 문자열이 동일한 `U+FFFD * 6` 으로 변환되어 DB에 저장됐습니다. 이후 `MATCH (n:Nutrient {name: "정제 탄수화물"})` 도 같은 손상된 문자열로 변환되어 두 carb Nutrient 노드를 **둘 다** 매칭하게 됐고, `CREATE (f)-[:CONTAINS]->(n)` 가 매 food당 2번씩 실행됐습니다.

흥미로운 확인 단서: `docker exec` 으로 컨테이너 내부에서 직접 `head` 한 파일 내용은 정상이었습니다. 즉, **파일 자체는 멀쩡한데 cypher-shell 의 stdin 디코더만 망가진** 상황이었습니다.

### 해결

`docker exec` 호출 시 환경 변수를 명시했습니다.

```bash
docker exec \
  -e LANG=C.UTF-8 \
  -e LC_ALL=C.UTF-8 \
  -e JAVA_TOOL_OPTIONS="-Dfile.encoding=UTF-8" \
  welda-neo4j \
  cypher-shell -u neo4j -p weldapassword -f /tmp/init_graph.cypher
```

세 변수 중 결정적인 것은 `LANG=C.UTF-8` 와 `-Dfile.encoding=UTF-8`. 전자는 GNU/glibc locale system, 후자는 JVM file/stream 디코더에 동시에 UTF-8 을 강제합니다.

`cypher-shell -f /tmp/init_graph.cypher` 처럼 컨테이너 내부 파일 경로를 주면 stdin 파이프를 거치지 않아도 되고, JVM 이 파일을 직접 읽기 때문에 `-Dfile.encoding=UTF-8` 만으로 충분합니다. 안전을 위해 둘 다 명시했습니다.

재실행 결과 관계 카운트가 모두 기대값과 일치:
- CONTAINS 16, INDICATES 5, MANIFESTS_AS 4. ✓

### 교훈

1. **POSIX/C locale은 non-ASCII 데이터에 안전하지 않다**: Docker 컨테이너 기본 LANG이 비어있는 경우 한국어/중국어/일본어/이모지 등이 모두 손상됩니다. 한국어 데이터를 다루는 모든 JVM/Python/Node 컨테이너 호출은 `LANG=C.UTF-8` 을 명시하는 것이 안전합니다.
2. **문자가 깨졌는지 의심되면 hex로 봐야 한다**: 터미널 디스플레이는 `?????` 로 보여서 NFC/NFD 정규화 차이로 오해할 수도 있었습니다. raw bytes 비교가 절대적 단서입니다.
3. **MATCH는 silent하게 N개 매칭한다**: 의도가 1개 매칭이라면 `LIMIT 1` 또는 unique constraint 를 걸어 두는 것이 안전합니다. unique constraint 가 있으면 데이터 모순이 INSERT 단계에서 폭로돼 더 빨리 발견됩니다 (Block 7 Part 2 에서 `Food(name)`, `MetabolicIndicator(name)` 에 적용 예정).
4. **stdin 파이프 vs `-f` 파일 경로**: 양쪽 모두 인코딩 문제를 겪을 수 있지만, `-f` 는 JVM `file.encoding` 한 가지만 신경 쓰면 되고 stdin 파이프는 OS locale, 컨테이너 locale, JVM 인코딩의 교집합이라 변수가 더 많습니다. 가능하면 파일 경로 전달 방식을 우선합니다.

### 디버깅 흐름 요약 (이 한 가지 버그에 들인 시간 추적)

1. 카운트 불일치 발견 (~30초)
2. 그룹화 쿼리로 한 영양소에 2배 발생 패턴 식별 (~2분)
3. `elementId` 로 노드 자체는 distinct 임을 확인 (~1분)
4. Python driver hex 출력으로 `U+FFFD` 진단 (~2분)
5. 컨테이너 locale 확인 → 원인 확정 (~1분)
6. 환경 변수 적용 후 재실행 → 정상화 (~30초)

총 약 7분. 추측 없이 단계마다 측정 → 진단 → 다음 단계로 좁히는 방식이 결과적으로 빠른 길이었습니다.

---

## 2026-05-09 — AIMessageChunk.content가 web_search tool 활성화 시 list로 바뀜

### 발생 위치
`scripts/chat.py` 의 `stream_graph_response` (Block 6.5 에서 작성, Block 7 Part 3 통합 직후 실사용 시 발견).

### 증상

`흰쌀밥 먹어도 돼요?` 를 입력하면 응답 첫 청크가 한 번 정상 표시된 직후 다음 예외로 그래프가 죽었습니다.

```
[{'text': '드셔도 됩니다. 다만 혈당 스파이크를', 'type': 'text', 'index': 0}]Traceback (most recent call last):
  ...
  File "scripts/chat.py", line 105, in stream_graph_response
    full_response += chunk.content
TypeError: can only concatenate str (not "list") to str
```

토큰 누적 한 번 만에 `full_response += chunk.content` 에서 string 과 list 를 concat 하려다 실패했습니다. 첫 chunk의 raw repr 도 print 에 그대로 흘러나와 있었습니다.

### 진단

`AIMessageChunk.content` 는 LangChain의 일반 ChatAnthropic 호출에서는 `str` 이지만, **Anthropic server-side `web_search` tool 을 attach 한 LLM 에서는 block dict 의 list** 가 됩니다. 한 chunk 안에 `{"type": "text", "text": "..."}`, `{"type": "server_tool_use", ...}`, `{"type": "web_search_tool_result", ...}` 같은 여러 block 이 섞여 들어옵니다.

Block 6.5 의 streaming 코드는 ChatAnthropic 의 단일-content 가정을 그대로 두고 작성됐고, Block 7 Part 3 에서 fallback LLM 에 web_search tool 을 붙이면서 그 가정이 무너졌습니다. 단위 테스트는 `extract_text_from_response()` 같은 helper 를 모킹된 list-content 로 검증해 통과했지만, chat.py 의 streaming 경로는 사람이 실제로 돌려보기 전까지 누구도 list 분기를 거치지 않았습니다.

### 해결

`scripts/chat.py` 에 작은 helper 를 두고 streaming 분기에서 사용합니다.

```python
def _chunk_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return ""
```

`stream_graph_response` 안:

```python
if isinstance(chunk, AIMessageChunk):
    text = _chunk_text(chunk.content)
    if text:
        print(text, end="", flush=True)
        full_response += text
        streamed_any_tokens = True
```

`server_tool_use` 와 `web_search_tool_result` 같은 internal block 은 사용자 화면에 띄울 필요가 없으므로 자연스럽게 필터됩니다. 동일한 화면 처리 + 토큰 누적 동작을 web_search 켜진 응답에서도 그대로 받게 됐습니다.

### 교훈

1. **Tool-augmented LLM 의 streaming chunk 는 multi-block 이다**: ChatAnthropic 만 봤을 때의 "content == str" 가정은 server-side tool 을 붙이는 순간 깨집니다. 모킹 테스트 한 번으로 확실히 잡았어야 하는 회귀.
2. **Helper 가 있어도 streaming 경로에는 자동 적용되지 않는다**: Part 2 의 `extract_text_from_response()` 는 완성된 응답을 가정해 만들었습니다. streaming chunk 마다 동일한 변환을 자동으로 거치지 않으므로 호출자 측에서 한 번 더 흘려보내야 합니다.
3. **수동 시연이 단위 테스트를 대체할 수는 없지만, 단위 테스트가 수동 시연을 대체할 수도 없다**: 두 layer 의 가정이 어긋난 케이스가 이번처럼 streaming 경로에서 터집니다. 이번 사례 이후 LangGraph + tool-augmented streaming 통합 시에는 작은 e2e 스모크 (3~5 청크만 흘려보기) 를 단위 테스트에 추가하는 것이 합리적인 보강책입니다.

---

## 2026-05-09 — Fallback 응답이 ~1024 토큰에서 잘려 끝 문장이 사라짐

### 발생 위치
`src/graph_fallback.py` 의 `create_fallback_llm()` (Block 7 Part 2 에서 작성, Part 3 실 시연에서 발견).

### 증상

`두쫀쿠 먹어도 돼요?` 응답이 다음과 같이 마지막 문단 도중에 끊겼습니다.

```
**그래도 먹고 싶다면 — 이렇게 드십시오**

1. **단백질을 먼저 드십
```

이어서 `참고:` citation 줄은 정상 출력됐습니다. 즉, 응답 텍스트 자체가 잘렸고 sources / disclaimer 흐름은 정상이었습니다.

### 진단

`create_fallback_llm(max_tokens=1024)` 가 기본값이었습니다. 두쫀쿠 같은 web_search fallback 응답은 다음을 모두 포함하므로 토큰 사용이 큽니다:

- 정의/구성 (재료 분석)
- 영양 수치 (탄수/지방/단백질/칼로리)
- 혈당 영향 양면 분석
- 실천 권장 사항
- 강제 disclaimer

1024 max_tokens 는 단순한 한국어 응답 4~6 문단 정도에 적합하며, web_search citation 이 풍부한 longtail 응답에는 부족합니다.

### 해결

`max_tokens` 기본값을 **4096** 으로 증가시켰습니다. Claude Sonnet 4.6 의 응답 토큰 한도 (8K) 이내, 평균 응답 비용 증가는 토큰 단위 청구라 실제 출력에 비례 (안 쓴 토큰은 청구 안 됨).

```python
def create_fallback_llm(
    model: str = "claude-sonnet-4-6",
    max_uses: int = 3,
    temperature: float = 0.3,
    max_tokens: int = 4096,  # was 1024
) -> ChatAnthropic:
    ...
```

### 교훈

1. **max_tokens 는 응답 풍부도 * fallback 케이스 * disclaimer 분량 의 합으로 잡아야 한다**: fallback 케이스는 그래프 hit 보다 응답이 통상 더 깁니다.
2. **응답 truncation 은 silent failure 다**: API 가 에러를 던지지 않고 정중하게 잘린 텍스트를 돌려줍니다. `finish_reason="max_tokens"` 같은 메타데이터를 응답 검증 단계에서 명시적으로 체크하는 게 안전합니다 (향후 보강).
3. **시연이 단위 테스트보다 길어야 한다**: 단위 테스트의 짧은 mock 응답은 1024 토큰에 잘 들어맞아 truncation 을 노출하지 않습니다. 실제 사용자 쿼리로 한 번 돌려봐야 잡힙니다.

---

## 2026-05-12 — chat_history 가 generate_or_fallback 프롬프트에 안 들어가 사용자 지시가 무시됨

### 발생 위치
`src/nodes.py::generate_or_fallback_node` + `src/graph_fallback.py::build_fallback_prompt` (Block 7 Part 3 에서 LCEL generate 노드를 GraphRAG 통합 노드로 교체할 때 발생한 회귀).

### 증상

긴 멀티턴 대화 중 사용자가 다음과 같이 명시적으로 지시했습니다.

> 사용자: "GL과 GI가 뭐야? 너 왜 어렵게 말해? 앞으로 이런 단어 쓰지마"
> 코치: "앞으로는 이 두 단어 대신 '혈당 올리는 속도', '실제 혈당 영향' 이런 표현으로 설명해 드리겠습니다." (좋은 답변)

그러나 직후 턴부터 코치가 다시 GI 라는 용어를 그대로 사용했고, 사용자가 항의하자 다음과 같이 답했습니다.

> 코치: "이전 대화 내역이 이 시스템에는 전달되지 않아, 어떤 맥락에서 GI 용어를 쓰지 말라고 하셨는지 확인이 어렵습니다."

LLM hallucination 이 아니라 실제로 prompt 에 chat_history 가 없었다는 자백입니다.

### 진단

`generate_or_fallback_node` 의 prompt 빌더 호출:

```python
prompt = build_fallback_prompt(
    query=state["user_question"],
    user_profile=user_profile_str,
    lifecycle_context=lifecycle_context,
    graph_context=combined_context,
)
```

`chat_history` 가 전달되지 않습니다. 그리고 `build_fallback_prompt` 의 시그니처에 `chat_history` 파라미터 자체가 없습니다.

비교용으로 `medical_disclaimer_node` 는 `format_chat_history(history)` 를 거쳐 prompt 에 정상 주입합니다. 같은 흐름이 generate_or_fallback 에만 빠진 회귀였습니다.

Block 3 에서 만든 `ConversationManager` → state["messages"] → `format_chat_history` → prompt 의 `{chat_history}` 자리표시자 경로가 Block 7 Part 3 에서 generate 노드를 GraphRAG 통합 노드로 갈아치울 때 단절됐습니다. 새 노드는 이전 노드와 다른 prompt 빌더(`build_fallback_prompt`)를 쓰는데 이 빌더에 chat_history 자리표시자가 처음부터 없었습니다.

### 옵션 검토

세 가지 해결안을 비교했습니다.

**옵션 1 — chat_history 만 prompt 에 단순 주입**
- 변경 최소, medical_disclaimer 와 일관
- 단점: LLM 이 매 턴마다 chat_history 에서 사용자 constraint("GI 쓰지마") 를 재추론. 대화가 길어지거나 constraint 가 묻히면 놓침. 옵션 3 권장으로 처음 제안했으나 사용자가 정확히 지적: "옵션 3 도 LLM 판단을 믿어야 해서 hallucination 이 생길 거다."

**옵션 2 — user_constraints state 필드로 추출/유지 (채택)**
- 별도 추출 노드가 사용자 발화에서 영구적 스타일/금지 규칙을 짧은 list 로 뽑아 state 에 누적
- 모든 LLM prompt 상단에 명시적 `[사용자 규칙]` 섹션으로 박힘
- chat_history 도 함께 주입 (대화 reference 용)
- 장점: constraint 가 짧고 명시적이라 LLM 이 매 턴 정확히 따름
- 단점:
    1. 추출 false negative (암묵적 지시 못 잡음)
    2. 추출 false positive (일회성 요청을 영구로 잘못 잡음)
    3. constraint 충돌/stale (사용자가 마음 바꾸면 list 누적되면서 모순)
- MVP 는 단순 누적, 충돌 해결은 향후 보강

**옵션 3 — 옵션 1 + system instruction 한 줄 강조**
- 옵션 1 + "이전 대화에서 사용자가 명시한 선호도를 반드시 따르세요" 한 줄
- 코드 변경 최소이지만 결국 LLM judgment 의존

채택: 옵션 2 + chat_history 둘 다 주입. 역할 분리:
- chat_history → 대화 reference ("방금 추천한 메뉴 중에서" 같은 anaphora)
- user_constraints → 지속적 스타일/금지 규칙 압축본 (prompt 상단 강조)

### 해결 디자인

1. `AgentState.user_constraints: list[str]` 추가, `operator.add` reducer 로 누적.
2. `extract_user_constraints_node` 신규: 사용자 마지막 발화를 Haiku 4.5 에 넘겨 Pydantic structured output 으로 constraint list 추출. classify_intent 직후 위치, 모든 분기에서 작동.
3. `build_fallback_prompt` 와 medical_disclaimer prompt 둘 다 `chat_history` + `user_constraints` 두 인자 받도록 확장. 프롬프트 상단에 `[사용자가 명시한 규칙 — 반드시 따르세요]` 섹션.
4. `generate_or_fallback_node` 와 `medical_disclaimer_node` 가 state 에서 messages + user_constraints 추출해 prompt 빌더에 전달.

### 교훈

1. **공유 state 의 새 소비 노드는 자동으로 따라가지 않는다**: Block 3 에서 만든 ConversationManager → state["messages"] 경로가 정상 동작했음에도, Block 7 Part 3 에서 새 generate 노드는 이 state 를 prompt 에 주입하는 명시적 코드가 없으면 자동으로 활용되지 않습니다. 모듈을 추가할 때마다 기존 공유 state 의 모든 필드가 새 노드에서도 활용되는지 매번 검증해야 합니다.
2. **LLM 의 자백 메시지는 결정적 단서**: "이전 대화 내역이 이 시스템에 전달되지 않아" 같은 메타 발화는 hallucination 이 아닐 가능성이 높습니다. 코드 추적의 시작점으로 신뢰할 수 있습니다.
3. **이전 대화 + 사용자 규칙은 역할이 다르다**: chat_history 는 reference 유지에, user_constraints 는 스타일 강제에. 둘을 하나의 chat_history 로 합치면 constraint 가 묻혀 LLM 이 놓치기 쉽습니다. 분리 + 압축 + 강조가 효과적입니다.
4. **옵션 비교를 사용자와 함께 하면 더 좋은 디자인이 나온다**: 처음엔 옵션 3 (LLM judgment) 을 권장했지만 사용자가 "LLM 판단 의존이 위험" 지점을 지적해 옵션 2 (state-explicit) 로 결정. 시니어 시그널.
