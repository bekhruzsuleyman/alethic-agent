"""Start the agent with no arguments: weights, tokenizer and config are found next to the program or in user data."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

from alethic import __version__

TOKENIZER = os.path.join("data", "tokenizer", "alethic-tokenizer-v1", "alethic-tokenizer-v1.model")
MODEL_CFG = os.path.join("configs", "model_gqa.yaml")
REPO, WEIGHTS_FILE = "bekhruzsuleyman/alethic-300m", "runs/sft3c/best/model.pt"
WEIGHTS_NAME = "model-sft3c.pt"  # named after the model, so an older model.pt next to the program is never loaded by mistake


class WeightsError(Exception):
    """The model weights are missing and could not be fetched; the message says what to do."""


def _can_write(folder: str) -> bool:
    if not os.path.isdir(folder):
        return True
    try:
        with tempfile.TemporaryFile(dir=folder):
            return True
    except OSError:
        return False


def user_folder() -> str:
    """User-writable folder where downloaded weights and default workspaces live."""
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "alethic-agent")
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "alethic-agent")


def default_work_folder(home: str | None = None) -> str:
    """Default workspace folder inside the user's Documents directory (honors redirected Windows Documents)."""
    docs = ""
    if home is None and os.name == "nt":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(260)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
                docs = buf.value
        except Exception:
            docs = ""
    if not docs:
        docs = os.path.join(home or os.path.expanduser("~"), "Documents")
    return os.path.join(docs, "Alethic")


def _is_source_checkout(source: str) -> bool:
    """True when running out of `<repo>/src/alethic/...` (editable install or repo checkout)."""
    src_dir = os.path.dirname(os.path.dirname(os.path.dirname(source)))
    return os.path.basename(src_dir) == "src"


def app_dirs(frozen: bool, exe: str, meipass: str | None, source: str, writable=None, fallback: str | None = None):
    """(bundle folder with the tokenizer and config, data folder for model.pt and the work folder).
    Frozen exes keep data beside the exe when writable; source checkouts use the repo root;
    pip/wheel installs read packaged assets inside site-packages and store weights in the user folder."""
    if frozen:
        here = os.path.dirname(exe)
        ok = (writable or _can_write)(here)
        return meipass or here, here if ok else (fallback or user_folder())
    if _is_source_checkout(source):
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(source))))
        return root, root
    pkg_root = os.path.dirname(os.path.dirname(source))
    return os.path.join(pkg_root, "_assets"), (fallback or user_folder())


def build_argv(user_args: list, bundle: str, data: str, suggest: str | None = None) -> list:
    """Default arguments first; anything the user typed comes later, and argparse keeps the last value."""
    return ["--weights", os.path.join(data, WEIGHTS_NAME),
            "--tokenizer", os.path.join(bundle, TOKENIZER),
            "--model", os.path.join(bundle, MODEL_CFG),
            "--suggest", suggest or default_work_folder()] + list(user_args)


def has_flag(argv: list[str], *flags: str) -> bool:
    """True if any exact flag or `--flag=value` appears in argv."""
    return any(arg in flags or any(arg.startswith(f + "=") for f in flags) for arg in argv)


def ensure_weights(path: str, download, say=print) -> None:
    """Fetch the weights once (download() returns a cached file path) and copy them to `path`."""
    if os.path.exists(path):
        return
    say("Downloading the SFT-3c weights from Hugging Face, 1.2 GB, once…")
    folder = os.path.dirname(path) or "."
    part = path + ".part"
    try:
        os.makedirs(folder, exist_ok=True)
        shutil.copyfile(download(), part)
        os.replace(part, path)          # a half-copied file never takes the name model.pt
    except Exception as exc:
        if os.path.exists(part):
            os.remove(part)
        raise WeightsError("Could not get the model weights (%s).\nCheck your internet connection and start the program again,\n"
                           "or copy the file %s into this folder:\n  %s" % (exc, os.path.basename(path), folder)) from exc


def _download():
    from huggingface_hub import hf_hub_download
    return hf_hub_download(REPO, WEIGHTS_FILE)


SELFTEST_MODULES = ["torch", "sentencepiece", "numpy", "huggingface_hub", "alethic.model.transformer", "alethic.agent.cli"]


def check_imports(names, importer=None) -> dict:
    """Import each module; return {name: error text} for those that fail (the .exe build runs this to catch a missing DLL)."""
    import importlib
    importer = importer or importlib.import_module
    failed = {}
    for name in names:
        try:
            importer(name)
        except BaseException as exc:
            failed[name] = "%s: %s" % (type(exc).__name__, exc)
    return failed


def _selftest(bundle: str | None = None) -> int:
    failed = check_imports(SELFTEST_MODULES)
    for name, err in failed.items():
        print("FAILED  %s  %s" % (name, err))
    missing_assets = []
    if bundle:
        for rel in (TOKENIZER, MODEL_CFG):
            if not os.path.isfile(os.path.join(bundle, rel)):
                missing_assets.append(rel)
                print("FAILED  asset  missing %s in %s" % (rel, bundle))
    ok = not failed and not missing_assets
    print("selftest: %s" % ("all %d modules load" % len(SELFTEST_MODULES) if ok else "failed"))
    return 0 if ok else 1


