# Welda Domain Graph Schema

Neo4j 5 위에 정의된 4개 서브그래프의 노드 라벨, 관계 타입, 속성 명세입니다. 모든 한국어 텍스트 속성은 UTF-8.

## Subgraph 1: Insulin Resistance Cycle

웰다 도메인 문서의 7단계 인슐린 저항성 피드백 사이클을 그래프로 표현합니다. 행동 → 호르몬 상태 → 대사 효과 → 에너지 상태 → 증상으로 이어지는 단방향 chain에 마지막 단계가 다시 1단계 행동을 강화하는 cycle edge가 붙습니다.

### Nodes

| Label | Properties |
|---|---|
| `:Behavior` | `name`, `stage`, `description` |
| `:HormoneState` | `name`, `stage`, `description` |
| `:MetabolicEffect` | `name`, `stage`, `description` |
| `:EnergyState` | `name`, `stage`, `description` |
| `:Symptom` | `name`, `stage`, `description` |

`stage` 는 1..7 정수로 사이클 내 위치를 표시합니다.

### Relationships

| Type | From | To | Semantics |
|---|---|---|---|
| `:TRIGGERS` | Behavior | HormoneState | 행동이 호르몬 분비를 유발 |
| `:CAUSES` | HormoneState | MetabolicEffect | 호르몬 상태가 대사 효과를 야기 |
| `:LEADS_TO` | MetabolicEffect | EnergyState | 대사 효과가 에너지 상태로 이어짐 |
| `:LEADS_TO` | EnergyState | Symptom | 에너지 상태가 증상으로 발현 |
| `:LEADS_TO` | Symptom | Behavior | 증상이 다음 행동으로 이어짐 |
| `:REINFORCES` | Behavior (stage=7) | Behavior (stage=1) | 보상성 과식 행동이 초기 잘못된 습관을 강화 (cycle close edge) |

### Counts

- 7 nodes, 7 relationships (6 forward edges + 1 REINFORCES back edge).

## Subgraph 2: Metabolic Health Indicators

대사 증후군 5대 지표(고혈당, 고혈압, 고지혈증, HDL 저하, 복부 비만) 와 종합 지표 `:MetabolicHealthAbnormality` 의 hub-and-spoke 구조입니다. 복부 비만이 다른 4개 지표로 manifest되는 관계도 함께 표현합니다.

### Nodes

| Label | Properties |
|---|---|
| `:MetabolicIndicator` | `name`, `normal_range`, `unit` |
| `:AbdominalObesity` | `name`, `criteria_male`, `criteria_female` |
| `:MetabolicHealthAbnormality` | `name`, `definition` |

### Relationships

| Type | From | To | Semantics |
|---|---|---|---|
| `:INDICATES` | MetabolicIndicator | MetabolicHealthAbnormality | 지표가 대사 건강 이상을 가리킴 |
| `:INDICATES` | AbdominalObesity | MetabolicHealthAbnormality | 복부 비만이 대사 건강 이상을 가리킴 |
| `:MANIFESTS_AS` | AbdominalObesity | MetabolicIndicator | 복부 비만이 다른 지표로 발현 |

### Counts

- 6 nodes (4 indicators + 1 abdominal obesity + 1 abnormality), 9 relationships (5 INDICATES + 4 MANIFESTS_AS).

## Subgraph 3: Food–Nutrient–Glucose Impact

식품, 영양소, GI 등급, 혈당 영향, 식이제한을 묶은 핵심 도메인 그래프. 한국 식단 위주로 10개 식품을 선정.

### Nodes

| Label | Properties |
|---|---|
| `:Food` | `name` (영어 snake_case), `display_name_ko` (한국어 표시명), `category` (rice/noodle/meat/fruit/tuber/vegetable/processed/legume) |
| `:Nutrient` | `name` (한국어), `type` (carb/protein/fat/fiber) |
| `:GIClass` | `level` (low/medium/high), `gi_range` ("<=55" / "56-69" / ">=70"), `display_name` (한국어), `description` (한국어) |
| `:GlucoseImpact` | `pattern` (sharp_spike/gradual_rise/minimal), `display_name` (한국어), `description` (한국어) |
| `:DietaryRestriction` | `name` (영어 snake_case), `display_name_ko` (한국어) |

Block 7 Part 1.5 정규화 이후 `Food.korean_name` 은 폐기되었고, 동일한 역할은 `display_name_ko` 가 담당합니다.

### Relationships

| Type | From | To | Semantics |
|---|---|---|---|
| `:CONTAINS` | Food | Nutrient | 식품이 영양소를 포함 |
| `:HAS_GI` | Food | GIClass | 식품의 GI 분류 |
| `:RESULTS_IN` | Food | GlucoseImpact | 식품 섭취가 일으키는 혈당 반응 패턴 |
| `:CONFLICTS_WITH` | Food | DietaryRestriction | 식품이 특정 식이제한과 충돌 |
| `:ALTERNATIVE_TO` | Food | Food | 대체 가능한 식품 (양방향) |

### Foods (10)

