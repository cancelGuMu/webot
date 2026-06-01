"""WeChat backend abstraction and factory.

Usage:
    from .wechat import create_wechat_backend

    backend = create_wechat_backend(config, groups)
    backend.start(message_callback)
"""

from .base import AbstractWeChatBackend, MessageCallback

__all__ = [
    "AbstractWeChatBackend",
    "MessageCallback",
]
