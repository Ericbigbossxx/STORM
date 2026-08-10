"""Feishu adapter boundary; no credentials or concrete MCP/API client lives here yet."""

from .ports import FeishuLedgerPort, LedgerObjectRef

__all__ = ["FeishuLedgerPort", "LedgerObjectRef"]
