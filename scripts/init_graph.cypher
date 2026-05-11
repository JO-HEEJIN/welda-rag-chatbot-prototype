// Welda domain graph initialization.
// Idempotent: wipes the database, then recreates every node and relationship.
// Run with: cat scripts/init_graph.cypher | docker exec -i welda-neo4j cypher-shell -u neo4j -p weldapassword

MATCH (n) DETACH DELETE n;

// =================================================================
// 1. Insulin Resistance Cycle (7 nodes, 6 relationships)
// =================================================================

CREATE (b1:Behavior {
    name: "잘못된 생활 습관",
    stage: 1,
    description: "정제 탄수화물 위주의 식단, 신체 활동 부족, 수면 부족, 만성 스트레스 등 인슐린 저항성을 유발하는 행동 패턴"
});
CREATE (h2:HormoneState {
    name: "인슐린 과잉 분비",
    stage: 2,
    description: "반복적인 고탄수화물 섭취로 췌장 베타세포가 인슐린을 과다 분비하는 상태"
});
CREATE (m3:MetabolicEffect {
    name: "지방 축적과 인슐린 저항성",
    stage: 3,
    description: "고인슐린 환경에서 내장지방이 축적되고 표적 세포의 인슐린 신호가 둔감해지는 상태"
});
CREATE (e4:EnergyState {
    name: "세포 에너지 부족",
    stage: 4,
    description: "혈당이 세포 내부로 충분히 흡수되지 않아 조직 단위에서 에너지 결핍이 발생"
});
CREATE (s5:Symptom {
    name: "피로와 가짜 배고픔",
    stage: 5,
    description: "에너지 부족으로 인한 만성 피로, 식후 졸음, 짧은 주기의 단 음식 갈망"
});
CREATE (s6:Symptom {
    name: "혈당 변동성 증가",
    stage: 6,
    description: "반복적인 스파이크와 급강하로 혈당이 안정되지 못하는 상태"
});
CREATE (b7:Behavior {
    name: "보상성 과식과 활동 회피",
    stage: 7,
    description: "피로와 갈망에 의한 추가 정제 탄수화물 섭취, 활동량 감소가 다시 1단계 행동을 강화"
});

MATCH (b1:Behavior {stage: 1}), (h2:HormoneState {stage: 2}) CREATE (b1)-[:TRIGGERS]->(h2);
MATCH (h2:HormoneState {stage: 2}), (m3:MetabolicEffect {stage: 3}) CREATE (h2)-[:CAUSES]->(m3);
MATCH (m3:MetabolicEffect {stage: 3}), (e4:EnergyState {stage: 4}) CREATE (m3)-[:LEADS_TO]->(e4);
MATCH (e4:EnergyState {stage: 4}), (s5:Symptom {stage: 5}) CREATE (e4)-[:LEADS_TO]->(s5);
MATCH (s5:Symptom {stage: 5}), (s6:Symptom {stage: 6}) CREATE (s5)-[:LEADS_TO]->(s6);
MATCH (s6:Symptom {stage: 6}), (b7:Behavior {stage: 7}) CREATE (s6)-[:LEADS_TO]->(b7);
MATCH (b7:Behavior {stage: 7}), (b1:Behavior {stage: 1}) CREATE (b7)-[:REINFORCES]->(b1);

// =================================================================
// 2. Metabolic Health Indicators (6 nodes, 9 relationships)
// =================================================================

CREATE (mha:MetabolicHealthAbnormality {
    name: "대사 건강 이상",
    definition: "대사증후군 진단 기준에 해당하는 복부 비만, 고혈당, 고혈압, 고중성지방, HDL 저하 등을 포함하는 상태"
});
CREATE (mi_glucose:MetabolicIndicator {
    name: "고혈당",
    normal_range: "공복 70-99",
    unit: "mg/dL"
});
CREATE (mi_bp:MetabolicIndicator {
    name: "고혈압",
    normal_range: "수축기 <130, 이완기 <85",
    unit: "mmHg"
});
CREATE (mi_tg:MetabolicIndicator {
    name: "고중성지방",
    normal_range: "<150",
    unit: "mg/dL"
});
CREATE (mi_hdl:MetabolicIndicator {
    name: "HDL 저하",
    normal_range: "남 >=40, 여 >=50",
    unit: "mg/dL"
});
CREATE (ao:AbdominalObesity {
    name: "복부 비만",
    criteria_male: "허리둘레 >=90cm",
    criteria_female: "허리둘레 >=85cm"
});

