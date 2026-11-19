"""The floor height survey's watcher: a small window that follows the server's log while the rooms on the survey list
(interiorfloors.FILE_TODO) are measured in game, checks each height as it comes in and keeps it at once.

Read only: it reads a log and writes its own file, nothing goes to the game. Where the log comes from is set in
SURVEY_DIR / "config.json" (in the user's home, so it stays out of the repo):

    {"source": {"command": ["ssh", "...", "... {offset} ..."]}, "account": 3}
        a command printing "@@<file length>" and then the file's text from byte {offset} on (-1: none, the length
        only): the server's command log, which logs each height command with the character's X, Y and Z;
    {"source": {"file": "C:/.../Logs/WoWChatLog.txt"}}
        a local file followed (the game's chat log, with /chatlog on): the command's answer lines.

Each reading is checked against the room the list is at (interiorfloors.check_reading): taken (kept in CAPTURES,
written at once) and on to the next, or what's wrong said. "Accept Anyway" takes a reading the check refused. The list
resumes after the rooms CAPTURES has; `agps floor-survey import` reads CAPTURES first.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

from . import interiorfloors as F

SURVEY_DIR = Path.home() / ".agps-floor-survey"
CAPTURES = SURVEY_DIR / "captures.json"
CONFIG = SURVEY_DIR / "config.json"
POLL_SEC = 2.0

NUM = r"(-?\d+(?:\.\d+)?)"
# the server's command log: "<time> Command: gps [Player: Name (...) (Account: 3) X: 1 Y: 2 Z: 3 Map: 0 (...) ...]"
LOG_LINE = re.compile(r"Command:\s*\.?gps\b.*?\[Player:\s*(.+?)\s*\(.*?\(Account:\s*(\d+)\)\s*X:\s*" + NUM
                      + r"\s*Y:\s*" + NUM + r"\s*Z:\s*" + NUM + r"\s*Map:\s*(\d+)")
# the command's answer in the chat log: "Map: 0 (...) Zone: ..." and "X: 1 Y: 2 Z: 3 Orientation: ..."
CHAT_POS = re.compile(r"(?<![A-Za-z0-9])X:\s*" + NUM + r"[,\s]+Y:\s*" + NUM + r"[,\s]+Z:\s*" + NUM)
CHAT_MAP = re.compile(r"(?<![A-Za-z0-9])Map:\s*(\d+)")


def parse_lines(lines, account: int | None = None, state: dict | None = None) -> list[dict]:
    """The readings in log or chat lines: [{map, x, y, z}]. `account`: only that account's (the command log).
    `state` keeps a chat log's last map between calls."""
    state = state if state is not None else {}
    out = []
    for ln in lines:
        m = LOG_LINE.search(ln)
        if m:
            if account is None or int(m.group(2)) == account:
                out.append({"map": int(m.group(6)), "x": float(m.group(3)), "y": float(m.group(4)),
                            "z": float(m.group(5)), "who": m.group(1)})
            continue
        if "Command:" in ln:
            continue
        mm = CHAT_MAP.search(ln)
        if mm:
            state["map"] = int(mm.group(1))
        p = CHAT_POS.search(ln)
        if p and state.get("map") is not None:
            out.append({"map": state["map"], "x": float(p.group(1)), "y": float(p.group(2)), "z": float(p.group(3))})
    return out


class CommandSource:
    """A command that prints "@@<length>" and the text from byte {offset}: followed by offset."""

    def __init__(self, args):
        self.args, self.offset, self.rest = list(args), None, ""

    def poll(self) -> list[str]:
        off = -1 if self.offset is None else self.offset
        args = [a.replace("{offset}", str(off)) for a in self.args]
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        out = r.stdout or ""
        m = re.search(r"@@(\d+)", out)
        if not m:
            raise RuntimeError((r.stderr or out or "no answer").strip()[-200:])
        n = int(m.group(1))
        text = out[m.end():].lstrip("\r\n")
        first = self.offset is None
        self.offset = n
        if first:
            return []
        return self._lines(text)

    def _lines(self, text: str) -> list[str]:
        text = self.rest + text.replace("\r", "")
        parts = text.split("\n")
        self.rest = parts.pop()
        return parts


class FileSource(CommandSource):
    """A local file followed from its end."""

    def __init__(self, path):
        super().__init__([])
        self.path = Path(path)

    def poll(self) -> list[str]:
        n = self.path.stat().st_size if self.path.exists() else 0
        if self.offset is None or n < self.offset:
            self.offset = n
            return []
        with open(self.path, "rb") as f:
            f.seek(self.offset)
            data = f.read(n - self.offset)
        self.offset = n
        return self._lines(data.decode("utf-8", errors="replace"))


def load_config(path: Path = CONFIG) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def make_source(cfg: dict):
    src = cfg.get("source") or {}
    if src.get("command"):
        return CommandSource(src["command"])
    if src.get("file"):
        return FileSource(src["file"])
    raise SystemExit(f"no log to follow: set \"source\" in {CONFIG} (see app/azerothgps/floorsurvey.py)")


def load_captures(path: Path = CAPTURES) -> dict:
    if not path.exists():
        return {"rooms": {}}
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc.setdefault("rooms", {})
    return doc


