"""The `alethic-agent` program: load the SFT model, then run a prompt loop that executes the model's tool calls."""
from __future__ import annotations

import argparse
import atexit
import os
import sys

from alethic.agent import effort as effort_levels
from alethic.agent import folderpick, splash
from alethic.agent.commands import run_command
from alethic.agent.loop import Agent
from alethic.agent.render import Renderer
from alethic.agent.tools import Workspace
from alethic.agent.ui import UI, enable_ansi, use_utf8_output


def agent_title(label: str) -> str:
    return "Alethic agent \u00b7 %s \u00b7 300M" % label


class Session:
    """Everything one chat needs, wired together: model function, work folder, permissions, screen."""

    def __init__(self, generate, engine, folder, ui, count_tokens, auto=False, mode=None, effort="medium",
                 title="Alethic agent", max_seq_len=4096, suggest=None,
                 weights_path="", model_config="", sp=None, model_name="SFT-3c"):
        self.engine, self.ui, self.count_tokens = engine, ui, count_tokens
        self._generate, self._mode, self.auto0 = generate, mode, auto
        self.title, self.max_seq_len, self.effort = title, max_seq_len, effort
        self._suggest = suggest
        self.weights_path, self.model_config, self.sp = weights_path, model_config, sp
        self.model_name, self.base_mode = model_name, False
        self.ws = Workspace(folder, mode=mode, approve=self._approve)
        self.ws.auto = auto
        self.agent = Agent(generate, self.ws)
        effort_levels.apply(self.agent, effort)

    def choose_model(self, name_or_path: str) -> str:
        """Switch to a named preset ('sft3c', 'base') or a local .pt checkpoint file."""
        import shutil

        from alethic.agent import modelio
        from alethic.agent.engine import Engine
        from alethic.agent.fastgen import KVDecoder

        raw = name_or_path.strip()
        key = raw.lower()
        if key in modelio.MODELS:
            preset = modelio.MODELS[key]
            base_dir = os.path.dirname(os.path.abspath(self.weights_path)) if self.weights_path else "."
            target = os.path.join(base_dir, preset["filename"])
            if key == "sft3c" and self.weights_path and os.path.isfile(self.weights_path):
                target = self.weights_path
            if not os.path.isfile(target):
                if self.ui and hasattr(self.ui, "info"):
                    self.ui.info("downloading %s weights from Hugging Face (once)..." % preset["label"])
                part = target + ".part"
                try:
                    from huggingface_hub import hf_hub_download
                    os.makedirs(base_dir, exist_ok=True)
                    cached = hf_hub_download(preset["hf_repo"], preset["hf_file"])
                    shutil.copyfile(cached, part)
                    os.replace(part, target)
                except Exception as exc:
                    if os.path.exists(part):
                        os.remove(part)
                    return "error: could not download %s weights: %s" % (preset["label"], exc)
            label = preset["label"]
            base_mode = preset["base_mode"]
        else:
            cand = raw if os.path.isabs(raw) else os.path.abspath(os.path.join(self.ws.root, raw))
            if not os.path.isfile(cand):
                cand = os.path.abspath(raw)
            if not os.path.isfile(cand):
                return "error: weights file not found: %s" % raw
            target = cand
            label = os.path.splitext(os.path.basename(target))[0]
            base_mode = "sft" not in os.path.basename(target).lower()

        if not (self.model_config and self.sp is not None):
            return "error: model reload is not available here"
        try:
            model = modelio.load_model(target, self.model_config)
        except Exception as exc:
            return "error: could not load %s: %s" % (target, exc)
        temp = self.engine.temperature
        self.engine = Engine(KVDecoder(model), self.sp, model.cfg.max_seq_len, temperature=temp)
        self._generate = self.engine.generate
        old = self.agent
        self.agent = Agent(self._generate, self.ws)
        effort_levels.apply(self.agent, self.effort)
        self.agent.max_new, self.agent.max_steps = old.max_new, old.max_steps
        self.weights_path = target
        self.max_seq_len = model.cfg.max_seq_len
        self.model_name = label
        self.base_mode = base_mode
        self.title = agent_title(label)
        return "model: %s (%s, new conversation)" % (label, "raw completion" if base_mode else "agent mode")

    def set_folder(self, folder: str) -> None:
        """Work somewhere else: a new Workspace and a new, empty conversation. Permissions and effort stay."""
        old = self.agent
        auto = self.ws.auto
        self.ws = Workspace(folder, mode=self._mode, approve=self._approve)
        self.ws.auto = auto
        self.agent = Agent(self._generate, self.ws)
        effort_levels.apply(self.agent, self.effort)
        self.agent.max_new, self.agent.max_steps = old.max_new, old.max_steps

    def choose_folder(self, arg: str = "") -> str:
        from alethic.agent.launcher import default_work_folder
        default = self._suggest or default_work_folder()
        if hasattr(self.ui, "pick_folder"):   # the Textual screen asks with its own dialog
            folder = self.ui.pick_folder(default, arg)
        else:
            folder = folderpick.pick(self.ui.line, input, folderpick.browse_dialog, folderpick.storage_path(),
                                     default=default, first=arg or None, ui=self.ui)
        if not folder:
            return "work folder unchanged: %s" % self.ws.root
        self.set_folder(folder)
        return "work folder: %s (new conversation)" % self.ws.root

    def _approve(self, call) -> bool:
        answer = self.ui.confirm(call)
        if answer == "a":
            self.ws.auto = True
        return answer != "n"


