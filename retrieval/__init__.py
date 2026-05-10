"""
retrieval/__init__.py
======================
Public API for the NIKKO retrieval layer.

Updated 2026-05-10 -- G-RETRIEVAL-01 (Director-directed architectural change):
  HealthdirectAdapter, BetterHealthAdapter, WHOAdapter superseded.
  WebSearchAdapter introduced (sanctioned web search + external fallback).

ADAPTER_PRIORITY_ORDER (REQ-200-071):
    1. PubMedAdapter       -- peer-reviewed, NCBI E-utilities API
    2. WebSearchAdapter    -- grey-lit, sanctioned web scraping + external fallback
"""

from retrieval.pubmed_adapter      import PubMedAdapter
from retrieval.web_search_adapter  import WebSearchAdapter, SANCTIONED_DOMAINS

ADAPTER_PRIORITY_ORDER = [
    PubMedAdapter,
    WebSearchAdapter,
]

__all__ = [
    "PubMedAdapter",
    "WebSearchAdapter",
    "SANCTIONED_DOMAINS",
    "ADAPTER_PRIORITY_ORDER",
]