흰쌀밥, 잡곡밥, 현미밥, 닭가슴살, 사과, 고구마, 떡, 라면, 김치, 두부.

### Counts

- 10 foods + 5 nutrients + 3 GIClass + 3 GlucoseImpact + 4 DietaryRestriction = 25 nodes.
- CONTAINS, HAS_GI, RESULTS_IN, CONFLICTS_WITH, ALTERNATIVE_TO 관계는 init 스크립트에서 도메인 사실에 맞춰 생성합니다.

## Subgraph 4: Lifecycle Stage Recommendations

웰다 5단계 라이프사이클을 노드로 두고 단계별로 권장/주의 식품과 집중 메커니즘 노드(MetabolicEffect, HormoneState 등)에 edge를 잇습니다.

### Nodes

| Label | Properties |
|---|---|
| `:LifecycleStage` | `name` (영어 enum: UNDERSTANDING/SPIKE_CONTROL/HUNGER_CONTROL/FAT_BURN/MAINTENANCE), `display_name_ko` (한국어), `stage_number` (1-5), `description` (한국어) |

### Relationships

| Type | From | To | Semantics |
|---|---|---|---|
| `:RECOMMENDS` | LifecycleStage | Food | 그 단계에 권장하는 식품 |
| `:CAUTIONS` | LifecycleStage | Food | 그 단계에 주의해야 하는 식품 |
| `:FOCUSES_ON` | LifecycleStage | (HormoneState\|MetabolicEffect\|EnergyState\|Symptom) | 그 단계에서 집중하는 메커니즘 |

### Stages

1. UNDERSTANDING (내 몸 이해하기)
2. SPIKE_CONTROL (혈당 스파이크 조절)
3. HUNGER_CONTROL (배고픔 조절)
4. FAT_BURN (체지방 연소)
5. MAINTENANCE (감량 유지)

### Counts

- 5 lifecycle nodes, 다수의 RECOMMENDS/CAUTIONS/FOCUSES_ON 관계.

## Internationalization (i18n) Strategy

노드 타입을 세 카테고리로 나누어 서로 다른 i18n 패턴을 적용합니다. 카테고리 구분 기준은 "그 노드를 Cypher 쿼리에서 식별자로 쓰는가, 도메인 개념으로 쓰는가, 분류 enum으로 쓰는가" 입니다.

### Category A — Identifier Nodes (English snake_case + Korean display)

| Label | name | display_name_ko |
|---|---|---|
| `:Food` | `white_rice`, `mixed_grain_rice`, ... | `흰쌀밥`, `잡곡밥`, ... |
| `:DietaryRestriction` | `lactose_intolerant`, `vegetarian`, ... | `유당불내증`, `채식주의`, ... |

영어 식별자를 `name`으로 쓰면 Cypher 쿼리, Python 호출자, 테스트가 모두 ASCII-only 문자열로 작성됩니다. UTF-8 인코딩 이슈에 노출되지 않고, 코드 리뷰 시 노드를 한눈에 식별할 수 있습니다. 한국어 표시는 `display_name_ko` 라는 명시적 속성으로 분리합니다.

### Category B — Domain Concept Nodes (Korean name)

| Label | name 예시 |
|---|---|
| `:Behavior`, `:HormoneState`, `:MetabolicEffect`, `:EnergyState`, `:Symptom` | `잘못된 생활 습관`, `인슐린 과잉 분비`, `지방 축적과 인슐린 저항성` |
| `:Nutrient` | `정제 탄수화물`, `복합 탄수화물`, `식이섬유` |
| `:MetabolicIndicator`, `:AbdominalObesity`, `:MetabolicHealthAbnormality` | `고혈당`, `복부 비만`, `대사 건강 이상` |

이 노드들은 코드에서 식별자로 직접 참조하지 않고, RAG/LLM 컨텍스트에서 자연어 의미 그대로 노출됩니다. 의학 용어를 영어로 매핑하면 의미 손실/맥락 이탈이 발생하므로 한국어 name을 유지합니다.

### Category C — Classification Nodes (attribute-based)

| Label | enum 속성 | 부가 속성 |
|---|---|---|
| `:GIClass` | `level` (low/medium/high) | `gi_range`, `display_name`, `description` |
| `:GlucoseImpact` | `pattern` (sharp_spike/gradual_rise/minimal) | `display_name`, `description` |

분류 노드는 enum-like 속성 (영어 소문자)으로 식별하고, 사용자 표시용 `display_name` 과 의미 해설용 `description` 을 별도로 둡니다. `name` 속성을 두지 않는 것은, 분류는 코드에서 enum 값으로만 다루고 자연어 표기는 prompt 생성 시점에만 필요하기 때문입니다.

### LLM Context Strategy

LangChain/LangGraph 노드에서 Neo4j 결과를 LLM prompt 문자열로 변환할 때 카테고리별로 다음 속성을 선택합니다.

- Identifier 노드 (Food, DietaryRestriction): `display_name_ko`
- Domain concept 노드 (Behavior, HormoneState, Nutrient, MetabolicIndicator 등): `name`
- Classification 노드 (GIClass, GlucoseImpact): `display_name` + (필요 시) `description`