def _turn(s: Session, ui: UI, message: str) -> None:
    state = {"r": Renderer(), "tokens": 0}

    def on_event(kind, *a):
        if kind == "token":
            state["tokens"] += 1
            ui.set_phase("generating")
            ui.tick(state["tokens"])
            ui.stream(state["r"].feed(a[0]))
        elif kind == "call":
            ui.stream(state["r"].finish())
            state["r"] = Renderer()
            ui.call(a[0])
        elif kind == "result":
            call, out = a
            ui.result(out.result if out.result is not None else ("" if out.ok else "error"), ok=out.ok, call=call)

    interrupted = False
    ui.begin_turn()
    try:
        if getattr(s, "base_mode", False):
            max_new = {"low": 128, "medium": 256, "high": 512}.get(s.effort, 256)
            s.engine.generate(message, lambda _: False, max_new, lambda chunk: on_event("token", chunk))
            ui.stream(state["r"].finish())
        else:
            res = s.agent.ask(message, on_event)
            ui.stream(state["r"].finish())
            if res.truncated:
                ui.warn("stopped after %d tool calls (%s)" % (res.steps, res.reason))
    except KeyboardInterrupt:
        interrupted = True
    finally:
        ui.end_turn()
    if interrupted:
        ui.warn("interrupted. the unfinished answer was dropped")


def _status(s: Session) -> str:
    if getattr(s, "base_mode", False):
        return "%s (raw) · %s · temp %s" % (getattr(s, "model_name", "Base"), s.effort, s.engine.temperature)
    return "%s · %s · %s" % (getattr(s, "model_name", "SFT-3c"), s.effort, "auto" if s.ws.auto else "asks first")


def repl(s: Session, ui: UI, title: str) -> None:
    ui.banner(title, s.ws.root, s.ws.auto, effort=s.effort)
    asked_quit = False
    while True:
        try:
            line = ui.prompt(status=_status(s))
        except KeyboardInterrupt:
            if asked_quit:
                break
            asked_quit = True
            ui.line()
            ui.warn("press Ctrl+C again (or type /quit) to leave")
            continue
        asked_quit = False
        if line is None:
            break
        if not line:
            continue
        cmd = run_command(line, s)
        if cmd is not None:
            if cmd.message:
                ui.info(cmd.message)
            if cmd.clear:
                ui.clear()
            if cmd.quit:
                break
            if cmd.rerun:
                _turn(s, ui, cmd.rerun)
            continue
        _turn(s, ui, line)
    ui.line("bye")


