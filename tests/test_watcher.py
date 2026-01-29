"""Tests for watcher module."""

from __future__ import annotations

from pathlib import Path

from probe.watcher import WatcherState, _is_branch_switch, _should_ignore


class TestShouldIgnore:
    """Tests for _should_ignore function."""

    def test_ignore_git_directory(self, tmp_path: Path) -> None:
        path = tmp_path / ".git" / "objects" / "abc123"
        assert _should_ignore(path, tmp_path) is True

    def test_allow_git_head(self, tmp_path: Path) -> None:
        path = tmp_path / ".git" / "HEAD"
        assert _should_ignore(path, tmp_path) is False

    def test_ignore_probe_directory(self, tmp_path: Path) -> None:
        path = tmp_path / ".probe" / "manifest.sqlite"
        assert _should_ignore(path, tmp_path) is True

    def test_ignore_node_modules(self, tmp_path: Path) -> None:
        path = tmp_path / "node_modules" / "react" / "index.js"
        assert _should_ignore(path, tmp_path) is True

    def test_ignore_pycache(self, tmp_path: Path) -> None:
        path = tmp_path / "__pycache__" / "module.cpython-312.pyc"
        assert _should_ignore(path, tmp_path) is True

    def test_ignore_venv(self, tmp_path: Path) -> None:
        path = tmp_path / ".venv" / "bin" / "python"
        assert _should_ignore(path, tmp_path) is True

    def test_ignore_binary_files(self, tmp_path: Path) -> None:
        assert _should_ignore(tmp_path / "app.exe", tmp_path) is True
        assert _should_ignore(tmp_path / "lib.so", tmp_path) is True
        assert _should_ignore(tmp_path / "lib.dll", tmp_path) is True
        assert _should_ignore(tmp_path / "lib.dylib", tmp_path) is True
        assert _should_ignore(tmp_path / "module.pyc", tmp_path) is True

    def test_allow_source_files(self, tmp_path: Path) -> None:
        assert _should_ignore(tmp_path / "main.py", tmp_path) is False
        assert _should_ignore(tmp_path / "src" / "app.ts", tmp_path) is False
        assert _should_ignore(tmp_path / "README.md", tmp_path) is False

    def test_ignore_hidden_directories(self, tmp_path: Path) -> None:
        path = tmp_path / ".hidden" / "file.txt"
        assert _should_ignore(path, tmp_path) is True

    def test_ignore_outside_project(self, tmp_path: Path) -> None:
        path = Path("/etc/passwd")
        assert _should_ignore(path, tmp_path) is True


class TestIsBranchSwitch:
    """Tests for _is_branch_switch function."""

    def test_git_head_is_branch_switch(self, tmp_path: Path) -> None:
        path = tmp_path / ".git" / "HEAD"
        assert _is_branch_switch(path, tmp_path) is True

    def test_other_git_files_not_branch_switch(self, tmp_path: Path) -> None:
        path = tmp_path / ".git" / "config"
        assert _is_branch_switch(path, tmp_path) is False

    def test_regular_files_not_branch_switch(self, tmp_path: Path) -> None:
        path = tmp_path / "main.py"
        assert _is_branch_switch(path, tmp_path) is False

    def test_outside_project_not_branch_switch(self, tmp_path: Path) -> None:
        path = Path("/etc/passwd")
        assert _is_branch_switch(path, tmp_path) is False


class TestWatcherState:
    """Tests for WatcherState dataclass."""

    def test_default_state(self) -> None:
        state = WatcherState()
        assert state.running is False
        assert state.last_scan_time == 0.0
        assert state.index_generation == 0
        assert len(state.pending_paths) == 0
        assert state.burst_count == 0

    def test_state_mutation(self) -> None:
        state = WatcherState()
        state.running = True
        state.index_generation = 5
        state.pending_paths.add(Path("test.py"))

        assert state.running is True
        assert state.index_generation == 5
        assert Path("test.py") in state.pending_paths

    def test_pending_paths_independence(self) -> None:
        # Ensure each WatcherState has its own pending_paths set
        state1 = WatcherState()
        state2 = WatcherState()

        state1.pending_paths.add(Path("a.py"))
        state2.pending_paths.add(Path("b.py"))

        assert Path("a.py") in state1.pending_paths
        assert Path("b.py") not in state1.pending_paths
        assert Path("b.py") in state2.pending_paths
        assert Path("a.py") not in state2.pending_paths
