"""Self-test of tool/adopter_check.py against tool/adopter_stub. Offline; stdlib only.

Run: python3 -m unittest discover -s tool/tests
"""
import hashlib
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

BOND = Path(__file__).resolve().parents[2]
TOOL = BOND / "tool" / "adopter_check.py"
STUB = BOND / "tool" / "adopter_stub"
GIT = ["git", "-c", "user.name=t", "-c", "user.email=none", "-c", "commit.gpgsign=false"]


def tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for dirpath, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(files + dirs):
            p = Path(dirpath) / name
            st = p.lstat()
            h.update(f"{p.relative_to(root)}:{st.st_mode}:{st.st_size}:{int(st.st_mtime_ns)}".encode())
            if p.is_file() and not p.is_symlink():
                h.update(p.read_bytes())
    return h.hexdigest()


class AdopterLane(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lane-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.scratch = self.tmp / "scratch"  # TMPDIR for the tool: shows what it leaves behind
        self.scratch.mkdir()

    def make_app(self, toml=None, git=True, dirty=True) -> Path:
        app = self.tmp / "work" / "stub"
        shutil.copytree(STUB, app)
        if toml is not None:
            (app / ".bond-adopter.toml").write_text(toml)
        if git:
            subprocess.run(["git", "init", "-q"], cwd=app, check=True)
            subprocess.run(["git", "add", "-A"], cwd=app, check=True)
            subprocess.run([*GIT, "commit", "-qm", "stub"], cwd=app, check=True)
        if dirty:
            (app / "py" / "untracked.txt").write_text("u\n")
            (app / "py" / "ignored.txt").write_text("i\n")
            with (app / "app" / "pubspec.yaml").open("a") as f:
                f.write("# uncommitted edit\n")
        return app

    def toml(self, old="", new="") -> str:
        text = (STUB / ".bond-adopter.toml").read_text()
        self.assertIn(old, text)
        return text.replace(old, new) if old else text

    def run_tool(self, app: Path, *args: str):
        env = {**os.environ, "TMPDIR": str(self.scratch), "GIT_CEILING_DIRECTORIES": str(self.tmp)}
        return subprocess.run([sys.executable, str(TOOL), "--app", str(app), "--bond", str(BOND), *args],
                              capture_output=True, text=True, env=env, timeout=120)

    def kept(self, r) -> Path:
        line = next(x for x in r.stdout.splitlines() if x.startswith("kept copy: "))
        return Path(line.removeprefix("kept copy: "))

    def rows(self, r) -> dict:
        out = {}
        for line in r.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[1] in {"PASS", "FAIL", "TIMEOUT", "SKIPPED"}:
                out[parts[0]] = parts[1]
        return out

    def test_pass_copies_working_state_and_leaves_app_untouched(self):
        app = self.make_app()
        before = tree_hash(app)
        r = self.run_tool(app, "--keep")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.rows(r), {"overlay": "PASS", "overrides": "PASS", "isolated": "PASS"})
        copy = self.kept(r)
        self.assertTrue(copy.is_relative_to(self.scratch))
        self.assertIn("# uncommitted edit", (copy / "app" / "pubspec.yaml").read_text())
        self.assertTrue((copy / "py" / "untracked.txt").exists())
        self.assertFalse((copy / "py" / "ignored.txt").exists())
        self.assertFalse((copy / ".git").exists())
        self.assertNotIn(str(app), (copy / "py" / "overlay.log").read_text())
        self.assertEqual(tree_hash(app), before, "the app checkout changed")
        self.assertIn("(dirty)", r.stdout)

    def test_copy_extra_brings_ignored_file(self):
        app = self.make_app(self.toml('version = 1\n', 'version = 1\n\n[copy]\nextra = ["py/ignored.txt"]\n'))
        r = self.run_tool(app, "--keep")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.kept(r) / "py" / "ignored.txt").exists())

    def test_temp_copy_removed_after_normal_run(self):
        r = self.run_tool(self.make_app())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_failing_suite_fails_and_others_still_run(self):
        extra = '\n[[suite]]\nname = "bad"\ndir = "py"\nrun = "echo boom; exit 1"\n\n[[suite]]\nname = "after"\ndir = "."\nrun = "true"\n'
        r = self.run_tool(self.make_app(self.toml() + extra))
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.rows(r)["bad"], "FAIL")
        self.assertEqual(self.rows(r)["after"], "PASS")
        self.assertIn("boom", r.stdout)

    def test_failing_setup_skips_its_suites(self):
        r = self.run_tool(self.make_app(self.toml('setup = []\noverlay', 'setup = ["exit 3"]\noverlay')))
        self.assertEqual(r.returncode, 1)
        rows = self.rows(r)
        self.assertEqual(rows["setup:py"], "FAIL")
        self.assertEqual((rows["overlay"], rows["isolated"]), ("SKIPPED", "SKIPPED"))
        self.assertEqual(rows["overrides"], "PASS")

    def test_timeout(self):
        extra = '\n[[suite]]\nname = "slow"\ndir = "."\nrun = "sleep 5"\ntimeout = 1\n'
        r = self.run_tool(self.make_app(self.toml() + extra))
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.rows(r)["slow"], "TIMEOUT")

    def test_validation_errors_exit_2_with_one_line(self):
        cases = {
            "version": self.toml("version = 1", "version = 2"),
            "lib": self.toml('"bond_storage"', '"bond_no_such_lib"'),
            "dir": self.toml('dir = "app"\npackages', 'dir = "../x"\npackages'),
            "suites": "version = 1\n",
            "parse": "version = [",
        }
        for label, text in cases.items():
            with self.subTest(label):
                app = self.make_app(text, dirty=False)
                r = self.run_tool(app)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertEqual(len(r.stderr.strip().splitlines()), 1, r.stderr)
                self.assertEqual(r.stdout, "")
                shutil.rmtree(app)

    def test_missing_config_exits_2(self):
        app = self.make_app(dirty=False)
        (app / ".bond-adopter.toml").unlink()
        r = self.run_tool(app)
        self.assertEqual(r.returncode, 2)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1)

    def test_tracked_pubspec_overrides_exits_2(self):
        app = self.make_app(dirty=False)
        (app / "app" / "pubspec_overrides.yaml").write_text("x: 1\n")
        r = self.run_tool(app)
        self.assertEqual(r.returncode, 2)
        self.assertIn("pubspec_overrides.yaml", r.stderr)

    def test_suite_flag_runs_one(self):
        r = self.run_tool(self.make_app(), "--suite", "overrides")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.rows(r), {"overrides": "PASS"})
        self.assertEqual(self.run_tool(self.make_app_again(), "--suite", "nope").returncode, 2)

    def make_app_again(self) -> Path:
        shutil.rmtree(self.tmp / "work")
        return self.make_app()

    def test_non_git_app_works(self):
        app = self.make_app(git=False, dirty=False)
        shutil.rmtree(app / ".git", ignore_errors=True)
        (app / "py" / "ignored.txt").write_text("x\n")  # no git: copied, not ignored
        before = tree_hash(app)
        r = self.run_tool(app, "--keep")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("no git", r.stdout)
        self.assertTrue((self.kept(r) / "py" / "ignored.txt").exists())
        self.assertEqual(tree_hash(app), before)

    def test_config_flag_reads_file_from_elsewhere(self):
        app = self.make_app(dirty=False)
        (app / ".bond-adopter.toml").unlink()
        cfg = self.tmp / "elsewhere.toml"
        cfg.write_text((STUB / ".bond-adopter.toml").read_text())
        self.assertEqual(self.run_tool(app).returncode, 2)
        r = self.run_tool(app, "--config", str(cfg))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(self.rows(r)), 3)

    def test_stub_overrides_list_every_sibling(self):
        r = self.run_tool(self.make_app(), "--keep")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = (self.kept(r) / "app" / "pubspec_overrides.yaml").read_text()
        for pkg in ("bond_tasks", "bond_api", "bond_json"):
            self.assertIn(f'path: "{BOND}/packages/{pkg}"\n', text)

    def test_closure_follows_sibling_paths_to_a_fixed_point(self):
        sys.path.insert(0, str(BOND / "tool"))
        from adopter_config import closure
        bond = self.tmp / "fakebond"
        for name, deps in {"a": ["b"], "b": ["c"], "c": [], "d": []}.items():
            d = bond / "packages" / name
            d.mkdir(parents=True)
            body = "".join(f"  {x}:\n    path: ../{x}\n" for x in deps)
            (d / "pubspec.yaml").write_text(f"name: {name}\ndependencies:\n{body}  http: ^1.0.0\n")
        self.assertEqual(sorted(closure(bond, ["a"])), ["a", "b", "c"])
        self.assertEqual(closure(bond, ["d"]), ["d"])

    def sleeper_app(self, run: str) -> Path:
        toml = f'version = 1\n\n[[suite]]\nname = "s"\ndir = "."\nrun = {run!r}\n'
        return self.make_app(toml, dirty=False)

    def alive(self, pid: int) -> bool:
        for _ in range(20):  # the kill is asynchronous
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return False
            time.sleep(0.1)
        return True

    def test_sigterm_removes_copy_and_kills_suite(self):
        pidfile = self.tmp / "pid"
        app = self.sleeper_app('sleep 300 & echo $! > "$PIDFILE"; wait')
        env = {**os.environ, "TMPDIR": str(self.scratch), "PIDFILE": str(pidfile)}
        proc = subprocess.Popen([sys.executable, str(TOOL), "--app", str(app), "--bond", str(BOND)],
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for _ in range(100):
            if pidfile.exists() and pidfile.read_text().strip():
                break
            time.sleep(0.1)
        pid = int(pidfile.read_text())
        proc.send_signal(signal.SIGTERM)
        proc.communicate(timeout=30)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(list(self.scratch.iterdir()), [])
        self.assertFalse(self.alive(pid), "the suite's background process survived SIGTERM")

    def test_background_process_is_killed_after_a_normal_run(self):
        pidfile = self.tmp / "pid"
        app = self.sleeper_app('sleep 300 & echo $! > "$PIDFILE"')
        old = os.environ.get("PIDFILE")
        os.environ["PIDFILE"] = str(pidfile)
        self.addCleanup(lambda: os.environ.pop("PIDFILE") if old is None else os.environ.update(PIDFILE=old))
        r = self.run_tool(app)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(self.alive(int(pidfile.read_text())))

    def test_symlinked_dir_leading_outside_exits_2_and_writes_nothing(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        app = self.sleeper_app("touch pwned")
        (app / "lnk").symlink_to(outside)
        toml = (app / ".bond-adopter.toml").read_text().replace('dir = "."', 'dir = "lnk"')
        (app / ".bond-adopter.toml").write_text(toml)
        subprocess.run(["git", "add", "-A"], cwd=app, check=True)
        r = self.run_tool(app)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_copy_extra_through_symlinked_parent_is_not_copied(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("s")
        app = self.make_app(self.toml('version = 1\n', 'version = 1\n\n[copy]\nextra = ["lnk/secret.txt"]\n'),
                            dirty=False)
        (app / "lnk").symlink_to(outside)
        before = (outside / "secret.txt").stat().st_mtime_ns
        r = self.run_tool(app, "--keep")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((outside / "py").exists())
        self.assertEqual((outside / "secret.txt").stat().st_mtime_ns, before)

    def test_dot_dot_lib_name_is_rejected(self):
        app = self.make_app(self.toml('"bond_storage"', '".."'), dirty=False)
        r = self.run_tool(app)
        self.assertEqual(r.returncode, 2)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1)

    def test_non_git_skips_only_root_and_project_build_dirs(self):
        app = self.make_app(git=False, dirty=False)
        for d in ("build", "other/build", "app/build", "app/.dart_tool"):
            (app / d).mkdir(parents=True, exist_ok=True)
            (app / d / "f.txt").write_text("x")
        r = self.run_tool(app, "--keep")
        copy = self.kept(r)
        self.assertFalse((copy / "build").exists())
        self.assertFalse((copy / "app" / "build").exists())
        self.assertFalse((copy / "app" / ".dart_tool").exists())
        self.assertTrue((copy / "other" / "build" / "f.txt").exists())

    def test_list_runs_nothing(self):
        r = self.run_tool(self.make_app(), "--list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("suite overlay", r.stdout)
        self.assertEqual(list(self.scratch.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
