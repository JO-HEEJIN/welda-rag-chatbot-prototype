"""Unified graph hit/miss fallback with Claude's server-side web_search tool.

The domain graph is closed-world: new foods (trend desserts, slang, regional
dishes) won't be in Neo4j. Instead of hand-rolling a heuristic classifier, we
hand the LLM a ``web_search`` tool plus both the graph context and the user
question, and let it decide when to search. The prompt builder explains the
contract; the helpers in this module post-process the response.
"""

from typing import Any

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

load_dotenv()

GRAPH_FALLBACK_DISCLAIMER = (
    "위 정보는 일반 영양 지식 또는 웹 검색 결과를 AI가 정리한 것이며, "
    "정확한 영양 분석과 개인 맞춤 권장은 영양사 또는 의료진 상담을 권장드립니다. "
    "본 응답은 의학적 자문이 아니며, 정확성을 보증하지 않습니다."
)


def create_fallback_llm(
    model: str = "claude-sonnet-4-6",
    max_uses: int = 3,
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> ChatAnthropic:
    """Build a ChatAnthropic with the server-side ``web_search`` tool enabled.

    ``max_uses`` caps the number of web search calls per response to control
    cost. Anthropic's web_search tool is server-managed: no client-side
    orchestration is needed — the model decides whether to call it.
    """
    return ChatAnthropic(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        model_kwargs={
            "tools": [
                {
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": max_uses,
                }
            ]
        },
    )


def extract_text_from_response(content: Any) -> str:
    """Concatenate the text blocks from a (possibly tool-using) Anthropic response.

    When ``web_search`` is enabled, ``response.content`` is a list of block
    dicts (``text``, ``server_tool_use``, ``web_search_tool_result``). Only the
    ``text`` blocks carry the final answer; everything else is internal trace.
    """
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)

    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts)


def extract_sources_from_response(content: Any) -> list[str]:
    """Collect unique citation URLs from text-block citations and tool results."""
    if not isinstance(content, list):
        return []

    urls: set[str] = set()
    for block in content:
        if not isinstance(block, dict):
            continue

        if block.get("type") == "text":
            for citation in block.get("citations", []) or []:
                if isinstance(citation, dict):
                    url = citation.get("url")
                    if url:
                        urls.add(url)

        if block.get("type") == "web_search_tool_result":
            for result in block.get("content", []) or []:
                if isinstance(result, dict):
                    url = result.get("url")
                    if url:
                        urls.add(url)

    return sorted(urls)


def did_use_web_search(response: Any) -> bool:
    """Check ``response_metadata.usage.server_tool_use.web_search_requests > 0``."""
    metadata = getattr(response, "response_metadata", {}) or {}
    usage = metadata.get("usage", {}) or {}
    server_tool_use = usage.get("server_tool_use", {}) or {}
    return server_tool_use.get("web_search_requests", 0) > 0


def inject_fallback_disclaimer_if_missing(response: str, used_fallback: bool) -> str:
    """Force the medical-referral disclaimer onto fallback responses.

    Defence-in-depth: the prompt already instructs the LLM to include the
    disclaimer, but we re-check here in case the model drops it. If the
    response already contains the equivalent referral language, leave it alone.
    """
    if not used_fallback:
        return response

    has_medical_referral = "의료진" in response or "영양사" in response
    has_ai_disclaimer = "AI" in response and ("추정" in response or "검색" in response)

    if has_medical_referral and has_ai_disclaimer:
        return response

    return f"{response}\n\n{GRAPH_FALLBACK_DISCLAIMER}"


def build_fallback_prompt(
    query: str,
    user_profile: str,
    lifecycle_context: str,
    graph_context: str,
) -> str:
    """Unified prompt: graph context (possibly empty) + delegation to web_search.

    When graph_context is non-empty, the model is told to prefer it. When
    empty, the model is told the food/concept is outside the domain graph and
    should use ``web_search`` for trend / slang / regional items. The model
    decides — there is no client-side heuristic.
    """
    parts = [
        "당신은 웰다의 혈당 관리 코치입니다.",
        "",
        f"사용자 프로필: {user_profile}",
        f"라이프사이클 단계: {lifecycle_context}",
        "",
    ]

    if graph_context.strip():
        parts.extend(
            [
                "도메인 데이터:",
                graph_context,
                "",
                "도메인 데이터가 사용자 질문에 충분히 답할 수 있으면 그 데이터만 사용하세요.",
                "도메인 데이터에 없는 신조어, 트렌드 음식, 지역 음식이라면 web_search tool로 정보를 가져오세요.",
            ]
        )
    else:
        parts.extend(
            [
                "도메인 데이터에 해당 음식이나 개념이 없습니다.",
                "신조어, 트렌드 음식, 지역 음식 같은 경우 web_search tool을 사용해 정확한 정보를 가져오세요.",
                "일반적인 영양 지식만으로 답변 가능하면 web_search 없이 답변하세요.",
            ]
        )

    parts.extend(
        [
            "",
            f"사용자 질문: {query}",
            "",
            "답변 시 주의사항:",
            "- 합쇼체로 답변하세요 (-습니다/-십니다)",
            "- 이모지 사용 금지",
            "- 사용자 라이프사이클 단계를 의식한 답변",
            "- 의학적 자문이 필요한 사안은 반드시 의료진 상담 권유",
            "- 도메인 데이터에 없는 정보를 추정하거나 web_search 결과로 답변한 경우, 응답 마지막에 다음 disclaimer를 반드시 포함:",
            f'  "{GRAPH_FALLBACK_DISCLAIMER}"',
        ]
    )

    return "\n".join(parts)
