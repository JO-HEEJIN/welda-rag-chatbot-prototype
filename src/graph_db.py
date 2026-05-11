"""Neo4j adapter for the Welda domain graph.

Provides a context-managed driver wrapper plus the two domain queries used by
the LangGraph nodes in Block 7 Part 3:

- ``lookup_food`` — multi-hop traversal that returns the food's nutrient list,
  GI class, glucose impact, alternatives, and conflicting dietary restrictions.
- ``get_lifecycle_recommendations`` — per-stage RECOMMENDS / CAUTIONS food
  display names for prompt injection.

Korean queries are accepted: ``lookup_food("흰쌀밥")`` resolves to the same
Food node as ``lookup_food("white_rice")`` via the ``display_name_ko`` lookup.
"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase
from neo4j.exceptions import ServiceUnavailable

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "weldapassword")


@dataclass
class GraphLookupResult:
    """Container for a single graph lookup.

    ``found=False`` means the node does not exist in the closed-world domain
    graph; callers should treat this as a signal to engage the web-search
    fallback rather than as an error.
    """

    found: bool
    node_data: dict | None = None
    context_text: str = ""
    sources: list[str] = field(default_factory=list)


class WeldaGraphDB:
    """Context-managed Neo4j driver with domain query helpers.

    Usage::

        with WeldaGraphDB() as graph:
            result = graph.lookup_food("흰쌀밥")
    """

    def __init__(
        self,
        uri: str = NEO4J_URI,
        username: str = NEO4J_USERNAME,
        password: str = NEO4J_PASSWORD,
    ):
        self.uri = uri
        self._driver: Driver | None = None
        self._auth = (username, password)

    def connect(self) -> None:
        """Open the driver and validate the connection with a trivial query."""
        self._driver = GraphDatabase.driver(self.uri, auth=self._auth)
        with self._driver.session() as session:
            session.run("RETURN 1")

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def __enter__(self) -> "WeldaGraphDB":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # ----- Korean → English key mapping ------------------------------------

    def find_food_by_korean_name(self, korean_name: str) -> str | None:
        """Resolve a Korean ``display_name_ko`` to the canonical English ``name``."""
        query = """
        MATCH (f:Food {display_name_ko: $korean_name})
        RETURN f.name AS name
        """
        with self._driver.session() as session:
            record = session.run(query, korean_name=korean_name).single()
            return record["name"] if record else None

    def get_all_food_korean_names(self) -> list[str]:
        """Return every Food node's ``display_name_ko`` sorted by length desc.

        Sorted longest-first so substring matching in ``food_extraction_node``
        picks the most specific name ("잡곡밥" before "밥") when a query
        mentions multiple candidate foods.
        """
        query = "MATCH (f:Food) RETURN f.display_name_ko AS name"
        with self._driver.session() as session:
            names = [r["name"] for r in session.run(query) if r["name"]]
        return sorted(names, key=len, reverse=True)

    # ----- Food domain query -----------------------------------------------

    def lookup_food(self, food_name: str) -> GraphLookupResult:
        """Multi-hop food profile lookup.

        Accepts either the English snake_case ``name`` or the Korean
        ``display_name_ko``. Returns a ``GraphLookupResult`` with rendered
        Korean prompt context when found, or ``found=False`` when the food is
        outside the domain graph.
        """
        if not food_name.replace("_", "").isascii():
            english_key = self.find_food_by_korean_name(food_name)
            if english_key is None:
                return GraphLookupResult(found=False)
            food_name = english_key

        query = """
        MATCH (f:Food {name: $name})
        OPTIONAL MATCH (f)-[:CONTAINS]->(n:Nutrient)
        OPTIONAL MATCH (f)-[:HAS_GI]->(gi:GIClass)
        OPTIONAL MATCH (f)-[:RESULTS_IN]->(impact:GlucoseImpact)
        OPTIONAL MATCH (f)-[:ALTERNATIVE_TO]-(alt:Food)
        OPTIONAL MATCH (f)-[:CONFLICTS_WITH]->(restriction:DietaryRestriction)
        RETURN
            f.name AS name,
            f.display_name_ko AS display_name_ko,
            f.category AS category,
            collect(DISTINCT n.name) AS nutrients,
            collect(DISTINCT {level: gi.level, display: gi.display_name, range: gi.gi_range}) AS gi_info,
            collect(DISTINCT {pattern: impact.pattern, display: impact.display_name, description: impact.description}) AS impact_info,
            collect(DISTINCT alt.display_name_ko) AS alternatives,
            collect(DISTINCT restriction.display_name_ko) AS restrictions
        """
        with self._driver.session() as session:
            record = session.run(query, name=food_name).single()
            if record is None:
                return GraphLookupResult(found=False)

            data = dict(record)
            return GraphLookupResult(
                found=True,
                node_data=data,
                context_text=self._format_food_context(data),
                sources=[f"graph:food:{food_name}"],
            )

    def _format_food_context(self, data: dict) -> str:
        """Render a food lookup result as a Korean prompt-ready block."""
        lines = [f"## {data['display_name_ko']} ({data['name']})"]

        if data.get("category"):
            lines.append(f"분류: {data['category']}")

        nutrients = [n for n in data["nutrients"] if n]
        if nutrients:
            lines.append(f"주요 영양소: {', '.join(nutrients)}")

        gi_entries = [g for g in data["gi_info"] if g.get("level")]
        if gi_entries:
            gi = gi_entries[0]
            lines.append(f"혈당지수: {gi['display']} ({gi['range']})")

        impact_entries = [i for i in data["impact_info"] if i.get("pattern")]
        if impact_entries:
            impact = impact_entries[0]
            lines.append(f"혈당 영향: {impact['display']} - {impact['description']}")

        alternatives = [a for a in data["alternatives"] if a]
        if alternatives:
            lines.append(f"대체 가능 식품: {', '.join(alternatives)}")

        restrictions = [r for r in data["restrictions"] if r]
        if restrictions:
            lines.append(f"식이제한 충돌: {', '.join(restrictions)}")

        return "\n".join(lines)

    # ----- Lifecycle recommendations ---------------------------------------

    def get_lifecycle_recommendations(self, stage: str) -> dict[str, list[str]]:
        """Return Korean ``display_name_ko`` lists of recommended / cautioned foods."""
        query = """
        MATCH (ls:LifecycleStage {name: $stage})
        OPTIONAL MATCH (ls)-[:RECOMMENDS]->(rec:Food)
        OPTIONAL MATCH (ls)-[:CAUTIONS]->(caut:Food)
        RETURN
            collect(DISTINCT rec.display_name_ko) AS recommended,
            collect(DISTINCT caut.display_name_ko) AS cautions
        """
        with self._driver.session() as session:
            record = session.run(query, stage=stage).single()
            if record is None:
                return {"recommended": [], "cautions": []}
            return {
                "recommended": [r for r in record["recommended"] if r],
                "cautions": [c for c in record["cautions"] if c],
            }

    # ----- Health -----------------------------------------------------------

    def health_check(self) -> bool:
        """Lightweight ping. Returns False on any driver error."""
        if self._driver is None:
            return False
        try:
            with self._driver.session() as session:
                session.run("RETURN 1")
            return True
        except ServiceUnavailable:
            return False
        except Exception:
            return False
