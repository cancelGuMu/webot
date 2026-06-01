#!/usr/bin/env python
"""WeChat UIA Diagnostic — aggressive tree inspection for 4.1.9+.

Usage: python diagnose_wechat.py
"""

import ctypes
import sys
from pathlib import Path

import uiautomation as uia
import win32gui
import win32con

OUTPUT = Path(__file__).resolve().parent / "data" / "uia_dump.txt"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

# ── Find WeChat window ────────────────────────────────────────────

def find_hwnd():
    candidates = []
    def _enum(hwnd, _):
        try:
            t = win32gui.GetWindowText(hwnd) or ""
            c = win32gui.GetClassName(hwnd) or ""
            if ("微信" in t or c.startswith("Qt")) and win32gui.IsWindowVisible(hwnd):
                candidates.append((hwnd, t, c))
        except Exception:
            pass
        return True
    win32gui.EnumWindows(_enum, None)
    if not candidates:
        for cls in ("Qt51514QWindowIcon","Qt51414QWindowIcon","Qt516QWindowIcon"):
            h = win32gui.FindWindow(cls, None)
            if h: candidates.append((h, "", cls))
    if not candidates:
        h = win32gui.FindWindow(None, "微信")
        if h: candidates.append((h, "微信", ""))
    return candidates[0] if candidates else None

# ── Aggressive tree dump ──────────────────────────────────────────

def dump_node(ctrl, depth=0, max_depth=8, lines=None, max_lines=3000):
    if lines is None:
        lines = []
    if depth > max_depth or len(lines) >= max_lines:
        return lines
    indent = "  " * depth
    try:
        name = str(ctrl.Name or "")[:120]
    except Exception:
        name = "<err>"
    try:
        cls = str(ctrl.ClassName or "")[:80]
    except Exception:
        cls = "<err>"
    try:
        ct = str(ctrl.ControlTypeName or "")[:40]
    except Exception:
        ct = "<err>"
    try:
        aid = str(ctrl.AutomationId or "")[:60]
    except Exception:
        aid = "<err>"
    try:
        r = ctrl.BoundingRectangle
        rect = f"{r.left},{r.top} {r.right-r.left}x{r.bottom-r.top}" if r else ""
    except Exception:
        rect = ""
    try:
        is_enabled = ctrl.IsEnabled
    except Exception:
        is_enabled = "?"
    try:
        is_offscreen = ctrl.IsOffscreen
    except Exception:
        is_offscreen = "?"

    lines.append(
        f"{indent}[{ct}] Name='{name}' Class='{cls}' "
        f"AutoId='{aid}' Rect=({rect}) Enabled={is_enabled} Offscreen={is_offscreen}"
    )

    try:
        children = ctrl.GetChildren()
    except Exception:
        children = []
    for ch in children:
        dump_node(ch, depth + 1, max_depth, lines, max_lines)
        if len(lines) >= max_lines:
            break
    return lines


# ── Main ──────────────────────────────────────────────────────────

def main():
    print("WeChat UIA Diagnostic Tool")
    print("=" * 50)

    r = find_hwnd()
    if not r:
        print("ERROR: WeChat window not found")
        sys.exit(1)
    hwnd, title, cls = r

    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    win32gui.SetForegroundWindow(hwnd)

    print(f"HWND={hwnd}, Title='{title}', Class='{cls}'")
    print()

    # Strategy 1: Get root via ControlFromHandle
    root = uia.ControlFromHandle(hwnd)
    if root is None:
        print("ERROR: ControlFromHandle returned None")
        sys.exit(1)

    lines = dump_node(root, max_depth=8, max_lines=5000)
    node_count = len(lines)

    print(f"Tree nodes via ControlFromHandle: {node_count}")

    # Strategy 2: Try getting root via GetRootElement
    try:
        desktop = uia.GetRootControl()
        wechat = None
        for c, d in uia.WalkControl(desktop, maxDepth=3):
            try:
                if c.NativeWindowHandle == hwnd:
                    wechat = c
                    break
            except Exception:
                pass
        if wechat:
            lines2 = dump_node(wechat, max_depth=8, max_lines=5000)
            print(f"Tree nodes via GetRootControl: {len(lines2)}")
            if len(lines2) > len(lines):
                lines = lines2
                node_count = len(lines2)
    except Exception as e:
        print(f"Strategy 2 failed: {e}")

    # Strategy 3: Try with AutomationElement.FromHandle via comtypes
    try:
        import comtypes.client
        from comtypes.gen.UIAutomationClient import (
            CUIAutomation, IUIAutomation,
            TreeScope_Descendants,
        )
        uiac = comtypes.client.CreateObject(CUIAutomation, interface=IUIAutomation)
        el = uiac.ElementFromHandle(hwnd)
        if el:
            # Try getting first-level children via COM
            walker = uiac.ControlViewWalker
            child = walker.GetFirstChildElement(el)
            com_children = 0
            while child:
                com_children += 1
                try:
                    cn = child.CurrentName or ""
                    cc = child.CurrentClassName or ""
                    ct = child.CurrentControlType
                    print(f"  COM child[{com_children}]: Name='{cn[:80]}' Class='{cc[:60]}' Type={ct}")
                except Exception:
                    print(f"  COM child[{com_children}]: <error reading>")
                child = walker.GetNextSiblingElement(child)
            print(f"COM direct children: {com_children}")
    except Exception as e:
        print(f"COM strategy failed: {e}")

    # Write full dump
    header = f"# HWND={hwnd} Title={title} Class={cls}\n# Nodes={node_count}\n\n"
    OUTPUT.write_text(header + "\n".join(lines), encoding="utf-8")

    # Show summary
    ct_count = {}
    for line in lines:
        ct = line.split("]")[0].split("[")[-1] if "[" in line else "?"
        ct_count[ct] = ct_count.get(ct, 0) + 1

    print()
    print("Control types found:")
    for ct, cnt in sorted(ct_count.items(), key=lambda x: -x[1]):
        print(f"  {ct:30s} x{cnt}")

    print(f"\nFull dump: {OUTPUT}")
    print(f"Total nodes: {node_count}")


if __name__ == "__main__":
    main()
