"""Raw UIAutomation backend for WeChat 4.1.x+.

Bypasses wx4py to work directly with the uiautomation library.
Designed to be version-agnostic — uses flexible element matching
rather than hardcoded selector paths.

Architecture:
    1. Window connection: win32gui to find/hwnd, uiautomation for UIA tree
    2. Message polling: iterate group chats, scan message panels
    3. Message sending: clipboard-based (most reliable across versions)
    4. Error recovery: auto-retry with backoff, reconnect on window loss
"""

import logging
import time
import threading
from pathlib import Path
from typing import Optional

# ── UIA imports (try multiple paths) ──────────────────────────────
try:
    import uiautomation as _uia
except ImportError:
    try:
        from wx4py.core import uiautomation as _uia  # noqa: F401
    except ImportError:
        _uia = None  # type: ignore

try:
    import win32gui
    import win32con
    import win32clipboard
    import win32process
except ImportError:
    win32gui = None  # type: ignore

# COM-level UIAutomation client (for tree wake-up)
try:
    import comtypes.client as _cc
    from comtypes.gen.UIAutomationClient import (
        CUIAutomation as _CUIAutomation,
        IUIAutomation as _IUIAutomation,
        IUIAutomationElement as _IUIAutomationElement,
        IUIAutomationEventHandler as _IUIAutomationEventHandler,
        UIA_StructureChangedEventId as _UIA_StructureChangedEventId,
        TreeScope_Descendants as _TreeScope_Descendants,
    )
    _COM_UIA_AVAILABLE = True
except (ImportError, AttributeError):
    _COM_UIA_AVAILABLE = False
    _cc = None  # type: ignore
    _CUIAutomation = None  # type: ignore
    _IUIAutomation = None  # type: ignore
    _IUIAutomationElement = None  # type: ignore

from .base import AbstractWeChatBackend, MessageCallback
from .helpers import DedupSet, generate_message_id

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────

# How long to wait for UIA operations (seconds)
UIA_TIMEOUT = 3.0
# How often to poll for new messages (seconds)
DEFAULT_POLL_SEC = 1.0
# Max retries for transient UIA errors
MAX_RETRIES = 3
# Retry backoff base (seconds)
RETRY_BASE = 2.0
# Max dedup set size
MAX_DEDUP_SIZE = 5000
# Minimum UIA tree nodes for healthy WeChat
MIN_UIA_NODES = 10


# ── Window discovery ──────────────────────────────────────────────

def _find_wechat_hwnd() -> Optional[int]:
    """Find the WeChat main window handle using multiple strategies.

    Returns:
        HWND (int) or None if no WeChat window found.
    """
    if win32gui is None:
        return None

    candidates = []

    def _enum(hwnd, _ctx):
        try:
            title = win32gui.GetWindowText(hwnd) or ""
            cls = win32gui.GetClassName(hwnd) or ""
            if not win32gui.IsWindowVisible(hwnd):
                return True
        except Exception:
            return True

        score = 0
        if "微信" in title:
            score += 100
        if cls.startswith("Qt"):
            score += 50
        if "WeChat" in cls:
            score += 40

        if score > 0:
            candidates.append((score, hwnd, title, cls))
        return True

    try:
        win32gui.EnumWindows(_enum, None)
    except Exception:
        pass

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    # Fallback: common class names
    for cls in ("Qt51514QWindowIcon", "Qt51414QWindowIcon",
                "Qt516QWindowIcon"):
        hwnd = win32gui.FindWindow(cls, None)
        if hwnd:
            return hwnd

    return win32gui.FindWindow(None, "微信")


def _get_wechat_pid(hwnd: int) -> Optional[int]:
    """Get the process ID for a window handle."""
    if win32process is None:
        return None
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return pid
    except Exception:
        return None


# ── UIA helpers ───────────────────────────────────────────────────

def _safe_call(fn, *args, default=None, **kwargs):
    """Call a UIA function, returning default on any exception."""
    try:
        return fn(*args, **kwargs)
    except Exception:
        return default


