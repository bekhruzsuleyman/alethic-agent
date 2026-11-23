import os

from alethic.agent.cli import build_parser
from alethic.agent.launcher import app_dirs, build_argv, ensure_weights


def norm(p):
    return os.path.normpath(p)


def test_frozen_app_keeps_data_next_to_the_exe_and_bundle_inside():
    bundle, data = app_dirs(frozen=True, exe=os.path.join("C:\\", "app", "alethic-agent.exe"), meipass="BUNDLE", source=__file__)
    assert bundle == "BUNDLE" and norm(data) == norm(os.path.join("C:\\", "app"))


def test_source_run_uses_the_repo_root_for_both():
    src = os.path.join("repo", "src", "alethic", "agent", "launcher.py")
    bundle, data = app_dirs(frozen=False, exe="python", meipass=None, source=src)
    assert norm(bundle) == norm(data) == "repo"


def test_default_arguments_point_at_weights_tokenizer_config_and_work_folder():
    from alethic.agent.launcher import default_work_folder
    a = build_parser().parse_args(build_argv([], "B", "D"))
    assert norm(a.weights) == norm("D/model-sft3c.pt") and a.folder is None
    assert norm(a.suggest) == norm(default_work_folder())
    assert norm(default_work_folder("/home/u")) == norm("/home/u/Documents/Alethic")
    assert a.tokenizer.endswith("alethic-tokenizer-v1.model") and a.tokenizer.startswith("B")
    assert norm(a.model) == norm("B/configs/model_gqa.yaml")


def test_arguments_typed_by_the_user_win_over_the_defaults():
    a = build_parser().parse_args(build_argv(["--effort", "high", "--folder", "other"], "B", "D"))
    assert a.effort == "high" and a.folder == "other"


def test_weights_are_downloaded_once_and_copied_next_to_the_app(tmp_path):
    cached = tmp_path / "cache.pt"
    cached.write_bytes(b"weights")
    target, calls, said = tmp_path / "app" / "model.pt", [], []
    ensure_weights(str(target), lambda: calls.append(1) or str(cached), say=said.append)
    assert target.read_bytes() == b"weights" and calls == [1] and said
    assert not (tmp_path / "app" / "model.pt.part").exists()
    ensure_weights(str(target), lambda: calls.append(1) or str(cached), say=said.append)
    assert calls == [1]


def test_selftest_reports_modules_that_fail_to_import():
    from alethic.agent.launcher import check_imports

    got = check_imports(["json", "no_such_module_xyz"])
    assert list(got) == ["no_such_module_xyz"] and got["no_such_module_xyz"]
    assert check_imports(["json", "os"]) == {}


def test_a_read_only_install_folder_moves_the_data_to_the_users_own_folder():
    exe = os.path.join("C:\\", "Program Files", "alethic", "alethic-agent.exe")
    bundle, data = app_dirs(frozen=True, exe=exe, meipass="BUNDLE", source=__file__, writable=lambda d: False,
                            fallback=os.path.join("C:\\", "Users", "x", "alethic-agent"))
    assert bundle == "BUNDLE" and norm(data) == norm(os.path.join("C:\\", "Users", "x", "alethic-agent"))


def test_a_writable_install_folder_keeps_the_data_next_to_the_exe():
    exe = os.path.join("C:\\", "app", "alethic-agent.exe")
    _, data = app_dirs(frozen=True, exe=exe, meipass="BUNDLE", source=__file__, writable=lambda d: True, fallback="elsewhere")
    assert norm(data) == norm(os.path.join("C:\\", "app"))


def test_a_failed_download_gives_a_message_a_person_can_act_on(tmp_path):
    import pytest
    from alethic.agent.launcher import WeightsError

    def offline():
        raise OSError("getaddrinfo failed")
    target = tmp_path / "model.pt"
    with pytest.raises(WeightsError) as e:
        ensure_weights(str(target), offline, say=lambda m: None)
    msg = str(e.value)
    assert "internet" in msg and "model.pt" in msg and str(tmp_path) in msg and not target.exists()


def test_the_harness_uses_the_sft3c_best_checkpoint_and_names_the_local_file_after_it():
    from alethic.agent import launcher
    assert launcher.WEIGHTS_FILE == "runs/sft3c/best/model.pt"
    assert launcher.WEIGHTS_NAME == "model-sft3c.pt"       # an older model.pt next to the exe is never reused by mistake


