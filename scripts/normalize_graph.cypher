// Welda graph i18n normalization.
// Idempotent: each SET is safe to re-run. Rename of korean_name -> display_name_ko
// is guarded by IS NOT NULL so it no-ops after the first run.
// Run with:
//   docker cp scripts/normalize_graph.cypher welda-neo4j:/tmp/normalize_graph.cypher
//   docker exec -e LANG=C.UTF-8 -e LC_ALL=C.UTF-8 \
//     -e JAVA_TOOL_OPTIONS="-Dfile.encoding=UTF-8" \
//     welda-neo4j cypher-shell -u neo4j -p weldapassword \
//     -f /tmp/normalize_graph.cypher

// =================================================================
// Food: rename korean_name -> display_name_ko
// =================================================================
MATCH (f:Food) WHERE f.korean_name IS NOT NULL
SET f.display_name_ko = f.korean_name
REMOVE f.korean_name;

// =================================================================
// DietaryRestriction: add display_name_ko
// =================================================================
MATCH (d:DietaryRestriction {name: "lactose_intolerant"}) SET d.display_name_ko = "유당불내증";
MATCH (d:DietaryRestriction {name: "vegetarian"}) SET d.display_name_ko = "채식주의";
MATCH (d:DietaryRestriction {name: "vegan"}) SET d.display_name_ko = "비건";
MATCH (d:DietaryRestriction {name: "gluten_free"}) SET d.display_name_ko = "글루텐 프리";

// =================================================================
// GIClass: add display_name and description (keep gi_range)
// =================================================================
MATCH (g:GIClass {level: "high"})
SET g.display_name = "고혈당지수",
    g.description = "혈당을 빠르고 큰 폭으로 상승시키는 식품군";

MATCH (g:GIClass {level: "medium"})
SET g.display_name = "중혈당지수",
    g.description = "혈당을 중간 정도로 상승시키는 식품군";

MATCH (g:GIClass {level: "low"})
SET g.display_name = "저혈당지수",
    g.description = "혈당 상승이 완만한 식품군";

// =================================================================
// GlucoseImpact: add display_name (keep existing description)
// =================================================================
MATCH (gi:GlucoseImpact {pattern: "sharp_spike"}) SET gi.display_name = "급격한 혈당 스파이크";
MATCH (gi:GlucoseImpact {pattern: "gradual_rise"}) SET gi.display_name = "완만한 혈당 상승";
MATCH (gi:GlucoseImpact {pattern: "minimal"}) SET gi.display_name = "최소 혈당 영향";

// =================================================================
// LifecycleStage: add display_name_ko
// =================================================================
MATCH (l:LifecycleStage {name: "UNDERSTANDING"}) SET l.display_name_ko = "내 몸 이해하기";
MATCH (l:LifecycleStage {name: "SPIKE_CONTROL"}) SET l.display_name_ko = "혈당 스파이크 조절";
MATCH (l:LifecycleStage {name: "HUNGER_CONTROL"}) SET l.display_name_ko = "배고픔 조절";
MATCH (l:LifecycleStage {name: "FAT_BURN"}) SET l.display_name_ko = "체지방 연소";
MATCH (l:LifecycleStage {name: "MAINTENANCE"}) SET l.display_name_ko = "감량 유지";