DEFAULT_TEMP = 0.3


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="alethic-agent", description="Chat with an Alethic SFT model that can run tools.")
    p.add_argument("--weights", required=True)
    p.add_argument("--tokenizer", required=True)
    p.add_argument("--model", default="configs/model_gqa.yaml")
    p.add_argument("--folder", default=None, help="the only folder the model may read and write (without it you are asked)")
    p.add_argument("--suggest", default="work", help="the folder suggested in the picker, and used when nobody can be asked")
    p.add_argument("--temp", type=float, default=DEFAULT_TEMP, help="0 = always the most likely token (loops); about 0.3 works best")
    p.add_argument("--effort", choices=list(effort_levels.LEVELS), default="medium")
    p.add_argument("--max-new", type=int, default=0, help="override the effort level: tokens per step")
    p.add_argument("--max-steps", type=int, default=0, help="override the effort level: tool calls per message")
    p.add_argument("--auto", action="store_true", help="run commands without asking")
    p.add_argument("--threads", type=int, default=0)
    p.add_argument("--textual", action="store_true", help="try the Textual screen instead of the classic terminal")
    p.add_argument("--json", action="store_true", help="talk JSON lines on stdin/stdout (the Ink screen in ui/ uses this)")
    p.add_argument("--label", default="SFT-3c", help="the model name shown in the title")
    return p


def wants_textual(a, tty: bool) -> bool:
    """The classic terminal is the default; the Textual screen only runs with --textual, a real terminal and the package."""
    if not a.textual or not tty:
        return False
    try:
        import textual  # noqa: F401
    except ImportError:
        return False
    return True


def resolve_folder(a, say, interactive: bool, suggest: str, ui=None):
    """--folder wins; otherwise ask (or use the suggestion when nobody can answer). None = the user cancelled."""
    if a.folder:
        return a.folder
    if not interactive:
        return suggest
    return folderpick.pick(say, input, folderpick.browse_dialog, folderpick.storage_path(), default=suggest, ui=ui)


def main(argv=None) -> None:
    a = build_parser().parse_args(argv)

    use_utf8_output()
    tty = sys.stdin.isatty() and sys.stdout.isatty()
    textual = wants_textual(a, tty)
    ui = UI(vt=enable_ansi()) if not a.json else None
    if ui:
        atexit.register(ui.reset_terminal)
    if a.json:
        folder = os.path.abspath(a.folder or a.suggest)
        os.makedirs(folder, exist_ok=True)
    else:
        if tty and not textual:
            splash.clear_console(ui)
        folder = resolve_folder(a, ui.line, tty, os.path.abspath(a.suggest), ui=ui)
        if not folder:
            ui.info("no folder chosen. bye")
            return

    def _load():
        import sentencepiece as spm
        import torch

        from alethic.agent.engine import Engine
        from alethic.agent.fastgen import KVDecoder
        from alethic.agent.modelio import load_model

        if a.threads:
            torch.set_num_threads(a.threads)
        sp = spm.SentencePieceProcessor(model_file=a.tokenizer)
        model = load_model(a.weights, a.model)
        engine = Engine(KVDecoder(model), sp, model.cfg.max_seq_len, temperature=a.temp)
        return sp, model, engine

    if a.json or textual:
        sp, model, engine = _load()
    else:
        sp, model, engine = splash.run_loading(ui, a.label, _load)
        if tty:
            splash.maximize_console()
            ui._sleep(0.05)
            splash.clear_console(ui)

    title = agent_title(a.label)
    bridge = None
    if a.json:
        from alethic.agent.jsonio import JsonBridge, serve
        bridge = JsonBridge(sys.stdout)
    elif textual:
        from alethic.agent.tui import AgentApp, TuiBridge
        bridge = TuiBridge()
    s = Session(engine.generate, engine, folder, bridge or ui, count_tokens=lambda t: len(sp.encode(t)), auto=a.auto,
                effort=a.effort, title=title, max_seq_len=model.cfg.max_seq_len, suggest=os.path.abspath(a.suggest),
                weights_path=a.weights, model_config=a.model, sp=sp, model_name=a.label)
    s.agent.max_new, s.agent.max_steps = a.max_new or s.agent.max_new, a.max_steps or s.agent.max_steps
    if a.json:
        serve(s, sys.stdin, sys.stdout)
    elif bridge:
        AgentApp(s, bridge).run()
    else:
        repl(s, ui, title=title)


if __name__ == "__main__":
    main()