def _get_control_text(ctrl) -> str:
    """Safely read control text (Name or text content)."""
    for attr in ("Name", "LegacyIAccessiblePattern.Name", "Value"):
        val = _safe_call(getattr, ctrl, attr, default="")
        val = str(val).strip() if val else ""
        if val:
            return val
    return ""


def _find_descendant(ctrl, *, name_contains=None,
                     class_name=None, ctrl_type=None,
                     auto_id=None, max_depth=6, timeout=UIA_TIMEOUT):
    """Find a descendant UIA element matching criteria.

    Args:
        ctrl: Root UIA control.
        name_contains: Substring to match in element name.
        class_name: Exact ClassName match.
        ctrl_type: Exact ControlType match.
        auto_id: Exact AutomationId match.
        max_depth: Maximum search depth.
        timeout: Max search time in seconds.

    Returns:
        Matching control or None.
    """
    if _uia is None:
        return None

    deadline = time.time() + timeout

    def _match(c):
        if name_contains and name_contains not in _get_control_text(c):
            return False
        if class_name and _safe_call(getattr, c, "ClassName", default="") != class_name:
            return False
        if ctrl_type and _safe_call(getattr, c, "ControlTypeName", default="") != ctrl_type:
            return False
        if auto_id and _safe_call(getattr, c, "AutomationId", default="") != auto_id:
            return False
        return True

    while time.time() < deadline:
        try:
            for child, depth in _uia.WalkControl(
                ctrl, includeTop=True, maxDepth=max_depth
            ):
                if _match(child):
                    return child
        except Exception:
            pass
        time.sleep(0.1)

    return None


def _find_all_descendants(ctrl, *, name_contains=None,
                          class_name=None, ctrl_type=None,
                          max_depth=5, limit=20, timeout=UIA_TIMEOUT):
    """Find all matching descendants."""
    results = []
    if _uia is None:
        return results

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            for child, depth in _uia.WalkControl(
                ctrl, includeTop=False, maxDepth=max_depth
            ):
                match = True
                if name_contains and name_contains not in _get_control_text(child):
                    match = False
                if class_name and _safe_call(getattr, child, "ClassName", default="") != class_name:
                    match = False
                if ctrl_type and _safe_call(getattr, child, "ControlTypeName", default="") != ctrl_type:
                    match = False
                if match:
                    results.append(child)
                    if len(results) >= limit:
                        return results
            break
        except Exception:
            time.sleep(0.1)

    return results


def _count_uia_nodes(ctrl, limit=100) -> int:
    """Quick node count for health check."""
    count = 0
    stack = [ctrl]
    while stack and count < limit:
        node = stack.pop()
        count += 1
        children = _safe_call(node.GetChildren, default=[])
        stack.extend(reversed(children) if children else [])
    return count


# ── Message representation ────────────────────────────────────────

class _ChatMessage:
    """Internal representation of a parsed chat message."""
    __slots__ = ("sender", "content", "timestamp", "is_self", "raw_text")

    def __init__(self, sender="", content="", timestamp=0.0,
                 is_self=False, raw_text=""):
        self.sender = sender
        self.content = content
        self.timestamp = timestamp or time.time()
        self.is_self = is_self
        self.raw_text = raw_text


# ── UIA Backend ───────────────────────────────────────────────────

