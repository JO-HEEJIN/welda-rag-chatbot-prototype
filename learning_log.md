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
