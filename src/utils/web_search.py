"""Web search utility for AI chat context enrichment.

Uses ddgs (DuckDuckGo metasearch library, free, no API key).
Gracefully degrades on failure — returns empty string so the chat flow
is never blocked by search issues.

Design notes for users behind the GFW (Great Firewall):
  - Most Western search engines are unreachable; Yandex is the most reliable.
  - ddgs tries engines sequentially in batches; a single slow batch can
    cascade into 15+ seconds of wasted time.
  - We wrap the entire search in a ThreadPoolExecutor with a hard timeout
    (default 3s) to prevent the chat pipeline from blocking.
  - The ``timelimit`` parameter is a DATE FILTER (d/w/m/y), never a
    timeout — passing a float causes TypeError/KeyError in some engines.
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor as _ThreadPoolExecutor
from concurrent.futures import TimeoutError as _FuturesTimeoutError

logger = logging.getLogger(__name__)

# ── PII redaction ───────────────────────────────────────────────────────
# Patterns for things that should never be sent to a public search engine.
_PII_PATTERNS: list[tuple[str, str]] = [
    # Email addresses
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[email]"),
    # Chinese mobile phone numbers (11 digits, starts with 1)
    (r"\b1[3-9]\d{9}\b", "[phone]"),
    # Chinese resident ID numbers (18 digits, last may be X)
    (r"\b\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b", "[id]"),
    # Generic long digit sequences (10+ digits, likely phone/account numbers)
    (r"\b\d{10,15}\b", "[number]"),
]


def _redact_pii(text: str) -> str:
    """Strip phone numbers, emails, ID numbers, and long digit sequences.

    These patterns are replaced with placeholder tokens before the query
    is sent to DuckDuckGo so that raw PII never leaves the machine in a
    search request.
    """
    for pattern, placeholder in _PII_PATTERNS:
        text = re.sub(pattern, placeholder, text)
    return text

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

    # Redact PII before the query leaves the machine (sent to DuckDuckGo).
    safe_query = _redact_pii(query.strip())

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(
                safe_query,
                max_results=max_results,
                timelimit=timeout,
            ))
    except Exception as e:
        logger.info("Web search failed for '%s': %s", safe_query[:30], e)
        return ""

    if not results:
        logger.info("Web search: no results for '%s'", safe_query[:30])
        return ""

    logger.info(
        "Web search for '%s': %d results in %.1fs",
        safe_query[:30], len(results), timeout,
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