def test_the_download_message_names_the_model_being_fetched(tmp_path):
    cached = tmp_path / "c.pt"
    cached.write_bytes(b"w")
    said = []
    ensure_weights(str(tmp_path / "app" / "model-sft3c.pt"), lambda: str(cached), say=said.append)
    assert "SFT-3c" in said[0] and "SFT-2" not in said[0]


def test_the_label_in_the_title_defaults_to_sft3c_and_can_be_changed():
    from alethic.agent.cli import agent_title
    assert build_parser().parse_args(build_argv([], "B", "D")).label == "SFT-3c"
    assert build_parser().parse_args(build_argv(["--label", "SFT-2"], "B", "D")).label == "SFT-2"
    assert agent_title("SFT-3c") == "Alethic agent \u00b7 SFT-3c \u00b7 300M"


def test_site_packages_install_uses_packaged_assets_and_user_folder():
    pkg = os.path.join("C:\\", "venv", "Lib", "site-packages", "alethic", "agent", "launcher.py")
    bundle, data = app_dirs(frozen=False, exe="python", meipass=None, source=pkg, fallback="U")
    assert bundle.endswith(os.path.join("alethic", "_assets")) and data == "U"


def test_version_and_help_exit_without_downloading_weights(capsys, monkeypatch):
    from alethic.agent import launcher
    import pytest

    called = []
    monkeypatch.setattr(launcher, "ensure_weights", lambda *a, **kw: called.append("download"))
    launcher.run(["--version"])
    assert "alethic" in capsys.readouterr().out and not called

    with pytest.raises(SystemExit) as e:
        launcher.run(["--help"])
    assert e.value.code == 0 and not called
    assert "Chat with an Alethic" in capsys.readouterr().out


def test_explicit_weights_flag_skips_auto_download(monkeypatch):
    from alethic.agent import cli, launcher

    called = []
    monkeypatch.setattr(launcher, "ensure_weights", lambda *a, **kw: called.append("download"))
    monkeypatch.setattr(cli, "main", lambda argv=None: called.append(argv))
    launcher.run(["--weights", "custom.pt"])
    assert len(called) == 1 and "custom.pt" in called[0]


def test_selftest_verifies_packaged_assets_in_repo():
    from alethic.agent import launcher

    assert launcher._selftest(launcher.app_dirs(False, "python", None, launcher.__file__)[0]) == 0


def test_embedded_python_runs_code_and_scripts_without_system_python(tmp_path, capsys, monkeypatch):
    from alethic.agent import launcher
    from alethic.agent.tools import Workspace

    script = tmp_path / "calc.py"
    script.write_text("import sys, json\nprint(json.dumps([int(sys.argv[1]) * 2]))\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert launcher.run_embedded_python(["-c", "print(6 * 7)"]) == 0
    assert capsys.readouterr().out.strip() == "42"
    assert launcher.run_embedded_python([str(script), "21"]) == 0
    assert capsys.readouterr().out.strip() == "[42]"
    assert launcher.run_embedded_python(["missing.py"]) == 2
    assert "No such file" in capsys.readouterr().err

    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    ws = Workspace(str(tmp_path), mode="windows")
    assert "--run-python" in ws.python


def test_download_weights_flag_downloads_and_exits(tmp_path, capsys, monkeypatch):
    from alethic.agent import launcher

    src = tmp_path / "cached.pt"
    src.write_bytes(b"weights")
    monkeypatch.setattr(launcher, "app_dirs", lambda *a, **kw: (str(tmp_path), str(tmp_path / "data")))
    monkeypatch.setattr(launcher, "_download", lambda: str(src))
    launcher.run(["--download-weights"])
    assert (tmp_path / "data" / launcher.WEIGHTS_NAME).read_bytes() == b"weights"
    assert "weights:" in capsys.readouterr().out


def test_macos_user_folder_uses_application_support(monkeypatch):
    from alethic.agent import launcher

    monkeypatch.setattr("sys.platform", "darwin")
    assert launcher.user_folder().replace("\\", "/").endswith("Library/Application Support/alethic-agent")

