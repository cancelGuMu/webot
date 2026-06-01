"""Web search utility for AI chat context enrichment.

Uses DuckDuckGo via the ddgs library (free, no API key).
Gracefully degrades on failure — returns empty string so the chat flow
is never blocked by search issues.
"""

import logging

logger = logging.getLogger(__name__)

# Try ddgs first (new name), fall back to duckduckgo_search (old name)
try:
    from ddgs import DDGS
    HAS_DDGS = True
except ImportError:
    try:
        from duckduckgo_search import DDGS  # type: ignore[no-redef]
        HAS_DDGS = True
    except ImportError:
        HAS_DDGS = False
        logger.warning(
            "ddgs not installed. Web search disabled. "
            "Install with: pip install ddgs"
        )


def search_web(query: str, max_results: int = 3, timeout: float = 5.0) -> str:
    """Search the web for a query and return formatted text results.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return (default 3).
        timeout: Max seconds to wait for search (default 5).

    Returns:
        Formatted search results as a string, or empty string if search
        fails or duckduckgo_search is not installed.
    """
    if not HAS_DDGS:
        return ""

    if not query or not query.strip():
        return ""

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(
                query.strip(),
                max_results=max_results,
                timelimit=str(timeout),
            ))
    except Exception as e:
        logger.info("Web search failed for '%s': %s", query[:60], e)
        return ""

    if not results:
        logger.info("Web search: no results for '%s'", query[:60])
        return ""

    logger.info(
        "Web search for '%s': %d results in %.1fs",
        query[:60], len(results), timeout,
    )

    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "").strip()
        body = r.get("body", "").strip()
        href = r.get("href", "").strip()

        if not title and not body:
            continue

        # Trim long bodies for token efficiency
        if len(body) > 200:
            body = body[:197] + "..."

        lines.append(f"{i}. {title}")
        if body:
            lines.append(f"   {body}")
        if href:
            lines.append(f"   来源: {href}")

    if not lines:
        return ""

    return "\n".join(lines)