MATCH (mi:MetabolicIndicator {name: "고혈당"}), (mha:MetabolicHealthAbnormality {name: "대사 건강 이상"}) CREATE (mi)-[:INDICATES]->(mha);
MATCH (mi:MetabolicIndicator {name: "고혈압"}), (mha:MetabolicHealthAbnormality {name: "대사 건강 이상"}) CREATE (mi)-[:INDICATES]->(mha);
MATCH (mi:MetabolicIndicator {name: "고중성지방"}), (mha:MetabolicHealthAbnormality {name: "대사 건강 이상"}) CREATE (mi)-[:INDICATES]->(mha);
MATCH (mi:MetabolicIndicator {name: "HDL 저하"}), (mha:MetabolicHealthAbnormality {name: "대사 건강 이상"}) CREATE (mi)-[:INDICATES]->(mha);
MATCH (ao:AbdominalObesity {name: "복부 비만"}), (mha:MetabolicHealthAbnormality {name: "대사 건강 이상"}) CREATE (ao)-[:INDICATES]->(mha);
MATCH (ao:AbdominalObesity {name: "복부 비만"}), (mi:MetabolicIndicator {name: "고혈당"}) CREATE (ao)-[:MANIFESTS_AS]->(mi);
MATCH (ao:AbdominalObesity {name: "복부 비만"}), (mi:MetabolicIndicator {name: "고혈압"}) CREATE (ao)-[:MANIFESTS_AS]->(mi);
MATCH (ao:AbdominalObesity {name: "복부 비만"}), (mi:MetabolicIndicator {name: "고중성지방"}) CREATE (ao)-[:MANIFESTS_AS]->(mi);
MATCH (ao:AbdominalObesity {name: "복부 비만"}), (mi:MetabolicIndicator {name: "HDL 저하"}) CREATE (ao)-[:MANIFESTS_AS]->(mi);

// =================================================================
// 3. Food-Nutrient-Glucose Impact (25 nodes, many relationships)
// =================================================================

// 3a. GIClass
CREATE (gi_low:GIClass {level: "low", gi_range: "<=55"});
CREATE (gi_mid:GIClass {level: "medium", gi_range: "56-69"});
CREATE (gi_high:GIClass {level: "high", gi_range: ">=70"});

// 3b. GlucoseImpact patterns
CREATE (gi_spike:GlucoseImpact {
    pattern: "sharp_spike",
    description: "식후 30~60분 내 혈당이 급격히 상승했다가 빠르게 하강하는 패턴"
});
CREATE (gi_gradual:GlucoseImpact {
    pattern: "gradual_rise",
    description: "식후 혈당이 완만하게 상승하고 정점도 낮은 패턴"
});
CREATE (gi_minimal:GlucoseImpact {
    pattern: "minimal",
    description: "탄수화물 함량이 낮거나 식이섬유/단백질 비중이 높아 혈당 영향이 거의 없는 패턴"
});

// 3c. Nutrients
CREATE (n_carb:Nutrient {name: "정제 탄수화물", type: "carb"});
CREATE (n_complex_carb:Nutrient {name: "복합 탄수화물", type: "carb"});
CREATE (n_fiber:Nutrient {name: "식이섬유", type: "fiber"});
CREATE (n_protein:Nutrient {name: "단백질", type: "protein"});
CREATE (n_fat:Nutrient {name: "지방", type: "fat"});

// 3d. Dietary Restrictions
CREATE (dr_lactose:DietaryRestriction {name: "lactose_intolerant"});
CREATE (dr_veg:DietaryRestriction {name: "vegetarian"});
CREATE (dr_vegan:DietaryRestriction {name: "vegan"});
CREATE (dr_gluten:DietaryRestriction {name: "gluten_free"});

// 3e. Foods (10)
CREATE (f_whiterice:Food {name: "white_rice", korean_name: "흰쌀밥", category: "rice"});
CREATE (f_mixedrice:Food {name: "mixed_grain_rice", korean_name: "잡곡밥", category: "rice"});
CREATE (f_brownrice:Food {name: "brown_rice", korean_name: "현미밥", category: "rice"});
CREATE (f_chicken:Food {name: "chicken_breast", korean_name: "닭가슴살", category: "meat"});
CREATE (f_apple:Food {name: "apple", korean_name: "사과", category: "fruit"});
CREATE (f_sweetpotato:Food {name: "sweet_potato", korean_name: "고구마", category: "tuber"});
CREATE (f_ricecake:Food {name: "rice_cake", korean_name: "떡", category: "processed"});
CREATE (f_ramen:Food {name: "ramen", korean_name: "라면", category: "noodle"});
CREATE (f_kimchi:Food {name: "kimchi", korean_name: "김치", category: "vegetable"});
CREATE (f_tofu:Food {name: "tofu", korean_name: "두부", category: "legume"});

