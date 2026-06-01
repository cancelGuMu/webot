"""WeChat backend abstraction."""

from abc import ABC, abstractmethod
from typing import Callable, Optional

# The callback receives a standardized message dict:
# {
#   message_id: str,       # WeChat-internal message ID
#   chat_id: str,          # Chatroom ID (e.g. "123456@chatroom")
#   group_name: str,       # Display name of the group (e.g. "摸鱼群")
#   sender_id: str,        # Sender's wxid
#   sender_name: str,      # Display name
#   content: str,          # Text content (or "[图片]", "[语音]", etc.)
#   msg_type: int,         # 1=text, 3=image, 34=voice, 47=emoji, 49=link/app
#   timestamp: int,        # Unix epoch seconds
#   is_at_mentioned: bool, # Whether the bot was @mentioned
#   is_group: bool,        # Whether this is a group chat
# }
MessageCallback = Callable[[dict], Optional[str]]


class AbstractWeChatBackend(ABC):
    """Abstract base class for WeChat backends.

    To add a new backend (e.g. Gewechat), implement these three methods
    in a new module. Nothing else in the codebase needs to change.
    """

    @abstractmethod
    def start(self, callback: MessageCallback) -> None:
        """Start listening for messages. Blocks until stop() is called.

        Args:
            callback: Called with a standardized message dict for each
                      incoming group message.
        """
        ...

    @abstractmethod
    def send_text(self, chat_id: str, content: str) -> bool:
        """Send a text message to a chat.

        Args:
            chat_id: The chatroom or user ID.
            content: The plain text content to send.

        Returns:
            True on success, False on failure.
        """
        ...

    @abstractmethod
    def stop(self) -> None:
        """Signal the listener loop to exit gracefully."""
        ...