이 규칙을 Python 도메인 어댑터(Block 7 Part 2 예정)에 함수로 캡슐화해서 노드 종류별 분기 로직이 prompt 빌더에 노출되지 않게 합니다.

### Reproduction

```bash
docker cp scripts/normalize_graph.cypher welda-neo4j:/tmp/normalize_graph.cypher
docker exec -e LANG=C.UTF-8 -e LC_ALL=C.UTF-8 \
  -e JAVA_TOOL_OPTIONS="-Dfile.encoding=UTF-8" \
  welda-neo4j cypher-shell -u neo4j -p weldapassword \
  -f /tmp/normalize_graph.cypher
```

`normalize_graph.cypher` 는 idempotent: 재실행 시 SET 은 같은 값을 다시 쓰는 no-op, REMOVE 는 이미 비어 있는 속성에 대해서도 안전합니다.

## LLM Fallback Strategy with Web Search

도메인 그래프는 closed-world assumption 을 가지므로 신조어, 트렌드 음식, 지역 음식 같은 longtail 쿼리를 커버할 수 없습니다. Claude의 server-side `web_search` tool을 통해 실시간 정보로 보완합니다.

### Architecture

1. 사용자 질문이 식단 의도(diet_advice)일 때, LangGraph 노드가 `WeldaGraphDB.lookup_food` 로 그래프 lookup 을 수행합니다.
2. **그래프 hit**: 도메인 데이터 (영양/GI/혈당 영향/대체 식품/식이제한)를 컨텍스트로 응답. 출처는 `graph:food:<name>` 형식.
3. **그래프 miss**: `create_fallback_llm()` 으로 만든 ChatAnthropic (web_search tool 활성화)이 LLM 판단에 따라 자동으로 web search 를 호출. 출처는 검색된 URL 리스트.
4. 두 경우 모두 동일한 통합 프롬프트 (`build_fallback_prompt`)를 사용. 그래프 컨텍스트가 비어 있으면 LLM 에게 "신조어/트렌드 음식이면 web_search 호출" 지시.
5. 응답 후 `inject_fallback_disclaimer_if_missing` 로 disclaimer 누락을 코드 레벨에서 보강 (프롬프트 + 코드 이중 안전망).

### Why No Client-Side Heuristic

명세 초안에서 `detect_trend_signal` 같은 휴리스틱으로 web search 호출 여부를 미리 결정하는 안이 있었지만, 단순 글자 길이/ASCII 검사 휴리스틱이 일반 음식 쿼리도 trend 로 잘못 분류하는 false-positive 가 쉽게 발생했습니다 (예: "흰쌀밥 먹어도 돼?" 의 "먹어도" 가 trend 로 잡힘). LLM 에게 도메인 컨텍스트 + 질문을 함께 주고 자체 판단하게 하는 편이 더 정확하고, 모델 업그레이드 시 자동으로 개선됩니다.

### Cost Management

- Anthropic web_search 가격: $0.01/call + 토큰 비용
- `max_uses=3` per turn 으로 호출 상한 설정 (모델이 한 응답 안에서 무한 검색하는 것 차단)
- 그래프 hit 케이스에는 web_search 호출 비용 0 (LLM 이 그래프 컨텍스트만 보고 답변)
- 실측 평균: 그래프 hit 70% 가정 시 호출당 약 $0.003 (web_search 30% × $0.01)

### Persona-Driven Design

웰다의 핵심 사용자 페르소나는 20-30대 여성 다이어트 사용자이며, SNS 트렌드 음식 노출 빈도가 높습니다. 신조어/트렌드 음식 질의 비율을 무시할 수 없어 fallback 전략이 retention 의 핵심 요소가 됩니다. 그래프 단독으로는 첫 한 달 안에 사용자가 "왜 이건 모르세요?" 경험을 반복하게 됩니다.

### Production Extension Paths

- 농촌진흥청 식품영양정보 DB API 통합 (한국 표준 식품 자동 확장)
- Vision 모델 기반 사진 인식 (DeepSeek-VL → 자동 노드 매핑)
- 사용자 기여 + 의료진 검증 워크플로우 (LangGraph human-in-the-loop)
- 미커버 쿼리 로그 분석 → 우선순위 기반 그래프 확장 (반복 검색되는 trend 음식을 그래프로 promote)

## Indexing Notes (Block 7 Part 2 이후)

- `Food(name)`, `MetabolicIndicator(name)` 에 unique constraint를 걸어 중복 생성 방지.
- LangGraph GraphRAG 노드에서 `:Food {name: $name}` 룩업이 잦으므로 인덱스 우선 적용.

## Reproduction

```bash
cat scripts/init_graph.cypher | docker exec -i welda-neo4j cypher-shell -u neo4j -p weldapassword
```

스크립트는 idempotent: 시작부에서 모든 노드와 관계를 삭제(`MATCH (n) DETACH DELETE n`)하므로 반복 실행해도 같은 결과를 만듭니다.
