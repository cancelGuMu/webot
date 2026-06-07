"""macOS WeChat UI automation backend.

This backend is intentionally separate from the Windows WCDB backend. It uses
macOS application automation as an experimental path for running the bot on
Darwin without importing Windows-only modules.
"""

import logging
import hashlib
import json
import os
import subprocess
import tempfile
import time
import ctypes
from ctypes import c_double, c_int64, c_void_p, Structure
from typing import Optional

from .base import AbstractWeChatBackend, MessageCallback

logger = logging.getLogger(__name__)

DEFAULT_POLL_SEC = 1.0
SEARCH_FIELD_X_OFFSET = 160
SEARCH_FIELD_Y_OFFSET = 28
SEARCH_CLEAR_X_OFFSET = 240
TOP_CHAT_RESULT_Y_OFFSET = 108
GROUP_CHAT_RESULT_Y_OFFSET = 310


class MacUIAutomation:
    """Thin adapter for macOS UI automation commands.

    The concrete automation behavior is implemented incrementally. Keeping it
    behind this class lets tests inject a fake automation object and keeps the
    backend free of Windows imports.
    """

    def __init__(
        self,
        app_name: str | None = None,
        runner=None,
        clicker=None,
        title_reader=None,
        screen_text_reader=None,
    ):
        self._app_name = app_name or os.getenv("MAC_WECHAT_APP_NAME", "WeChat")
        self._custom_runner = runner is not None
        self._runner = runner or self._default_runner
        self._clicker = clicker or self._core_graphics_click
        self._title_reader = title_reader or self._read_current_header_texts
        self._screen_text_reader = screen_text_reader or self._recognize_screen_texts

    @staticmethod
    def _default_runner(cmd, input_text=None, timeout=5):
        try:
            return subprocess.run(
                cmd,
                input=input_text,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return subprocess.CompletedProcess(
                cmd,
                124,
                stdout=exc.stdout or "",
                stderr=f"Command timed out after {timeout}s: {exc}",
            )

    def activate_wechat(self) -> bool:
        return self._bring_wechat_frontmost()

    def open_chat(
        self,
        chat_name: str,
        prefer_group: bool = False,
        sidebar_index: int | None = None,
        expected_title: str | None = None,
        expected_is_group: bool = False,
        require_group_marker: bool = False,
    ) -> bool:
        if not chat_name:
            return False
        if _looks_internal_chat_id(chat_name):
            logger.warning("Refusing to search macOS WeChat with internal chat id: %s", chat_name)
            return False
        if not self._bring_wechat_frontmost():
            return False
        if expected_title and self._current_chat_title_matches(
            expected_title,
            expected_is_group=expected_is_group,
            require_group_marker=require_group_marker,
        ):
            return True
        if sidebar_index is not None:
            opened = self._open_sidebar_chat(sidebar_index)
            if opened and expected_title:
                return self._verify_current_chat_title(
                    expected_title,
                    expected_is_group=expected_is_group,
                    require_group_marker=require_group_marker,
                )
            return opened
        if not self._open_existing_chat_from_search(
            chat_name,
            prefer_group=prefer_group,
            expected_is_group=expected_is_group,
        ):
            return False
        if expected_title:
            if self._verify_current_chat_title(
                expected_title,
                expected_is_group=expected_is_group,
                require_group_marker=require_group_marker,
            ):
                return True
            if not prefer_group and expected_is_group:
                logger.info(
                    "Retrying macOS WeChat search in group result section: %s",
                    chat_name,
                )
                if self._open_existing_chat_from_search(
                    chat_name,
                    prefer_group=True,
                    expected_is_group=expected_is_group,
                ):
                    return self._verify_current_chat_title(
                        expected_title,
                        expected_is_group=expected_is_group,
                        require_group_marker=require_group_marker,
                    )
            return False
        return True

    def _open_sidebar_chat(self, sidebar_index: int) -> bool:
        if sidebar_index < 0 or sidebar_index > 7:
            logger.warning("WeChat sidebar session index is not visible: %s", sidebar_index)
            return False
        geometry = self._get_wechat_geometry()
        window = self._window_rect(geometry)
        if not window:
            logger.warning("Could not locate WeChat main window for sidebar chat open")
            return False
        x = window["x"] + 227
        y = window["y"] + 110 + (sidebar_index * 68)
        if not self._click_screen(x, y):
            return False
        time.sleep(0.25)
        return True

    def _open_existing_chat_from_search(
        self,
        chat_name: str,
        prefer_group: bool = False,
        expected_is_group: bool = False,
    ) -> bool:
        geometry = self._get_wechat_geometry()
        if int(geometry.get("closed_aux_windows", 0) or 0) > 0:
            time.sleep(0.2)
            geometry = self._get_wechat_geometry()
        if self._modal_sheet_rect(geometry):
            if not self._press_escape():
                return False
            time.sleep(0.2)
            geometry = self._get_wechat_geometry()
        window = self._window_rect(geometry)
        if not window:
            logger.warning("Could not locate WeChat main window for existing chat search")
            return False
        if not self._goto_chats_tab():
            logger.warning(
                "Could not switch macOS WeChat to chats tab before search; "
                "will search from current view",
            )
        if not self._replace_search_text(window, chat_name):
            return False
        time.sleep(0.4)

        point = self._find_existing_chat_search_result(
            window,
            chat_name,
            prefer_group=prefer_group,
            expected_is_group=expected_is_group,
        )
        if not point:
            return False
        resolved_title = self._resolved_group_title_from_point(point, chat_name)
        if expected_is_group and resolved_title:
            logger.info(
                "Resolved macOS WeChat search target %r to group title %r",
                chat_name,
                resolved_title,
            )
            if self._replace_search_text(window, resolved_title):
                time.sleep(0.4)
                refined = self._find_existing_chat_search_result(
                    window,
                    resolved_title,
                    prefer_group=prefer_group,
                    expected_is_group=expected_is_group,
                )
                if refined:
                    point = refined
        if not self._click_screen(point["x"], point["y"]):
            return False
        time.sleep(0.25)
        return True

    def _replace_search_text(self, window: dict, text: str) -> bool:
        if not self._click_screen(
            window["x"] + SEARCH_FIELD_X_OFFSET,
            window["y"] + SEARCH_FIELD_Y_OFFSET,
        ):
            return False
        time.sleep(0.1)
        if not self._click_screen(
            window["x"] + SEARCH_CLEAR_X_OFFSET,
            window["y"] + SEARCH_FIELD_Y_OFFSET,
        ):
            return False
        time.sleep(0.1)
        if not self._select_focused_text():
            return False
        time.sleep(0.05)
        if not self._run(["pbcopy"], input_text=text):
            return False
        return self._paste_clipboard(send=False)

    def _find_existing_chat_search_result(
        self,
        window: dict,
        chat_name: str,
        prefer_group: bool = False,
        expected_is_group: bool = False,
    ) -> dict | None:
        rect = self._search_results_capture_rect(window)
        entries = self._screen_text_reader(rect)
        match = self._search_result_match(
            entries,
            chat_name,
            prefer_group=prefer_group,
            expected_is_group=expected_is_group,
        )
        if match:
            point = self._entry_center(match)
            point["resolved_title"] = match.get("text", "")
            return point

        if self._has_search_network_result(entries):
            logger.warning(
                "Refusing to click macOS WeChat network search result for chat: %s",
                chat_name,
            )
            return None

        if expected_is_group or prefer_group:
            logger.warning(
                "Refusing to blind-click macOS WeChat group search result without OCR match: %s",
                chat_name,
            )
            return None

        offset = GROUP_CHAT_RESULT_Y_OFFSET if prefer_group else TOP_CHAT_RESULT_Y_OFFSET
        return {"x": window["x"] + SEARCH_FIELD_X_OFFSET, "y": window["y"] + offset}

    @staticmethod
    def _search_results_capture_rect(window: dict) -> dict:
        return {
            "x": window["x"] + 120,
            "y": window["y"] + 80,
            "w": min(max(window["w"] - 120, 1), 560),
            "h": min(max(window["h"] - 80, 1), 500),
        }

    @classmethod
    def _search_result_click_point(
        cls,
        entries: list[dict],
        chat_name: str,
        prefer_group: bool = False,
        expected_is_group: bool = False,
    ) -> dict | None:
        match = cls._search_result_match(
            entries,
            chat_name,
            prefer_group=prefer_group,
            expected_is_group=expected_is_group,
        )
        return cls._entry_center(match) if match else None

    @classmethod
    def _search_result_match(
        cls,
        entries: list[dict],
        chat_name: str,
        prefer_group: bool = False,
        expected_is_group: bool = False,
    ) -> dict | None:
        target = cls._normalize_title(chat_name)
        if not target:
            return None

        labels = []
        candidates = []
        partial_candidates = []
        for entry in entries or []:
            text = str(entry.get("text") or "").strip()
            normalized = cls._normalize_title(text)
            if not normalized:
                continue
            y = float(entry.get("y", 0))
            item = {**entry, "text": text, "normalized": normalized, "y": y}
            if cls._is_search_section_label(normalized):
                labels.append(item)
                continue
            if normalized == target:
                candidates.append(item)
            elif target in normalized and not cls._is_search_result_metadata(normalized):
                partial_candidates.append(item)

        group_y = cls._label_y(labels, "群聊")
        frequent_y = cls._label_y(labels, "最常使用")
        network_y = cls._network_label_y(labels)

        if (expected_is_group or prefer_group) and group_y is not None:
            group_candidates = [c for c in candidates if c["y"] > group_y]
            if group_candidates:
                return min(group_candidates, key=lambda c: c["y"])
            group_boundary = cls._next_label_y(labels, group_y)
            group_partial_candidates = [
                c for c in partial_candidates
                if c["y"] > group_y and (group_boundary is None or c["y"] < group_boundary)
            ]
            if group_partial_candidates:
                return min(group_partial_candidates, key=lambda c: c["y"])

        if not candidates:
            return None

        if prefer_group:
            return None

        if frequent_y is not None:
            frequent_candidates = [
                c for c in candidates
                if c["y"] > frequent_y and (network_y is None or c["y"] < network_y)
            ]
            if frequent_candidates:
                return min(frequent_candidates, key=lambda c: c["y"])

        if network_y is not None:
            safe_candidates = [c for c in candidates if c["y"] < network_y]
            if safe_candidates:
                return min(safe_candidates, key=lambda c: c["y"])
            return None

        return min(candidates, key=lambda c: c["y"])

    @classmethod
    def _resolved_group_title_from_point(cls, point: dict, chat_name: str) -> str | None:
        title = str(point.get("resolved_title") or "").strip()
        normalized_title = cls._normalize_title(title)
        normalized_query = cls._normalize_title(chat_name)
        if (
            title
            and normalized_query
            and normalized_title != normalized_query
            and normalized_query in normalized_title
        ):
            return title
        return None

    @classmethod
    def _has_search_network_result(cls, entries: list[dict]) -> bool:
        return any(
            cls._is_search_network_label(cls._normalize_title(str(entry.get("text") or "")))
            for entry in entries or []
        )

    @classmethod
    def _network_label_y(cls, entries: list[dict]) -> float | None:
        values = [
            float(entry["y"])
            for entry in entries
            if cls._is_search_network_label(str(entry.get("normalized") or ""))
        ]
        return min(values) if values else None

    @staticmethod
    def _is_search_network_label(normalized: str) -> bool:
        return normalized in {"搜索网络结果", "搜一搜", "搜一搜网络结果"}

    @classmethod
    def _is_search_section_label(cls, normalized: str) -> bool:
        return normalized in {"群聊", "最常使用", "联系人", "聊天记录"} or cls._is_search_network_label(normalized)

    @staticmethod
    def _is_search_result_metadata(normalized: str) -> bool:
        return normalized.startswith("包含:") or normalized.startswith("包含：")

    @staticmethod
    def _next_label_y(labels: list[dict], after_y: float) -> float | None:
        values = [float(entry["y"]) for entry in labels if float(entry["y"]) > after_y]
        return min(values) if values else None

    @classmethod
    def _label_y(cls, entries: list[dict], label: str) -> float | None:
        normalized = cls._normalize_title(label)
        values = [float(entry["y"]) for entry in entries if entry.get("normalized") == normalized]
        return min(values) if values else None

    @staticmethod
    def _entry_center(entry: dict) -> dict:
        return {
            "x": float(entry.get("x", 0)) + (float(entry.get("w", 0)) / 2),
            "y": float(entry.get("y", 0)) + (float(entry.get("h", 0)) / 2),
        }

    def read_visible_texts(self) -> list[str]:
        app = self._escape_jxa(self._app_name)
        script = f'''
const appName = "{app}";
const se = Application("System Events");
const proc = se.processes.byName(appName);
const values = [];

function add(value) {{
  if (typeof value === "string") {{
    const trimmed = value.trim();
    if (trimmed) values.push(trimmed);
  }}
}}

function walk(node, depth) {{
  if (depth > 8) return;
  try {{ add(node.name()); }} catch (e) {{}}
  try {{ add(node.value()); }} catch (e) {{}}
  try {{
    const children = node.uiElements();
    for (let i = 0; i < children.length; i += 1) {{
      walk(children[i], depth + 1);
    }}
  }} catch (e) {{}}
}}

try {{
  const windows = proc.windows();
  for (let i = 0; i < windows.length; i += 1) {{
    walk(windows[i], 0);
  }}
}} catch (e) {{}}

JSON.stringify([...new Set(values)]);
'''
        result = self._runner(
            ["osascript", "-l", "JavaScript", "-e", script],
            timeout=10,
        )
        if result.returncode != 0:
            logger.warning("macOS visible text read failed: %s", result.stderr)
            return []
        try:
            data = json.loads(result.stdout or "[]")
        except json.JSONDecodeError:
            logger.warning("macOS visible text read returned non-JSON output")
            return []
        return [str(item).strip() for item in data if str(item).strip()]

    def read_current_chat_title_candidates(self) -> list[str]:
        return self._title_reader()

    def diagnose_access(self) -> dict:
        """Return a side-effect-light diagnostic for packaged macOS permissions."""
        result = {
            "app_name": self._app_name,
            "activated": False,
            "frontmost": False,
            "accessibility_ok": False,
            "screen_capture_ok": False,
            "window": None,
            "header_rect": None,
            "title_texts": [],
            "errors": [],
        }

        try:
            result["activated"] = self._bring_wechat_frontmost()
        except Exception as exc:
            result["errors"].append(f"activate_wechat: {exc}")

        try:
            result["frontmost"] = self._is_wechat_frontmost()
        except Exception as exc:
            result["errors"].append(f"frontmost: {exc}")

        try:
            geometry = self._get_wechat_geometry()
            result["geometry"] = geometry
            window = self._window_rect(geometry)
            if window:
                result["window"] = window
                result["accessibility_ok"] = True
        except Exception as exc:
            result["errors"].append(f"geometry: {exc}")
            window = None

        if window:
            header = self._chat_header_capture_rect(window)
            valid_header = self._valid_rect(header)
            result["header_rect"] = valid_header
            if valid_header:
                capture = self._probe_screen_capture(valid_header)
                result["screen_capture_ok"] = capture["ok"]
                if capture.get("error"):
                    result["errors"].append(capture["error"])
                if capture["ok"]:
                    try:
                        result["title_texts"] = self._read_current_header_texts()
                    except Exception as exc:
                        result["errors"].append(f"title_ocr: {exc}")

        result["ok"] = bool(result["activated"] and result["accessibility_ok"] and result["screen_capture_ok"])
        return result

    def send_text(self, content: str) -> bool:
        if not content:
            return False
        if not self._bring_wechat_frontmost():
            return False
        geometry = self._get_wechat_geometry()
        window = self._window_rect(geometry)
        if not window:
            logger.warning("Could not locate WeChat main window for send")
            return False
        if not self._click_screen(window["x"] + (window["w"] * 0.68), window["y"] + window["h"] - 44):
            return False
        time.sleep(0.1)
        if not self._select_focused_text():
            return False
        time.sleep(0.05)
        if not self._run(["pbcopy"], input_text=content):
            return False
        return self._paste_clipboard(send=True)

    def _paste_clipboard(self, send: bool = False) -> bool:
        send_line = self._send_key_script_line() if send else ''
        return self._run_wechat_process_script(
            f'''
  keystroke "v" using command down
  delay 0.1
{send_line}
''',
            timeout=8,
        )

    @staticmethod
    def _send_key_script_line() -> str:
        shortcut = os.getenv("MAC_WECHAT_SEND_SHORTCUT", "enter").strip().lower()
        if shortcut in {"cmd_enter", "command_enter", "command+enter", "cmd+enter"}:
            return "  key code 36 using command down"
        return "  key code 36"

    def _verify_current_chat_title(
        self,
        expected_title: str,
        expected_is_group: bool = False,
        require_group_marker: bool = False,
    ) -> bool:
        texts = self._title_reader()
        if self._texts_match_chat_title(
            texts,
            expected_title,
            expected_is_group=expected_is_group,
            require_group_marker=require_group_marker,
        ):
            return True
        logger.warning(
            "macOS WeChat title verification failed: expected=%r group=%s marker=%s texts=%s",
            expected_title,
            expected_is_group,
            require_group_marker,
            texts[:10],
        )
        return False

    def _current_chat_title_matches(
        self,
        expected_title: str,
        expected_is_group: bool = False,
        require_group_marker: bool = False,
    ) -> bool:
        return self._texts_match_chat_title(
            self._title_reader(),
            expected_title,
            expected_is_group=expected_is_group,
            require_group_marker=require_group_marker,
        )

    def _read_current_header_texts(self) -> list[str]:
        geometry = self._get_wechat_geometry()
        window = self._window_rect(geometry)
        if not window:
            return []

        header = self._chat_header_capture_rect(window)
        x = int(header["x"])
        y = int(header["y"])
        w = int(header["w"])
        h = int(header["h"])
        tmp = tempfile.NamedTemporaryFile(prefix="webot_wechat_header_", suffix=".png", delete=False)
        path = tmp.name
        tmp.close()
        try:
            if not self._run(["screencapture", "-x", f"-R{x},{y},{w},{h}", path], timeout=5):
                return self.read_visible_texts()
            script = '''
import Foundation
import Vision
import AppKit

let path = CommandLine.arguments[1]
guard let image = NSImage(contentsOfFile: path),
      let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    print("[]")
    exit(0)
}

var texts: [String] = []
let request = VNRecognizeTextRequest { request, error in
    let observations = request.results as? [VNRecognizedTextObservation] ?? []
    for obs in observations {
        guard let top = obs.topCandidates(1).first else { continue }
        let text = top.string.trimmingCharacters(in: .whitespacesAndNewlines)
        if !text.isEmpty {
            texts.append(text)
        }
    }
}
request.recognitionLanguages = ["zh-Hans", "en-US"]
request.recognitionLevel = .accurate
try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([request])
let data = try! JSONSerialization.data(withJSONObject: texts, options: [])
print(String(data: data, encoding: .utf8)!)
'''
            result = self._runner(["swift", "-", path], input_text=script, timeout=20)
            if result.returncode != 0:
                logger.warning("macOS title OCR failed: %s", result.stderr)
                return []
            data = json.loads(result.stdout or "[]")
            return [str(item).strip() for item in data if str(item).strip()]
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("macOS title OCR failed: %s", exc)
            return []
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def _recognize_screen_texts(self, rect: dict) -> list[dict]:
        valid = self._valid_rect(rect)
        if not valid:
            return []

        x = int(valid["x"])
        y = int(valid["y"])
        w = int(valid["w"])
        h = int(valid["h"])
        tmp = tempfile.NamedTemporaryFile(prefix="webot_wechat_search_", suffix=".png", delete=False)
        path = tmp.name
        tmp.close()
        try:
            if not self._run(["screencapture", "-x", f"-R{x},{y},{w},{h}", path], timeout=5):
                return []
            script = '''
import Foundation
import Vision
import AppKit

let path = CommandLine.arguments[1]
guard let image = NSImage(contentsOfFile: path),
      let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    print("[]")
    exit(0)
}

var items: [[String: Any]] = []
let request = VNRecognizeTextRequest { request, error in
    let observations = request.results as? [VNRecognizedTextObservation] ?? []
    for obs in observations {
        guard let top = obs.topCandidates(1).first else { continue }
        let text = top.string.trimmingCharacters(in: .whitespacesAndNewlines)
        if text.isEmpty { continue }
        let box = obs.boundingBox
        items.append([
            "text": text,
            "x": Double(box.minX),
            "y": Double(1.0 - box.maxY),
            "w": Double(box.width),
            "h": Double(box.height),
        ])
    }
}
request.recognitionLanguages = ["zh-Hans", "en-US"]
request.recognitionLevel = .accurate
try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([request])
let data = try! JSONSerialization.data(withJSONObject: items, options: [])
print(String(data: data, encoding: .utf8)!)
'''
            result = self._runner(["swift", "-", path], input_text=script, timeout=20)
            if result.returncode != 0:
                logger.warning("macOS search OCR failed: %s", result.stderr)
                return []
            data = json.loads(result.stdout or "[]")
            items = []
            for item in data if isinstance(data, list) else []:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("text") or "").strip()
                if not text:
                    continue
                try:
                    items.append({
                        "text": text,
                        "x": valid["x"] + (float(item.get("x", 0)) * valid["w"]),
                        "y": valid["y"] + (float(item.get("y", 0)) * valid["h"]),
                        "w": float(item.get("w", 0)) * valid["w"],
                        "h": float(item.get("h", 0)) * valid["h"],
                    })
                except (TypeError, ValueError):
                    continue
            return items
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("macOS search OCR failed: %s", exc)
            return []
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    @classmethod
    def _texts_match_chat_title(
        cls,
        texts: list[str],
        expected_title: str,
        expected_is_group: bool = False,
        require_group_marker: bool = False,
    ) -> bool:
        expected = cls._normalize_title(expected_title)
        if not expected:
            return False
        for text in texts:
            actual = cls._normalize_title(text)
            if not actual:
                continue
            if require_group_marker:
                if actual.startswith(expected + "(") or actual.startswith(expected + "（"):
                    return True
                continue
            if expected_is_group:
                if (
                    actual == expected
                    or actual.startswith(expected + "(")
                    or actual.startswith(expected + "（")
                    or (len(expected) >= 3 and actual.startswith(expected))
                ):
                    return True
                continue
            if actual == expected:
                return True
        return False

    @staticmethod
    def _normalize_title(value: str) -> str:
        return "".join(str(value or "").strip().split())

    def _bring_wechat_frontmost(self) -> bool:
        if not self._run(["open", "-a", self._app_name], timeout=8):
            return False
        for _ in range(10):
            if self._is_wechat_frontmost():
                return True
            time.sleep(0.2)
        logger.warning("WeChat did not become frontmost after activation")
        return False

    def _is_wechat_frontmost(self) -> bool:
        if not self._custom_runner:
            name = self._frontmost_app_name_from_appkit()
            if name:
                return name in {self._app_name, "WeChat", "微信"}

        script = '''
const se = Application("System Events");
const front = se.processes.whose({frontmost: true})();
const name = front.length ? front[0].name() : "";
JSON.stringify({front: name});
'''
        result = self._runner(
            ["osascript", "-l", "JavaScript", "-e", script],
            timeout=3,
        )
        if result.returncode != 0:
            logger.warning("macOS frontmost check failed: %s", result.stderr)
            return False
        try:
            data = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            return False
        return data.get("front") in {self._app_name, "WeChat", "微信"}

    @staticmethod
    def _frontmost_app_name_from_appkit() -> str:
        try:
            from AppKit import NSWorkspace

            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            if not app:
                return ""
            return str(app.localizedName() or "")
        except Exception as exc:
            logger.debug("macOS AppKit frontmost check failed: %s", exc)
            return ""

    def _run(self, cmd, input_text=None, timeout=5) -> bool:
        result = self._runner(cmd, input_text=input_text, timeout=timeout)
        if result.returncode != 0:
            logger.warning("macOS command failed (%s): %s", cmd, result.stderr)
            return False
        return True

    def _run_osascript(self, script: str, timeout=5) -> bool:
        if not self._custom_runner:
            native = self._run_applescript_in_process(script)
            if native is not None:
                return native["ok"]
        return self._run(["osascript", "-e", script], timeout=timeout)

    @staticmethod
    def _run_applescript_in_process(script: str) -> dict | None:
        try:
            from Foundation import NSAppleScript
        except Exception:
            return None

        try:
            apple_script = NSAppleScript.alloc().initWithSource_(script)
            descriptor, error = apple_script.executeAndReturnError_(None)
        except Exception as exc:
            logger.warning("macOS in-process AppleScript failed: %s", exc)
            return {"ok": False, "stdout": "", "stderr": str(exc)}

        if error:
            logger.warning("macOS in-process AppleScript failed: %s", error)
            return {"ok": False, "stdout": "", "stderr": str(error)}

        stdout = ""
        try:
            if descriptor is not None and descriptor.stringValue() is not None:
                stdout = str(descriptor.stringValue())
        except Exception:
            stdout = ""
        return {"ok": True, "stdout": stdout, "stderr": ""}

    def _run_wechat_process_script(self, body: str, timeout=5) -> bool:
        app = self._escape_applescript(self._app_name)
        script = f'''
tell application "System Events"
  tell process "{app}"
    set frontmost to true
{body}
  end tell
end tell
'''
        return self._run_osascript(script, timeout=timeout)

    def _probe_screen_capture(self, rect: dict) -> dict:
        x = int(rect["x"])
        y = int(rect["y"])
        w = int(rect["w"])
        h = int(rect["h"])
        tmp = tempfile.NamedTemporaryFile(prefix="webot_wechat_diag_", suffix=".png", delete=False)
        path = tmp.name
        tmp.close()
        try:
            result = self._runner(
                ["screencapture", "-x", f"-R{x},{y},{w},{h}", path],
                timeout=5,
            )
            if result.returncode != 0:
                stderr = str(result.stderr or "").strip()
                logger.warning("macOS screen capture diagnostic failed: %s", stderr)
                return {
                    "ok": False,
                    "error": stderr or "screencapture failed",
                }
            return {"ok": True, "error": None}
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def _press_escape(self) -> bool:
        return self._run_wechat_process_script(
            '''
  key code 53
''',
            timeout=3,
        )

    def _goto_chats_tab(self) -> bool:
        ok = self._run_wechat_process_script(
            '''
  key code 19 using command down
''',
            timeout=3,
        )
        if ok:
            time.sleep(0.25)
        return ok

    def _select_focused_text(self) -> bool:
        return self._run_wechat_process_script(
            '''
  keystroke "a" using command down
''',
            timeout=3,
        )

    def _get_wechat_geometry(self) -> dict:
        if not self._custom_runner:
            native = self._get_wechat_geometry_applescript()
            if native is not None:
                return native

        app = self._escape_jxa(self._app_name)
        script = f'''
const appName = "{app}";
const se = Application("System Events");
const proc = se.processes.byName(appName);

function rect(node) {{
  const pos = node.position();
  const size = node.size();
  return {{
    x: Number(pos[0]),
    y: Number(pos[1]),
    w: Number(size[0]),
    h: Number(size[1]),
  }};
}}

let result = {{}};
try {{
  const windows = proc.windows();
  let mainWindow = null;
  let closedAuxWindows = 0;
  for (let i = 0; i < windows.length; i += 1) {{
    try {{
      const name = String(windows[i].name() || "");
      if (name === "微信") {{
        mainWindow = windows[i];
        break;
      }}
    }} catch (e) {{}}
  }}
  if (mainWindow) {{
    for (let i = 0; i < windows.length; i += 1) {{
      try {{
        const name = String(windows[i].name() || "");
        if (name === "微信 (窗口)" || name.indexOf("搜一搜") >= 0 || name.endsWith(" - 搜一搜")) {{
          const buttons = windows[i].buttons();
          if (buttons.length > 0) {{
            buttons[0].click();
            closedAuxWindows += 1;
          }}
        }}
      }} catch (e) {{}}
    }}
  }}
  if (!mainWindow && windows.length > 0) mainWindow = windows[0];
  if (mainWindow) {{
    result.window = rect(mainWindow);
    result.closed_aux_windows = closedAuxWindows;
    try {{
      const sheets = mainWindow.sheets();
      if (sheets.length > 0) result.sheet = rect(sheets[0]);
    }} catch (e) {{}}
  }}
}} catch (e) {{
  result.error = String(e);
}}

JSON.stringify(result);
'''
        result = self._runner(
            ["osascript", "-l", "JavaScript", "-e", script],
            timeout=5,
        )
        if result.returncode != 0:
            logger.warning("macOS WeChat geometry read failed: %s", result.stderr)
            return {}
        try:
            data = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            logger.warning("macOS WeChat geometry returned non-JSON output")
            return {}
        if isinstance(data, dict) and data.get("error"):
            logger.warning(
                "macOS WeChat geometry access failed: %s. "
                "Grant Accessibility permission to webot.app.",
                data.get("error"),
            )
        return data if isinstance(data, dict) else {}

    def _get_wechat_geometry_applescript(self) -> dict | None:
        app = self._escape_applescript(self._app_name)
        script = f'''
set appName to "{app}"
try
  tell application "System Events"
    set proc to first process whose name is appName
    set mainWindow to missing value
    set closedAuxWindows to 0
    repeat with candidateWindow in windows of proc
      try
        set candidateName to name of candidateWindow
        if candidateName is "微信" then
          set mainWindow to candidateWindow
          exit repeat
        end if
      end try
    end repeat

    if mainWindow is not missing value then
      repeat with candidateWindow in windows of proc
        try
          set candidateName to name of candidateWindow
          if candidateName is "微信 (窗口)" or candidateName contains "搜一搜" or candidateName ends with " - 搜一搜" then
            try
              click button 1 of candidateWindow
              set closedAuxWindows to closedAuxWindows + 1
            end try
          end if
        end try
      end repeat
    end if

    if mainWindow is missing value and (count of windows of proc) > 0 then
      set mainWindow to window 1 of proc
    end if

    if mainWindow is missing value then
      return "empty"
    end if

    set windowPosition to position of mainWindow
    set windowSize to size of mainWindow
    set outputText to "window|" & item 1 of windowPosition & "|" & item 2 of windowPosition & "|" & item 1 of windowSize & "|" & item 2 of windowSize & "|closed|" & closedAuxWindows

    try
      if (count of sheets of mainWindow) > 0 then
        set sheetRect to sheet 1 of mainWindow
        set sheetPosition to position of sheetRect
        set sheetSize to size of sheetRect
        set outputText to outputText & "|sheet|" & item 1 of sheetPosition & "|" & item 2 of sheetPosition & "|" & item 1 of sheetSize & "|" & item 2 of sheetSize
      end if
    end try

    return outputText
  end tell
on error errorMessage
  return "error|" & errorMessage
end try
'''
        native = self._run_applescript_in_process(script)
        if native is None:
            return self._get_wechat_geometry_external_applescript(script)
        if not native["ok"]:
            if _is_tcc_denial(native.get("stderr", "")):
                return self._get_wechat_geometry_external_applescript(script)
            return {"error": native.get("stderr") or "AppleScript failed"}
        return self._parse_wechat_geometry_applescript(native.get("stdout", ""))

    def _get_wechat_geometry_external_applescript(self, script: str) -> dict | None:
        result = self._runner(["osascript", "-e", script], timeout=5)
        if result.returncode != 0:
            logger.warning("macOS WeChat geometry read failed: %s", result.stderr)
            return {}
        return self._parse_wechat_geometry_applescript(result.stdout)

    @staticmethod
    def _parse_wechat_geometry_applescript(output: str) -> dict:
        parts = str(output or "").split("|")
        if not parts or parts[0] == "empty":
            return {}
        if parts[0] == "error":
            return {"error": "|".join(parts[1:]).strip()}
        if parts[0] != "window" or len(parts) < 7:
            return {}
        try:
            data = {
                "window": {
                    "x": float(parts[1]),
                    "y": float(parts[2]),
                    "w": float(parts[3]),
                    "h": float(parts[4]),
                },
                "closed_aux_windows": int(float(parts[6])) if parts[5] == "closed" else 0,
            }
            if len(parts) >= 12 and parts[7] == "sheet":
                data["sheet"] = {
                    "x": float(parts[8]),
                    "y": float(parts[9]),
                    "w": float(parts[10]),
                    "h": float(parts[11]),
                }
            return data
        except (TypeError, ValueError):
            return {}

    def _window_rect(self, geometry: dict) -> dict | None:
        return self._valid_rect(geometry.get("window") if isinstance(geometry, dict) else None)

    def _modal_sheet_rect(self, geometry: dict) -> dict | None:
        return self._valid_rect(geometry.get("sheet") if isinstance(geometry, dict) else None)

    @staticmethod
    def _chat_header_capture_rect(window: dict) -> dict:
        left_offset = min(max(window["w"] * 0.34, 260), 620)
        return {
            "x": window["x"] + left_offset,
            "y": window["y"],
            "w": max(window["w"] - left_offset, 1),
            "h": 140,
        }

    @staticmethod
    def _valid_rect(value) -> dict | None:
        if not isinstance(value, dict):
            return None
        try:
            rect = {
                "x": float(value["x"]),
                "y": float(value["y"]),
                "w": float(value["w"]),
                "h": float(value["h"]),
            }
        except (KeyError, TypeError, ValueError):
            return None
        if rect["w"] <= 0 or rect["h"] <= 0:
            return None
        return rect

    def _click_screen(self, x: float, y: float) -> bool:
        try:
            return bool(self._clicker(x, y))
        except Exception as exc:
            logger.warning("macOS CoreGraphics click failed: %s", exc)
            return False

    @staticmethod
    def _core_graphics_click(x: float, y: float) -> bool:
        class CGPoint(Structure):
            _fields_ = [("x", c_double), ("y", c_double)]

        cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        cg.CGEventCreateMouseEvent.argtypes = [c_void_p, c_int64, CGPoint, c_int64]
        cg.CGEventCreateMouseEvent.restype = c_void_p
        cg.CGEventPost.argtypes = [c_int64, c_void_p]
        cg.CFRelease.argtypes = [c_void_p]

        point = CGPoint(float(x), float(y))
        for event_type in (1, 2):
            event = cg.CGEventCreateMouseEvent(None, event_type, point, 0)
            if not event:
                return False
            cg.CGEventPost(0, event)
            cg.CFRelease(event)
            time.sleep(0.05)
        return True

    @staticmethod
    def _escape_applescript(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _escape_jxa(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')


def _is_tcc_denial(message: str) -> bool:
    text = str(message or "").lower()
    return (
        "不允许辅助访问" in text
        or "未获得授权" in text
        or "not allowed assistive access" in text
        or "not authorized" in text
        or "not authorised" in text
        or "not permitted to send apple events" in text
    )


def _looks_internal_chat_id(value: str) -> bool:
    value = str(value or "").strip()
    return value.endswith("@chatroom") or value.startswith("wxid_")


class MacUIBackend(AbstractWeChatBackend):
    """Experimental macOS backend driven by visible WeChat UI text."""

    def __init__(
        self,
        bot_display_name: str = "",
        groups: list[str] | None = None,
        poll_sec: float = DEFAULT_POLL_SEC,
        store=None,
        automation: Optional[MacUIAutomation] = None,
    ):
        self._bot_name = bot_display_name
        self._groups = groups or []
        self._poll_sec = poll_sec
        self._store = store
        self._automation = automation or MacUIAutomation()
        self._running = False
        self._seen_ids: set[str] = set()
        self._current_group = self._default_group_name()

    def start(self, callback: MessageCallback) -> None:
        self._running = True
        logger.info(
            "MacUIBackend starting (groups=%s, poll=%ss, bot=%r)",
            self._groups, self._poll_sec, self._bot_name,
        )
        self._automation.activate_wechat()
        while self._running:
            self.poll_once(callback)
            time.sleep(self._poll_sec)

    def send_text(self, chat_id: str, content: str) -> bool:
        if not content:
            return False
        return self._automation.send_text(content)

    def stop(self) -> None:
        self._running = False

    def health_status(self) -> str:
        return "mac_ui_ok"

    def poll_once(self, callback: MessageCallback) -> None:
        """Poll visible WeChat UI text once and dispatch new lines.

        This testable single-cycle method keeps the long-running start loop
        simple and gives the macOS backend a deterministic unit-test surface.
        """
        for group_name in self._iter_groups():
            if group_name != self._current_group:
                if not self._automation.open_chat(group_name):
                    logger.warning("Failed to open macOS WeChat chat: %s", group_name)
                    continue
                self._current_group = group_name

            for line in self._automation.read_visible_texts():
                msg = self._message_from_line(group_name, line)
                if not msg or msg["message_id"] in self._seen_ids:
                    continue
                self._seen_ids.add(msg["message_id"])
                reply = callback(msg)
                if reply:
                    self.send_text(msg["chat_id"], reply)

    def _iter_groups(self) -> list[str]:
        groups = [g for g in self._groups if g and g != "*"]
        return groups or [self._default_group_name()]

    def _default_group_name(self) -> str:
        return "当前聊天"

    def _message_from_line(self, group_name: str, line: str) -> dict | None:
        text = (line or "").strip()
        if not text:
            return None

        sender_name = "unknown"
        content = text
        if ":" in text:
            sender_name, content = text.split(":", 1)
            sender_name = sender_name.strip() or "unknown"
            content = content.strip()
        if not content:
            return None

        digest = hashlib.sha1(
            f"{group_name}\0{sender_name}\0{content}".encode("utf-8")
        ).hexdigest()
        return {
            "message_id": f"mac-ui-{digest}",
            "chat_id": group_name,
            "group_name": group_name,
            "sender_id": sender_name,
            "sender_name": sender_name,
            "content": content,
            "msg_type": 1,
            "timestamp": int(time.time()),
            "is_at_mentioned": bool(self._bot_name and self._bot_name in content),
            "is_group": True,
        }