class UiaBackend(AbstractWeChatBackend):
    """Production UIAutomation backend for WeChat 4.x.

    Connects directly to WeChat's UIA tree without wx4py dependency.
    Uses flexible element matching to adapt across minor WeChat versions.

    Usage:
        backend = UiaBackend(
            bot_display_name="MyBot",
            groups=["Work Chat", "Friends"],
            poll_sec=1.0,
        )
        backend.start(my_callback)
    """

    def __init__(self,
                 bot_display_name: str = "",
                 groups: list[str] | None = None,
                 poll_sec: float = DEFAULT_POLL_SEC,
                 data_dir: str = "data"):
        """Initialize UIA backend.

        Args:
            bot_display_name: Bot's WeChat display name (for self-filtering).
            groups: Group chat names to monitor.
            poll_sec: Seconds between message polls.
            data_dir: Directory for diagnostic dumps.
        """
        self._bot_name = bot_display_name
        self._groups = groups or []
        self._poll_sec = poll_sec
        self._data_dir = Path(data_dir)

        # Runtime state
        self._running = False
        self._hwnd: Optional[int] = None
        self._uia_root = None
        self._known_ids = DedupSet(max_size=5000)
        self._connect_retries = 0
        self._max_connect_retries = 10

    # ── Public API ─────────────────────────────────────────────────

    def start(self, callback: MessageCallback) -> None:
        """Start the message polling loop. Blocks until stop() is called."""
        if _uia is None or win32gui is None:
            logger.error(
                "Required libraries not installed. Run: "
                "pip install uiautomation pywin32"
            )
            return

        if not self._groups:
            logger.error(
                "No groups configured. Set WECHAT_GROUPS in .env"
            )
            return

        self._running = True
        logger.info(
            f"UiaBackend starting "
            f"(groups={self._groups}, poll={self._poll_sec}s, "
            f"bot='{self._bot_name}')"
        )

        # Auto-detect bot name
        if not self._bot_name:
            self._bot_name = self._detect_self_name()

        try:
            self._connect()
        except Exception as e:
            logger.error(f"Failed to connect to WeChat: {e}")
            return

        # Main polling loop
        consecutive_errors = 0
        while self._running:
            try:
                self._poll_cycle(callback)
                consecutive_errors = 0
            except KeyboardInterrupt:
                break
            except Exception as e:
                consecutive_errors += 1
                wait = min(2 ** min(consecutive_errors, 5), 30)
                logger.warning(
                    f"Poll error (consecutive={consecutive_errors}): {e}. "
                    f"Retrying in {wait}s..."
                )
                time.sleep(wait)

                # Attempt reconnection on persistent errors
                if consecutive_errors >= 3:
                    try:
                        self._connect()
                    except Exception:
                        pass

        self._cleanup()
        logger.info("UiaBackend stopped.")

    def send_text(self, chat_id: str, content: str) -> bool:
        """Send a text message to a group chat.

        Strategy:
        1. Navigate to the group chat
        2. Paste content into input area
        3. Click send or press Enter
        """
        if not self._running:
            return False

        for attempt in range(MAX_RETRIES):
            try:
                return self._send_text_impl(chat_id, content)
            except Exception as e:
                wait = RETRY_BASE ** attempt
                logger.warning(
                    f"Send failed (attempt {attempt + 1}/{MAX_RETRIES}): "
                    f"{e}. Waiting {wait}s..."
                )
                time.sleep(wait)

        logger.error(f"Failed to send message after {MAX_RETRIES} attempts")
        return False

    def stop(self) -> None:
        """Signal the main loop to stop."""
        self._running = False

    # ── Connection management ──────────────────────────────────────

    def _connect(self) -> None:
        """Connect to the WeChat window, wake up the UIA tree, and init UIA.

        WeChat 4.1.x uses Qt with on-demand accessibility: the UIA tree stays
        as a 2-node skeleton until a legitimate UIA client connects and
        subscribes to events. We force the tree to populate by:
        1. Getting the root element
        2. Subscribing to a StructureChanged event (signals "real client")
        3. Repeatedly polling until the tree expands beyond skeleton nodes
        """
        self._connect_retries += 1

        # ── Step 1: Find window ─────────────────────────────────
        hwnd = _find_wechat_hwnd()
        if not hwnd:
            raise RuntimeError(
                "WeChat window not found. Is WeChat running and logged in?"
            )

        title = _safe_call(win32gui.GetWindowText, hwnd, default="")
        cls = _safe_call(win32gui.GetClassName, hwnd, default="")
        logger.info(
            f"Found WeChat: HWND={hwnd}, Title='{title}', Class='{cls}'"
        )

        # ── Step 2: Activate (not minimized) ────────────────────
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        time.sleep(0.5)

        # ── Step 3: Get root element ────────────────────────────
        root = _uia.ControlFromHandle(hwnd)
        if root is None:
            raise RuntimeError(
                "UIA root element is None.\n"
                "The Qt accessibility bridge is not providing ANY data.\n\n"
                "Fixes (try in order):\n"
                "  1. Restart WeChat completely (close, reopen, log in)\n"
                "  2. Run this program as Administrator (once)\n"
                "  3. Check Windows Settings > Accessibility > turn ON "
                "Narrator briefly, then turn OFF\n"
                "  4. Run: python diagnose_wechat.py"
            )

        # ── Step 4: Wake up the UIA tree ────────────────────────
        # WeChat 4.1.x+ only builds the full tree when a UIA client
        # subscribes to events. We force registration by subscribing
        # to StructureChanged, then polling until the tree expands.
        logger.info("Waking up WeChat UIA tree...")

        self._register_uia_client(root)

        # Poll with backoff until tree populates
        node_count = 0
        for attempt in range(10):
            time.sleep(0.5)
            node_count = _count_uia_nodes(root, limit=200)
            logger.debug(
                f"Tree wake-up attempt {attempt + 1}/10: "
                f"{node_count} nodes"
            )
            if node_count >= MIN_UIA_NODES:
                break

        if node_count < MIN_UIA_NODES:
            # Try one more thing: set screen reader flag + re-fetch
            self._force_screen_reader_flag()
            time.sleep(1.0)
            # Re-get root (handle may have changed)
            root = _uia.ControlFromHandle(hwnd)
            if root is None:
                raise RuntimeError(
                    "UIA root lost after screen reader flag set."
                )
            node_count = _count_uia_nodes(root, limit=200)

        logger.info(
            f"WeChat connected: HWND={hwnd}, UIA nodes={node_count}"
        )

        if node_count < MIN_UIA_NODES:
            raise RuntimeError(
                f"UIA tree did not populate ({node_count} nodes).\n"
                f"WeChat 4.1.x requires a UIA client subscription to "
                f"expose the full widget tree. Tried for 5+ seconds.\n\n"
                f"Last resort fixes:\n"
                f"  1. Close WeChat completely\n"
                f"  2. Open Windows Narrator (Win+Ctrl+Enter)\n"
                f"  3. Start WeChat and log in\n"
                f"  4. Close Narrator\n"
                f"  5. Run this program again\n\n"
                f"Or run: python diagnose_wechat.py for diagnostics"
            )

        self._hwnd = hwnd
        self._uia_root = root
        self._connect_retries = 0

    @staticmethod
    def _register_uia_client(root) -> None:
        """Register as a UIAutomation client using COM-level event subscription.

        WeChat 4.1.x+ Qt framework checks whether a real UIA client
        (screen reader, automation tool) has subscribed to events
        before building the full accessibility tree.

        We use comtypes to create a CUIAutomation → ElementFromHandle →
        subscribe to StructureChanged event. This is the exact pattern
        that triggers Qt's accessibility bridge.
        """
        if not _COM_UIA_AVAILABLE:
            logger.debug("COM UIA not available, skipping client registration")
            return

        try:
            # Create the UIAutomation COM client
            uia_client = _cc.CreateObject(
                _CUIAutomation,
                interface=_IUIAutomation,
            )

            # Get the element for our hwnd through COM
            hwnd = _safe_call(getattr, root, "NativeWindowHandle", default=0)
            if not hwnd:
                hwnd = _safe_call(lambda: root.CurrentNativeWindowHandle, default=0)
            if not hwnd:
                logger.debug("Could not get HWND from root element for COM reg")
                return

            element = uia_client.ElementFromHandle(hwnd)
            if not element:
                return

            # Define a minimal event handler
            class _TreeWakeHandler(_cc.COMObject):
                _com_interfaces_ = [
                    _IUIAutomationElement,  # placeholder; real handler below
                ]

            # We use the pre-imported COM types

            class _EventHandler(_cc.COMObject):
                _com_interfaces_ = [_IUIAutomationEventHandler]

                def HandleAutomationEvent(self, sender, eventId):
                    pass  # No-op — we just need the subscription to exist

                def HandleStructureChangedEvent(self, sender, changeType, runtimeId):
                    pass

            handler = _EventHandler()

            # Subscribe — this is the key call that wakes up Qt
            uia_client.AddAutomationEventHandler(
                _UIA_StructureChangedEventId,
                element,
                _TreeScope_Descendants,
                None,  # cacheRequest
                handler,
            )
            logger.debug(
                "COM UIA client registered with StructureChanged handler"
            )
        except Exception as e:
            logger.debug(f"COM UIA client registration failed: {e}")

    @staticmethod
    def _force_screen_reader_flag() -> bool:
        """Set the Windows screen reader flag via SystemParametersInfo.

        WeChat 4.x checks this flag at startup to decide whether to
        enable Qt accessibility. Setting it here and restarting WeChat
        can fix persistent empty-tree issues.
        """
        try:
            import ctypes
            SPI_SETSCREENREADER = 0x0047
            SPIF_UPDATEINIFILE = 0x01
            SPIF_SENDCHANGE = 0x02
            result = ctypes.windll.user32.SystemParametersInfoW(
                SPI_SETSCREENREADER, 1, 0,
                SPIF_UPDATEINIFILE | SPIF_SENDCHANGE,
            )
            if result:
                logger.info("Screen reader flag set (SPI_SETSCREENREADER)")
            return bool(result)
        except Exception as e:
            logger.debug(f"Screen reader flag set failed: {e}")
            return False

    def _ensure_connected(self) -> bool:
        """Check connection health, reconnect if needed."""
        if self._hwnd is None or self._uia_root is None:
            try:
                self._connect()
                return True
            except Exception:
                return False

        # Verify window still exists
        try:
            if not win32gui.IsWindow(self._hwnd):
                logger.warning("WeChat window destroyed, reconnecting...")
                try:
                    self._connect()
                    return True
                except Exception:
                    return False
        except Exception:
            pass

        return True

    def _cleanup(self) -> None:
        """Release UIA resources."""
        self._hwnd = None
        self._uia_root = None

    # ── Message polling ────────────────────────────────────────────

    def _poll_cycle(self, callback: MessageCallback) -> None:
        """One poll cycle: scan configured groups for new messages."""
        if not self._ensure_connected():
            time.sleep(self._poll_sec)
            return

        for group_name in self._groups:
            if not self._running:
                break
            try:
                self._poll_group(group_name, callback)
            except Exception as e:
                logger.debug(f"Error polling group '{group_name}': {e}")

        time.sleep(self._poll_sec)

    def _poll_group(self, group_name: str,
                    callback: MessageCallback) -> None:
        """Poll a single group chat for new messages."""
        # Navigate to the group
        if not self._navigate_to_chat(group_name):
            return

        time.sleep(0.2)

        # Read messages from the message panel
        messages = self._read_message_panel()
        if not messages:
            return

        # Process each message
        for msg in messages:
            if not self._running:
                break

            # Generate stable ID
            msg_id = generate_message_id(
                group_name, msg.sender, msg.content, msg.timestamp)

            # Dedup
            if msg_id in self._known_ids:
                continue
            self._known_ids.add(msg_id)

            # Skip bot's own messages
            if self._bot_name and msg.sender == self._bot_name:
                continue

            # Detect @mention
            is_at = (
                self._bot_name and
                f"@{self._bot_name}" in (msg.content or "")
            )

            # Dispatch to callback
            standardized = self._standardize_message(
                msg, group_name, msg_id, is_at
            )
            reply = callback(standardized)
            if reply:
                self.send_text(group_name, reply)

    # ── Chat navigation ────────────────────────────────────────────

    def _navigate_to_chat(self, chat_name: str) -> bool:
        """Navigate to a specific chat (group or contact) by name via keyboard.

        Primary: Ctrl+F → paste name → Enter (keyboard-only).
        Fallback: UIA find chat in sidebar → Click (mouse, for broken search).
        """
        for attempt in range(MAX_RETRIES):
            try:
                # Strategy 1 (primary): Ctrl+F keyboard search
                self._activate_window()
                time.sleep(0.1)
                self._send_combo(0x11, 0x46)  # Ctrl+F
                time.sleep(0.3)

                # Paste the group name into search
                self._paste_text(chat_name)
                time.sleep(0.5)

                # Press Enter to select first result
                self._press_key(0x0D)  # Enter
                time.sleep(0.3)

                # Tab to ensure input area focus
                self._press_key(0x09)  # Tab
                time.sleep(0.15)

                return True

            except Exception as e:
                logger.debug(
                    "Keyboard navigate attempt %d failed: %s",
                    attempt + 1, e,
                )
                # Strategy 2 (fallback): UIA find chat in sidebar → Click
                try:
                    chat_item = _find_descendant(
                        self._uia_root,
                        name_contains=chat_name,
                        max_depth=5,
                        timeout=1.0,
                    )
                    if chat_item:
                        _safe_call(chat_item.Click)
                        return True
                except Exception:
                    pass

                time.sleep(RETRY_BASE ** attempt)

        logger.warning("Could not navigate to chat: %s", chat_name)
        return False

    def _activate_window(self) -> None:
        """Bring WeChat window to foreground."""
        if self._hwnd is None:
            return
        try:
            win32gui.ShowWindow(self._hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(self._hwnd)
        except Exception:
            pass

    @staticmethod
    def _press_key(vk: int) -> None:
        """Send a key press/release to the foreground window."""
        import ctypes
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.03)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)

    @staticmethod
    def _send_combo(mod_vk: int, key_vk: int) -> None:
        """Send a modifier+key combo (e.g. Ctrl+F) to the foreground window."""
        import ctypes
        ctypes.windll.user32.keybd_event(mod_vk, 0, 0, 0)
        time.sleep(0.03)
        ctypes.windll.user32.keybd_event(key_vk, 0, 0, 0)
        time.sleep(0.03)
        ctypes.windll.user32.keybd_event(key_vk, 0, 2, 0)
        time.sleep(0.03)
        ctypes.windll.user32.keybd_event(mod_vk, 0, 2, 0)

    # ── Message reading ────────────────────────────────────────────

    def _read_message_panel(self) -> list[_ChatMessage]:
        """Read messages currently visible in the chat message panel.

        Scans UIA elements in the message area and parses text content.
        Returns a list of _ChatMessage objects.
        """
        messages = []

        # Find the message list region
        # In WeChat 4.x, messages are typically in a List or Pane control
        # containing Text or Group elements per message
        msg_elements = _find_all_descendants(
            self._uia_root,
            name_contains="",
            ctrl_type="TextControl",
            max_depth=5,
            limit=200,
            timeout=1.5,
        )

        if not msg_elements:
            # Fallback: look for ListItem or Group elements
            msg_elements = _find_all_descendants(
                self._uia_root,
                ctrl_type="ListItemControl",
                max_depth=6,
                limit=200,
                timeout=1.5,
            )

        if not msg_elements:
            # Last resort: scan all leaf text elements
            msg_elements = _find_all_descendants(
                self._uia_root,
                ctrl_type="EditControl",
                max_depth=6,
                limit=100,
                timeout=1.5,
            )

        for elem in msg_elements:
            text = _get_control_text(elem)
            if not text or len(text) < 1:
                continue

            parsed = self._parse_message_text(text)
            if parsed:
                messages.append(parsed)

        return messages

    def _parse_message_text(self, raw: str) -> Optional[_ChatMessage]:
        """Parse a raw text string from the UIA tree into a _ChatMessage.

        WeChat message format is typically:
            SenderName
            Message content

        or in group chats:
            SenderName
            Content line 1
            Content line 2
        """
        raw = raw.strip()
        if not raw:
            return None

        lines = raw.split("\n", 1)
        sender = lines[0].strip()
        content = lines[1].strip() if len(lines) > 1 else ""

        # If the first "line" looks like a whole message (no line break),
        # it might be a system notification — skip those
        if not content:
            # Check if it's a system message
            system_keywords = ("修改群名", "加入了群聊", "退出了群聊",
                               "撤回了一条消息", "被移除")
            if any(kw in sender for kw in system_keywords):
                return None
            # Single-line: might be a notification, or just a short message
            content = sender
            sender = ""

        # Skip very long raw text (not a chat message)
        if len(raw) > 2000:
            return None

        # Try to determine if this is from ourselves
        is_self = bool(self._bot_name and self._bot_name in sender)

        return _ChatMessage(
            sender=sender,
            content=content,
            timestamp=time.time(),
            is_self=is_self,
            raw_text=raw,
        )

    # ── Message sending ────────────────────────────────────────────

    def _send_text_impl(self, _chat_id: str, content: str) -> bool:
        """Send a text message to the currently active chat via keyboard.

        Uses clipboard paste + Enter — no mouse clicks, no UIA element finding.
        The caller must have already navigated to the correct chat and
        ensured input area focus.
        """
        self._activate_window()
        time.sleep(0.1)

        # Paste text via clipboard into the focused input
        self._paste_text(content)
        time.sleep(0.1)

        # Press Enter to send
        try:
            import ctypes
            ctypes.windll.user32.keybd_event(0x0D, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0x0D, 0, 2, 0)
        except Exception:
            pass

        return True

    def _paste_text(self, text: str) -> None:
        """Paste text via the Windows clipboard."""
        if win32clipboard is None:
            return

        # Save current clipboard
        old_data = None
        try:
            win32clipboard.OpenClipboard()
            try:
                old_data = win32clipboard.GetClipboardData(
                    win32clipboard.CF_UNICODETEXT
                )
            except Exception:
                pass
            win32clipboard.CloseClipboard()
        except Exception:
            pass

        # Set our text
        for attempt in range(3):
            try:
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
                win32clipboard.CloseClipboard()
                break
            except Exception:
                time.sleep(0.1)

        # Send Ctrl+V
        try:
            import ctypes
            # Ctrl down
            ctypes.windll.user32.keybd_event(0x11, 0, 0, 0)
            # V down
            ctypes.windll.user32.keybd_event(0x56, 0, 0, 0)
            time.sleep(0.05)
            # V up
            ctypes.windll.user32.keybd_event(0x56, 0, 2, 0)
            # Ctrl up
            ctypes.windll.user32.keybd_event(0x11, 0, 2, 0)
        except Exception:
            pass

        # Restore old clipboard (best effort)
        if old_data:
            try:
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(
                    old_data, win32clipboard.CF_UNICODETEXT
                )
                win32clipboard.CloseClipboard()
            except Exception:
                pass

    # ── Helpers ────────────────────────────────────────────────────

    def _detect_self_name(self) -> str:
        """Try to detect the bot's own WeChat display name."""
        # Look for the "self" user indicator in the sidebar
        # WeChat usually shows "你" or the actual nickname
        self_elem = _find_descendant(
            self._uia_root,
            name_contains="你",
            max_depth=4,
            timeout=0.5,
        )
        if self_elem:
            return ""
        return ""

    def _standardize_message(self, msg: _ChatMessage, chat_id: str,
                              msg_id: str, is_at: bool) -> dict:
        """Convert internal _ChatMessage to the standard message dict."""
        # Try to extract sender_id from sender name
        sender_id = hashlib.md5(
            (msg.sender or "unknown").encode()
        ).hexdigest()[:12]

        return {
            "message_id": msg_id,
            "chat_id": chat_id,
            "sender_id": sender_id,
            "sender_name": msg.sender or "群成员",
            "content": msg.content or msg.raw_text or "",
            "msg_type": 1,  # text
            "timestamp": int(msg.timestamp),
            "is_at_mentioned": is_at,
            "is_group": True,
        }

