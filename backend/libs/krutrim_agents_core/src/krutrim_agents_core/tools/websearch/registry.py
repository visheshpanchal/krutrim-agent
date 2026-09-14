"""Selects which web-search tool a profile's default `web_search` export resolves to.

The `web_search` export is built once at import time, so it can't vary per
user; pass an explicit `provider` to pin one, otherwise it resolves to the
built-in default. `TAVILY_API_KEY` is what actually enables Tavily.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .tavily import tavily_search

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

_DEFAULT_PROVIDER = "tavily"

SEARCH_PROVIDERS: dict[str, BaseTool] = {
    "tavily": tavily_search,
}


def get_web_search_tool(provider: str | None = None) -> BaseTool:
    return SEARCH_PROVIDERS.get(provider or _DEFAULT_PROVIDER, tavily_search)
