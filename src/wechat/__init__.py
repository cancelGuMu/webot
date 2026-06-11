"""WeChat backend abstraction.

The factory for creating backend instances lives on Bot._create_wechat_backend()
in src/bot.py. New backends implement AbstractWeChatBackend from .base.
"""

from .base import AbstractWeChatBackend, MessageCallback

__all__ = [
    "AbstractWeChatBackend",
    "MessageCallback",
]