def _set_title(title: str) -> None:
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleTitleW(title)
        except Exception:
            pass


def _wait(prompt: str) -> None:
    try:
        input(prompt)
    except EOFError:
        pass


def run_embedded_python(args: list[str]) -> int:
    """Execute `-c`, `-m`, or a `.py` file using the Python embedded in a standalone executable."""
    import runpy
    import traceback

    i = 0
    while i < len(args) and args[i].startswith("-") and args[i] != "-":
        opt = args[i]
        if opt == "--":
            i += 1
            break
        if opt in ("-V", "--version"):
            print("Python %s" % sys.version.split()[0])
            return 0
        if opt == "-c" or opt.startswith("-c"):
            code = args[i][2:] if len(opt) > 2 else (args[i + 1] if i + 1 < len(args) else "")
            rest = args[i + (1 if len(opt) > 2 else 2):]
            if len(opt) == 2 and i + 1 >= len(args):
                print("Argument expected for the -c option", file=sys.stderr)
                return 2
            return _exec_target("code", code, rest, runpy, traceback)
        if opt == "-m" or opt.startswith("-m"):
            mod = args[i][2:] if len(opt) > 2 else (args[i + 1] if i + 1 < len(args) else "")
            rest = args[i + (1 if len(opt) > 2 else 2):]
            if not mod:
                print("Argument expected for the -m option", file=sys.stderr)
                return 2
            return _exec_target("module", mod, rest, runpy, traceback)
        i += 1

    if i >= len(args):
        print("usage: python [-c cmd | -m mod | file] [arg ...]", file=sys.stderr)
        return 2
    script, rest = args[i], args[i + 1:]
    if not os.path.isfile(script):
        print("python: can't open file %r: [Errno 2] No such file or directory" % script, file=sys.stderr)
        return 2
    return _exec_target("path", script, rest, runpy, traceback)


def _exec_target(kind: str, target: str, rest: list[str], runpy, traceback_mod) -> int:
    cwd = os.getcwd()
    old_argv = list(sys.argv)
    added = os.path.dirname(os.path.abspath(target)) if kind == "path" else cwd
    inserted = False
    if added and (not sys.path or sys.path[0] != added):
        sys.path.insert(0, added)
        inserted = True
    try:
        sys.argv = [("-c" if kind == "code" else target)] + list(rest)
        if kind == "code":
            exec(compile(target, "<string>", "exec"), {"__name__": "__main__", "__package__": None})
        elif kind == "module":
            runpy.run_module(target, run_name="__main__", alter_sys=True)
        else:
            runpy.run_path(target, run_name="__main__")
        return 0
    except SystemExit as exc:
        if isinstance(exc.code, int):
            return exc.code
        if exc.code is None:
            return 0
        print(exc.code, file=sys.stderr)
        return 1
    except BaseException:
        traceback_mod.print_exc()
        return 1
    finally:
        sys.argv = old_argv
        if inserted and sys.path and sys.path[0] == added:
            sys.path.pop(0)


def run(argv: list[str] | None = None) -> None:
    """Entry point for `alethic` console command and the frozen Windows executable."""
    user_args = list(sys.argv[1:] if argv is None else argv)
    if user_args and user_args[0] == "--run-python":
        raise SystemExit(run_embedded_python(user_args[1:]))
    if has_flag(user_args, "--version", "-V"):
        print("alethic %s" % __version__)
        return
    frozen = bool(getattr(sys, "frozen", False))
    bundle, data = app_dirs(frozen, sys.executable, getattr(sys, "_MEIPASS", None), __file__)
    if user_args == ["--selftest"]:
        raise SystemExit(_selftest(bundle))
    if user_args == ["--download-weights"]:
        try:
            ensure_weights(os.path.join(data, WEIGHTS_NAME), _download)
        except WeightsError as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc
        print("weights: %s" % os.path.join(data, WEIGHTS_NAME))
        return
    if has_flag(user_args, "-h", "--help"):
        from alethic.agent.cli import build_parser
        build_parser().parse_args(build_argv(user_args, bundle, data))
        return
    os.environ.setdefault("PYTHONUTF8", "1")
    _set_title("Alethic agent")
    try:
        from alethic.agent.cli import main
        if not has_flag(user_args, "--weights"):
            ensure_weights(os.path.join(data, WEIGHTS_NAME), _download)
        main(build_argv(user_args, bundle, data))
    except SystemExit:
        raise
    except WeightsError as exc:
        print("\n" + str(exc))
        _wait("\nPress Enter to close.")
        return
    except BaseException:
        if not frozen:
            raise
        import traceback
        traceback.print_exc()
        _wait("\nSomething went wrong. Press Enter to close.")
        return
    if frozen:
        _wait("\nPress Enter to close.")
