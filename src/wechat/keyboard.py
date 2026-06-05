"""Shared keyboard simulation helpers via Win32 keybd_event.

These are used by window_controller to inject keystrokes into the
foreground window.
"""

import ctypes
import time


def press_key(vk: int) -> None:
    """Send one key press/release to the foreground window."""
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.03)
    ctypes.windll.user32.keybd_event(vk, 0, 2, 0)


def send_combo(mod_vk: int, key_vk: int) -> None:
    """Send a modifier+key combo (e.g. Ctrl+F) to the foreground window."""
    ctypes.windll.user32.keybd_event(mod_vk, 0, 0, 0)
    time.sleep(0.03)
    ctypes.windll.user32.keybd_event(key_vk, 0, 0, 0)
    time.sleep(0.03)
    ctypes.windll.user32.keybd_event(key_vk, 0, 2, 0)
    time.sleep(0.03)
    ctypes.windll.user32.keybd_event(mod_vk, 0, 2, 0)
