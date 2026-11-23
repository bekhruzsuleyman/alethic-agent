"""The input line as a small state machine: typing, cursor keys, history and the "/" menu. It draws nothing."""
from __future__ import annotations

from dataclasses import dataclass

from alethic.agent.menu import suggest, takes_argument


@dataclass
class Result:
    kind: str        # "submit", "interrupt" or "eof"
    text: str = ""


class LineEditor:
    def __init__(self, history=None):
        self.history = list(history or [])
        self.buffer, self.cursor = "", 0
        self.selected, self.closed = 0, False
        self._hist_at, self._draft = len(self.history), ""

    # menu ---------------------------------------------------------------
    def suggestions(self) -> list:
        return [] if self.closed else suggest(self.buffer)

    def _set(self, text: str, cursor: int | None = None) -> None:
        self.buffer = text
        self.cursor = len(text) if cursor is None else cursor
        self.selected, self.closed = 0, False

    def _changed(self) -> None:
        self.selected, self.closed = 0, False
        self._hist_at = len(self.history)

    # drawing helper -----------------------------------------------------
    def window(self, width: int):
        """The part of the line that fits in `width` columns and where the cursor sits inside it."""
        width = max(4, width)
        start = self.cursor - width + 1 if self.cursor >= width else 0
        return self.buffer[start:start + width], self.cursor - start

    def lines_window(self, width: int, max_lines: int = 8) -> tuple[list[str], int, int]:
        """Wrap the buffer into at most `max_lines` visible rows of `width` columns, returning (lines, row, col)."""
        width = max(4, width)
        max_lines = max(1, max_lines)
        rows: list[str] = []
        cur_row, cur_col, pos = 0, 0, 0
        parts = self.buffer.split("\n")
        for idx, part in enumerate(parts):
            end = pos + len(part)
            chunks = [part[i:i + width] for i in range(0, len(part), width)] or [""]
            if pos <= self.cursor <= end:
                rel = self.cursor - pos
                c_idx = min(len(chunks) - 1, rel // width)
                cur_row = len(rows) + c_idx
                cur_col = rel - c_idx * width
                if cur_col == width and c_idx == len(chunks) - 1:
                    chunks.append("")
                    cur_row += 1
                    cur_col = 0
            rows.extend(chunks)
            pos = end + 1
        start = max(0, cur_row - max_lines + 1)
        return rows[start:start + max_lines], cur_row - start, cur_col

    # keys ---------------------------------------------------------------
    def feed(self, key: str):
        """Handle one key. Returns a Result when the line is finished, otherwise None."""
        if len(key) == 1:
            if ord(key) >= 32:
                self.buffer = self.buffer[:self.cursor] + key + self.buffer[self.cursor:]
                self.cursor += 1
                self._changed()
            return None
        n = len(self.suggestions())
        if key == "newline":
            self.buffer = self.buffer[:self.cursor] + "\n" + self.buffer[self.cursor:]
            self.cursor += 1
            self._changed()
            return None
        if key == "enter":
            return self._enter()
        if key == "ctrl-c":
            return Result("interrupt")
        if key == "ctrl-d":
            if not self.buffer:
                return Result("eof")
            return self.feed("delete")
        if key == "backspace" and self.cursor:
            self.buffer = self.buffer[:self.cursor - 1] + self.buffer[self.cursor:]
            self.cursor -= 1
            self._changed()
        elif key == "delete" and self.cursor < len(self.buffer):
            self.buffer = self.buffer[:self.cursor] + self.buffer[self.cursor + 1:]
            self._changed()
        elif key == "left":
            self.cursor = max(0, self.cursor - 1)
        elif key == "right":
            self.cursor = min(len(self.buffer), self.cursor + 1)
        elif key == "home":
            self.cursor = self.buffer.rfind("\n", 0, self.cursor) + 1
        elif key == "end":
            nxt = self.buffer.find("\n", self.cursor)
            self.cursor = len(self.buffer) if nxt == -1 else nxt
        elif key == "ctrl-u":
            self.buffer, self.cursor = self.buffer[self.cursor:], 0
            self._changed()
        elif key == "ctrl-w":
            head = self.buffer[:self.cursor].rstrip()
            head = head[:head.rfind(" ") + 1]
            self.buffer, self.cursor = head + self.buffer[self.cursor:], len(head)
            self._changed()
        elif key == "tab" and n:
            self._complete(self.suggestions()[self.selected].text)
        elif key == "esc":
            self.closed = True
        elif key in ("up", "down"):
            if n:
                self.selected = (self.selected + (1 if key == "down" else -1)) % n
            elif not self._move_line(-1 if key == "up" else 1):
                self._walk_history(-1 if key == "up" else 1)
        return None

    def _move_line(self, step: int) -> bool:
        """Move up or down one logical line within a multiline buffer; False if already at the boundary."""
        if "\n" not in self.buffer:
            return False
        ls = self.buffer.rfind("\n", 0, self.cursor) + 1
        col = self.cursor - ls
        if step < 0:
            if ls == 0:
                return False
            pls = self.buffer.rfind("\n", 0, ls - 1) + 1
            self.cursor = min(pls + col, ls - 1)
            return True
        le = self.buffer.find("\n", self.cursor)
        if le == -1:
            return False
        nle = self.buffer.find("\n", le + 1)
        end = len(self.buffer) if nle == -1 else nle
        self.cursor = min(le + 1 + col, end)
        return True

    def _complete(self, text: str) -> None:
        self._set(text + " " if takes_argument(text) else text)

    def _enter(self):
        sugg = self.suggestions()
        if sugg:
            pick = sugg[self.selected].text
            if pick != self.buffer:
                self._complete(pick)
                if takes_argument(pick):
                    return None          # it needs text after it: fill it in and wait
        return Result("submit", self.buffer)

    def _walk_history(self, step: int) -> None:
        if not self.history:
            return
        if self._hist_at == len(self.history):
            self._draft = self.buffer
        at = min(max(self._hist_at + step, 0), len(self.history))
        if at == self._hist_at:
            return
        self._hist_at = at
        keep = at
        self._set(self._draft if at == len(self.history) else self.history[at])
        self._hist_at = keep
