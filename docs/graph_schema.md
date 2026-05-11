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
| `:Food` | `name`, `korean_name`, `category` (rice/noodle/meat/fruit/tuber/vegetable/processed/legume) |
| `:Nutrient` | `name`, `type` (carb/protein/fat/fiber) |
| `:GIClass` | `level` (low/medium/high), `gi_range` (string, e.g. "<=55", "56-69", ">=70") |
| `:GlucoseImpact` | `pattern` (sharp_spike/gradual_rise/minimal), `description` |
| `:DietaryRestriction` | `name` (예: lactose_intolerant, vegetarian, vegan, gluten_free) |

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
| `:LifecycleStage` | `name`, `stage_number`, `description` |

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

## Indexing Notes (Block 7 Part 2 이후)

- `Food(name)`, `MetabolicIndicator(name)` 에 unique constraint를 걸어 중복 생성 방지.
- LangGraph GraphRAG 노드에서 `:Food {name: $name}` 룩업이 잦으므로 인덱스 우선 적용.

## Reproduction

```bash
cat scripts/init_graph.cypher | docker exec -i welda-neo4j cypher-shell -u neo4j -p weldapassword
```

스크립트는 idempotent: 시작부에서 모든 노드와 관계를 삭제(`MATCH (n) DETACH DELETE n`)하므로 반복 실행해도 같은 결과를 만듭니다.