// 3f. Food -> Nutrient (CONTAINS)
MATCH (f:Food {name: "white_rice"}), (n:Nutrient {name: "정제 탄수화물"}) CREATE (f)-[:CONTAINS]->(n);
MATCH (f:Food {name: "mixed_grain_rice"}), (n:Nutrient {name: "복합 탄수화물"}) CREATE (f)-[:CONTAINS]->(n);
MATCH (f:Food {name: "mixed_grain_rice"}), (n:Nutrient {name: "식이섬유"}) CREATE (f)-[:CONTAINS]->(n);
MATCH (f:Food {name: "brown_rice"}), (n:Nutrient {name: "복합 탄수화물"}) CREATE (f)-[:CONTAINS]->(n);
MATCH (f:Food {name: "brown_rice"}), (n:Nutrient {name: "식이섬유"}) CREATE (f)-[:CONTAINS]->(n);
MATCH (f:Food {name: "chicken_breast"}), (n:Nutrient {name: "단백질"}) CREATE (f)-[:CONTAINS]->(n);
MATCH (f:Food {name: "apple"}), (n:Nutrient {name: "식이섬유"}) CREATE (f)-[:CONTAINS]->(n);
MATCH (f:Food {name: "apple"}), (n:Nutrient {name: "복합 탄수화물"}) CREATE (f)-[:CONTAINS]->(n);
MATCH (f:Food {name: "sweet_potato"}), (n:Nutrient {name: "복합 탄수화물"}) CREATE (f)-[:CONTAINS]->(n);
MATCH (f:Food {name: "sweet_potato"}), (n:Nutrient {name: "식이섬유"}) CREATE (f)-[:CONTAINS]->(n);
MATCH (f:Food {name: "rice_cake"}), (n:Nutrient {name: "정제 탄수화물"}) CREATE (f)-[:CONTAINS]->(n);
MATCH (f:Food {name: "ramen"}), (n:Nutrient {name: "정제 탄수화물"}) CREATE (f)-[:CONTAINS]->(n);
MATCH (f:Food {name: "ramen"}), (n:Nutrient {name: "지방"}) CREATE (f)-[:CONTAINS]->(n);
MATCH (f:Food {name: "kimchi"}), (n:Nutrient {name: "식이섬유"}) CREATE (f)-[:CONTAINS]->(n);
MATCH (f:Food {name: "tofu"}), (n:Nutrient {name: "단백질"}) CREATE (f)-[:CONTAINS]->(n);
MATCH (f:Food {name: "tofu"}), (n:Nutrient {name: "지방"}) CREATE (f)-[:CONTAINS]->(n);

// 3g. Food -> GIClass (HAS_GI)
MATCH (f:Food {name: "white_rice"}), (g:GIClass {level: "high"}) CREATE (f)-[:HAS_GI]->(g);
MATCH (f:Food {name: "mixed_grain_rice"}), (g:GIClass {level: "medium"}) CREATE (f)-[:HAS_GI]->(g);
MATCH (f:Food {name: "brown_rice"}), (g:GIClass {level: "medium"}) CREATE (f)-[:HAS_GI]->(g);
MATCH (f:Food {name: "chicken_breast"}), (g:GIClass {level: "low"}) CREATE (f)-[:HAS_GI]->(g);
MATCH (f:Food {name: "apple"}), (g:GIClass {level: "low"}) CREATE (f)-[:HAS_GI]->(g);
MATCH (f:Food {name: "sweet_potato"}), (g:GIClass {level: "medium"}) CREATE (f)-[:HAS_GI]->(g);
MATCH (f:Food {name: "rice_cake"}), (g:GIClass {level: "high"}) CREATE (f)-[:HAS_GI]->(g);
MATCH (f:Food {name: "ramen"}), (g:GIClass {level: "high"}) CREATE (f)-[:HAS_GI]->(g);
MATCH (f:Food {name: "kimchi"}), (g:GIClass {level: "low"}) CREATE (f)-[:HAS_GI]->(g);
MATCH (f:Food {name: "tofu"}), (g:GIClass {level: "low"}) CREATE (f)-[:HAS_GI]->(g);