def save_captures(doc: dict, path: Path = CAPTURES) -> None:
    """Written whole to a file next to it, then moved over it: never half written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


class Survey:
    """The list, what's measured, and the room being measured (the first not done, in the list's order)."""

    def __init__(self, todo: list, captures_path: Path = CAPTURES):
        self.todo, self.path = todo, captures_path
        self.caps = load_captures(captures_path)
        self.skipped: set = set()
        self.last = None  # (the last reading refused: Accept Anyway)

    def done(self, row) -> bool:
        return row["id"] in self.caps["rooms"]

    def current(self):
        for row in self.todo:
            if not self.done(row) and row["id"] not in self.skipped:
                return row
        return None

    def left(self) -> int:
        return sum(1 for r in self.todo if not self.done(r))

    def index(self, row) -> int:
        return next(i for i, r in enumerate(self.todo) if r["id"] == row["id"]) + 1

    def take(self, row, rd: dict, accepted: bool = False) -> None:
        self.caps["rooms"][row["id"]] = {"z": round(rd["z"], 2), "x": round(rd["x"], 2), "y": round(rd["y"], 2),
                                         "map": rd["map"], "place": row["place"], "at": int(time.time()),
                                         **({"accepted": True} if accepted else {})}
        save_captures(self.caps, self.path)
        self.last = None

    def reading(self, rd: dict) -> tuple[bool, str]:
        """A reading in: checked against the room being measured; kept and on to the next when right."""
        row = self.current()
        if row is None:
            return False, "All done: nothing left to measure."
        ok, msg = F.check_reading(row, rd["map"], rd["x"], rd["y"], rd["z"])
        if ok:
            self.take(row, rd)
        else:
            self.last = (row, rd)
        return ok, msg

    def accept_anyway(self) -> bool:
        if not self.last or self.last[0] is not self.current():
            return False
        self.take(self.last[0], self.last[1], accepted=True)
        return True


def describe(row, n: int, total: int) -> str:
    name = row.get("name") or f"room {row['id']}"
    return (f"Next ({n} of {total}): {name}\nmap {row['map']}, {row['x']:.0f}, {row['y']:.0f}, about z "
            f"{row['expect'] if row.get('expect') is not None else row['z']:.0f}\n{row['need']}")


def run_window(todo=None, cfg=None) -> int:  # pragma: no cover (a window)
    import tkinter as tk

    todo = F.load_todo() if todo is None else todo
    cfg = load_config() if cfg is None else cfg
    src = make_source(cfg)
    account = cfg.get("account")
    survey = Survey(todo)
    chat_state: dict = {}

    root = tk.Tk()
    root.title("Floor Height Survey")
    root.attributes("-topmost", True)
    root.geometry("460x250")
    head = tk.Label(root, justify="left", anchor="w", wraplength=440, font=("Segoe UI", 10))
    head.pack(fill="x", padx=10, pady=(10, 4))
    status = tk.Label(root, justify="left", anchor="w", wraplength=440, font=("Segoe UI", 12, "bold"))
    status.pack(fill="x", padx=10, pady=4)
    info = tk.Label(root, justify="left", anchor="w", fg="gray40", font=("Segoe UI", 9))
    info.pack(fill="x", padx=10)
    bar = tk.Frame(root)
    bar.pack(side="bottom", fill="x", padx=10, pady=10)

    def show(msg=None, ok=None):
        row = survey.current()
        if row is None:
            head.config(text=f"All done: {len(todo)} rooms measured. Run: agps floor-survey import")
        else:
            head.config(text=describe(row, survey.index(row), len(todo)))
        if msg is not None:
            status.config(text=(msg + " \u2713") if ok else msg, fg="#1a8f1a" if ok else "#c0392b")
        accept.config(state="normal" if survey.last else "disabled")
        info.config(text=f"{survey.left()} left; kept in {CAPTURES}")

    def copy_go():
        row = survey.current()
        if row:
            root.clipboard_clear()
            root.clipboard_append(row["go"])
            status.config(text=f"Copied: {row['go']}", fg="gray20")

    def skip():
        row = survey.current()
        if row:
            survey.skipped.add(row["id"])
            survey.last = None
            show("Skipped (back next time the window opens).", None)

    def accept_anyway():
        if survey.accept_anyway():
            show("Taken as it was.", True)

    def back():
        survey.skipped.clear()
        survey.last = None
        show("Back to the first room not measured.", None)

    tk.Button(bar, text="Copy Teleport", command=copy_go).pack(side="left")
    accept = tk.Button(bar, text="Accept Anyway", command=accept_anyway)
    accept.pack(side="left", padx=6)
    tk.Button(bar, text="Skip", command=skip).pack(side="left")
    tk.Button(bar, text="Back To First", command=back).pack(side="left", padx=6)

    def tick():
        try:
            for rd in parse_lines(src.poll(), account, chat_state):
                ok, msg = survey.reading(rd)
                show(msg, ok)
        except Exception as e:  # (the log out of reach a moment: said, tried again)
            info.config(text=f"Log not read: {e}"[:200])
        root.after(int(POLL_SEC * 1000), tick)

    show("Waiting for a height: teleport, stand on the floor, Record.", None)
    root.after(200, tick)
    root.mainloop()
    return 0