// 3h. Food -> GlucoseImpact (RESULTS_IN)
MATCH (f:Food {name: "white_rice"}), (i:GlucoseImpact {pattern: "sharp_spike"}) CREATE (f)-[:RESULTS_IN]->(i);
MATCH (f:Food {name: "mixed_grain_rice"}), (i:GlucoseImpact {pattern: "gradual_rise"}) CREATE (f)-[:RESULTS_IN]->(i);
MATCH (f:Food {name: "brown_rice"}), (i:GlucoseImpact {pattern: "gradual_rise"}) CREATE (f)-[:RESULTS_IN]->(i);
MATCH (f:Food {name: "chicken_breast"}), (i:GlucoseImpact {pattern: "minimal"}) CREATE (f)-[:RESULTS_IN]->(i);
MATCH (f:Food {name: "apple"}), (i:GlucoseImpact {pattern: "gradual_rise"}) CREATE (f)-[:RESULTS_IN]->(i);
MATCH (f:Food {name: "sweet_potato"}), (i:GlucoseImpact {pattern: "gradual_rise"}) CREATE (f)-[:RESULTS_IN]->(i);
MATCH (f:Food {name: "rice_cake"}), (i:GlucoseImpact {pattern: "sharp_spike"}) CREATE (f)-[:RESULTS_IN]->(i);
MATCH (f:Food {name: "ramen"}), (i:GlucoseImpact {pattern: "sharp_spike"}) CREATE (f)-[:RESULTS_IN]->(i);
MATCH (f:Food {name: "kimchi"}), (i:GlucoseImpact {pattern: "minimal"}) CREATE (f)-[:RESULTS_IN]->(i);
MATCH (f:Food {name: "tofu"}), (i:GlucoseImpact {pattern: "minimal"}) CREATE (f)-[:RESULTS_IN]->(i);

// 3i. Food -> DietaryRestriction (CONFLICTS_WITH)
MATCH (f:Food {name: "ramen"}), (r:DietaryRestriction {name: "gluten_free"}) CREATE (f)-[:CONFLICTS_WITH]->(r);
MATCH (f:Food {name: "chicken_breast"}), (r:DietaryRestriction {name: "vegetarian"}) CREATE (f)-[:CONFLICTS_WITH]->(r);
MATCH (f:Food {name: "chicken_breast"}), (r:DietaryRestriction {name: "vegan"}) CREATE (f)-[:CONFLICTS_WITH]->(r);

// 3j. Food ALTERNATIVE_TO Food (대체 가능, 방향성 정보 보존을 위해 단방향으로만 생성)
MATCH (a:Food {name: "white_rice"}), (b:Food {name: "mixed_grain_rice"}) CREATE (a)-[:ALTERNATIVE_TO]->(b);
MATCH (a:Food {name: "white_rice"}), (b:Food {name: "brown_rice"}) CREATE (a)-[:ALTERNATIVE_TO]->(b);
MATCH (a:Food {name: "rice_cake"}), (b:Food {name: "sweet_potato"}) CREATE (a)-[:ALTERNATIVE_TO]->(b);
MATCH (a:Food {name: "ramen"}), (b:Food {name: "mixed_grain_rice"}) CREATE (a)-[:ALTERNATIVE_TO]->(b);

// =================================================================
// 4. Lifecycle Stage Recommendations (5 nodes + relationships)
// =================================================================

CREATE (ls1:LifecycleStage {
    name: "UNDERSTANDING",
    stage_number: 1,
    description: "내 몸 이해하기 — 자신의 혈당 반응과 생활 패턴을 관찰하는 단계"
});
CREATE (ls2:LifecycleStage {
    name: "SPIKE_CONTROL",
    stage_number: 2,
    description: "혈당 스파이크 조절 — 식후 혈당 급상승을 줄이는 단계"
});
CREATE (ls3:LifecycleStage {
    name: "HUNGER_CONTROL",
    stage_number: 3,
    description: "배고픔 조절 — 가짜 배고픔 식별과 식욕 안정화"
});
CREATE (ls4:LifecycleStage {
    name: "FAT_BURN",
    stage_number: 4,
    description: "체지방 연소 — 대사 유연성 회복 후 체지방 감량"
});
CREATE (ls5:LifecycleStage {
    name: "MAINTENANCE",
    stage_number: 5,
    description: "감량 유지 — 신체 컴포지션과 혈당 안정 장기 유지"
});

// 4a. LifecycleStage -> Food (RECOMMENDS)
MATCH (s:LifecycleStage {name: "SPIKE_CONTROL"}), (f:Food {name: "mixed_grain_rice"}) CREATE (s)-[:RECOMMENDS]->(f);
MATCH (s:LifecycleStage {name: "SPIKE_CONTROL"}), (f:Food {name: "brown_rice"}) CREATE (s)-[:RECOMMENDS]->(f);
MATCH (s:LifecycleStage {name: "SPIKE_CONTROL"}), (f:Food {name: "tofu"}) CREATE (s)-[:RECOMMENDS]->(f);
MATCH (s:LifecycleStage {name: "SPIKE_CONTROL"}), (f:Food {name: "chicken_breast"}) CREATE (s)-[:RECOMMENDS]->(f);
MATCH (s:LifecycleStage {name: "HUNGER_CONTROL"}), (f:Food {name: "tofu"}) CREATE (s)-[:RECOMMENDS]->(f);
MATCH (s:LifecycleStage {name: "HUNGER_CONTROL"}), (f:Food {name: "chicken_breast"}) CREATE (s)-[:RECOMMENDS]->(f);
MATCH (s:LifecycleStage {name: "HUNGER_CONTROL"}), (f:Food {name: "apple"}) CREATE (s)-[:RECOMMENDS]->(f);
MATCH (s:LifecycleStage {name: "FAT_BURN"}), (f:Food {name: "chicken_breast"}) CREATE (s)-[:RECOMMENDS]->(f);
MATCH (s:LifecycleStage {name: "FAT_BURN"}), (f:Food {name: "tofu"}) CREATE (s)-[:RECOMMENDS]->(f);
MATCH (s:LifecycleStage {name: "FAT_BURN"}), (f:Food {name: "kimchi"}) CREATE (s)-[:RECOMMENDS]->(f);
MATCH (s:LifecycleStage {name: "MAINTENANCE"}), (f:Food {name: "mixed_grain_rice"}) CREATE (s)-[:RECOMMENDS]->(f);
MATCH (s:LifecycleStage {name: "MAINTENANCE"}), (f:Food {name: "brown_rice"}) CREATE (s)-[:RECOMMENDS]->(f);

// 4b. LifecycleStage -> Food (CAUTIONS)
MATCH (s:LifecycleStage {name: "SPIKE_CONTROL"}), (f:Food {name: "white_rice"}) CREATE (s)-[:CAUTIONS]->(f);
MATCH (s:LifecycleStage {name: "SPIKE_CONTROL"}), (f:Food {name: "rice_cake"}) CREATE (s)-[:CAUTIONS]->(f);
MATCH (s:LifecycleStage {name: "SPIKE_CONTROL"}), (f:Food {name: "ramen"}) CREATE (s)-[:CAUTIONS]->(f);
MATCH (s:LifecycleStage {name: "HUNGER_CONTROL"}), (f:Food {name: "rice_cake"}) CREATE (s)-[:CAUTIONS]->(f);
MATCH (s:LifecycleStage {name: "HUNGER_CONTROL"}), (f:Food {name: "ramen"}) CREATE (s)-[:CAUTIONS]->(f);
MATCH (s:LifecycleStage {name: "FAT_BURN"}), (f:Food {name: "rice_cake"}) CREATE (s)-[:CAUTIONS]->(f);
MATCH (s:LifecycleStage {name: "FAT_BURN"}), (f:Food {name: "ramen"}) CREATE (s)-[:CAUTIONS]->(f);
MATCH (s:LifecycleStage {name: "FAT_BURN"}), (f:Food {name: "white_rice"}) CREATE (s)-[:CAUTIONS]->(f);

// 4c. LifecycleStage -> mechanism (FOCUSES_ON)
MATCH (s:LifecycleStage {name: "UNDERSTANDING"}), (m:Symptom {name: "혈당 변동성 증가"}) CREATE (s)-[:FOCUSES_ON]->(m);
MATCH (s:LifecycleStage {name: "SPIKE_CONTROL"}), (m:HormoneState {name: "인슐린 과잉 분비"}) CREATE (s)-[:FOCUSES_ON]->(m);
MATCH (s:LifecycleStage {name: "HUNGER_CONTROL"}), (m:Symptom {name: "피로와 가짜 배고픔"}) CREATE (s)-[:FOCUSES_ON]->(m);
MATCH (s:LifecycleStage {name: "FAT_BURN"}), (m:MetabolicEffect {name: "지방 축적과 인슐린 저항성"}) CREATE (s)-[:FOCUSES_ON]->(m);
MATCH (s:LifecycleStage {name: "MAINTENANCE"}), (m:EnergyState {name: "세포 에너지 부족"}) CREATE (s)-[:FOCUSES_ON]->(m);
