#!/usr/bin/env python3
"""
Package smoke test: artifact audit + runtime verification in an isolated venv.

All checks are derived dynamically from project metadata (pyproject.toml,
MANIFEST.in, setup.py, wheel contents) — no hardcoded package names, paths,
versions, or file lists.

Usage:
  python3 scripts/dev/smoketest_package.py            # audit existing dist/
  python3 scripts/dev/smoketest_package.py --build    # build first, then test
  python3 scripts/dev/smoketest_package.py --dist path/to/dist
  python3 scripts/dev/smoketest_package.py --python python3.12
"""

import argparse
import ast
import fnmatch
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional

try:
    import tomllib  # stdlib ≥ 3.11
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]  # pip install tomli
    except ImportError:
        sys.exit(
            "error: tomllib not available — upgrade to Python 3.11+ or: pip install tomli"
        )

# ── terminal output ───────────────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"


def _ok(msg: str) -> bool:
    print(f"  {GREEN}✓{RESET}  {msg}")
    return True


def _fail(msg: str) -> bool:
    print(f"  {RED}✗{RESET}  {msg}")
    return False


def _info(msg: str) -> None:
    print(f"  {DIM}·{RESET}  {msg}")


def _section(title: str) -> None:
    bar = "─" * (len(title) + 4)
    print(f"\n{BOLD}{bar}{RESET}\n{BOLD}  {title}{RESET}\n{BOLD}{bar}{RESET}\n")


def _last_stderr_line(proc: subprocess.CompletedProcess) -> str:
    lines = proc.stderr.strip().splitlines()
    return lines[-1] if lines else "(no stderr)"


# ── project introspection ─────────────────────────────────────────────────────


@dataclass
class ManifestConfig:
    """Parsed directives from MANIFEST.in."""

    banned_files: list[str] = field(default_factory=list)  # 'exclude' lines
    banned_dirs: list[str] = field(
        default_factory=list
    )  # 'prune'   lines (with trailing /)
    required_files: list[str] = field(default_factory=list)  # 'include' lines
    data_patterns: list[tuple] = field(default_factory=list)  # (dir, [globs])


@dataclass
class ProjectConfig:
    """Metadata derived entirely from project source files."""

    package_name: str
    python_candidates: list[str]  # newest-first binary names to try
    console_scripts: dict[str, str]  # {name: module:callable}
    manifest: ManifestConfig
    data_checks: list[tuple[str, str]]  # [(label, wheel_path)] from wheel + manifest


def _load_pyproject(root: Path) -> dict:
    with open(root / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)


def _parse_manifest(root: Path) -> ManifestConfig:
    cfg = ManifestConfig()
    for raw in (root / "MANIFEST.in").read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        directive, *rest = line.split()
        if directive == "exclude":
            cfg.banned_files.extend(rest)
        elif directive == "prune":
            cfg.banned_dirs.extend(f"{p}/" for p in rest)
        elif directive == "include":
            cfg.required_files.extend(rest)
        elif directive == "recursive-include" and len(rest) >= 2:
            cfg.data_patterns.append((rest[0], rest[1:]))
    return cfg


def _parse_console_scripts(root: Path) -> dict[str, str]:
    """Extract console_scripts from setup.py using the AST (no exec)."""
    source = (root / "setup.py").read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        is_setup = (isinstance(fn, ast.Name) and fn.id == "setup") or (
            isinstance(fn, ast.Attribute) and fn.attr == "setup"
        )
        if not is_setup:
            continue
        for kw in node.keywords:
            if kw.arg == "entry_points":
                ep = ast.literal_eval(kw.value)
                return {
                    entry.split("=", 1)[0].strip(): entry.split("=", 1)[1].strip()
                    for entry in ep.get("console_scripts", [])
                }
    return {}


def _python_candidates(pyproject: dict) -> list[str]:
    """
    Derive compatible Python binary names from the project's python version
    specifier, e.g. ">=3.10,<4" → ["python3.15", ..., "python3.10", "python3"].
    """
    spec = (
        pyproject.get("tool", {})
        .get("poetry", {})
        .get("dependencies", {})
        .get("python", ">=3.10")
    )
    min_match = re.search(r">=\s*(\d+)\.(\d+)", spec)
    major = int(min_match.group(1)) if min_match else 3
    min_minor = int(min_match.group(2)) if min_match else 10
    # Probe from a generous ceiling (15) down to the declared minimum.
    return [f"python{major}.{m}" for m in range(15, min_minor - 1, -1)] + [
        f"python{major}"
    ]


def _data_checks_from_wheel(
    wheel_path: Path,
    data_patterns: list[tuple],
) -> list[tuple[str, str]]:
    """
    For each recursive-include directory in MANIFEST.in, find one
    representative matching file in the wheel.  Returns [(label, wheel_path)].
    """
    with zipfile.ZipFile(wheel_path) as zf:
        wheel_names = sorted(zf.namelist())

    checks = []
    for directory, globs in data_patterns:
        for name in wheel_names:
            if not name.startswith(directory + "/"):
                continue
            filename = name.rsplit("/", 1)[-1]
            if any(fnmatch.fnmatch(filename, g) for g in globs):
                checks.append((f"data: {name}", name))
                break  # one representative per directory is enough
    return checks


def load_project_config(root: Path, wheel_path: Path) -> ProjectConfig:
    pyproject = _load_pyproject(root)
    manifest = _parse_manifest(root)
    return ProjectConfig(
        package_name=pyproject["tool"]["poetry"]["name"],
        python_candidates=_python_candidates(pyproject),
        console_scripts=_parse_console_scripts(root),
        manifest=manifest,
        data_checks=_data_checks_from_wheel(wheel_path, manifest.data_patterns),
    )


# ── sdist audit ───────────────────────────────────────────────────────────────

# The one sentinel: lockfiles have no place in a published sdist and the
# glob 'include *.lock' has bitten this project before.
_LOCKFILE_SENTINEL = "poetry.lock"


def audit_sdist(sdist_path: Path, cfg: ProjectConfig) -> bool:
    _section(f"sdist audit  ·  {sdist_path.name}")
    passed = True

    with tarfile.open(sdist_path, "r:gz") as tf:
        all_names = tf.getnames()

    prefix = all_names[0].rstrip("/") + "/"
    members = [n[len(prefix) :] for n in all_names if n != prefix.rstrip("/")]

    # Banned files — from MANIFEST.in 'exclude' directives
    for banned in cfg.manifest.banned_files:
        if banned in members:
            passed = _fail(f"banned file present: {banned}")
        else:
            _ok(f"absent (excluded): {banned}")

    # Lockfile sentinel — belt-and-suspenders against 'include *.lock' regressions
    if _LOCKFILE_SENTINEL in members:
        passed = _fail(f"lockfile present in sdist: {_LOCKFILE_SENTINEL}")
    else:
        _ok(f"absent (sentinel): {_LOCKFILE_SENTINEL}")

    # Banned directories — from MANIFEST.in 'prune' directives
    for banned_dir in cfg.manifest.banned_dirs:
        hits = [m for m in members if m.startswith(banned_dir)]
        if hits:
            passed = _fail(
                f"pruned directory present: {banned_dir}  ({len(hits)} entries)"
            )
        else:
            _ok(f"absent (pruned): {banned_dir}")

    # Required files — from MANIFEST.in 'include' directives
    for required in cfg.manifest.required_files:
        if required in members:
            _ok(f"required file present: {required}")
        else:
            passed = _fail(f"required file missing: {required}")

    _info(f"total sdist entries: {len(members)}")
    return passed


# ── wheel audit ───────────────────────────────────────────────────────────────


def audit_wheel(wheel_path: Path, cfg: ProjectConfig) -> bool:
    _section(f"wheel audit  ·  {wheel_path.name}")
    passed = True

    with zipfile.ZipFile(wheel_path) as zf:
        names = zf.namelist()
        names_set = set(names)

        # top_level.txt must contain exactly the package name
        tl = next((n for n in names if n.endswith("top_level.txt")), None)
        if tl:
            top_level = zf.read(tl).decode().strip().splitlines()
            if top_level == [cfg.package_name]:
                _ok(f"top_level.txt: {top_level}")
            else:
                passed = _fail(
                    f"top_level.txt unexpected: {top_level}  (expected [{cfg.package_name!r}])"
                )
        else:
            passed = _fail("top_level.txt not found")

        # entry_points.txt must contain every console_script from setup.py
        ep_file = next((n for n in names if n.endswith("entry_points.txt")), None)
        if ep_file:
            ep_text = zf.read(ep_file).decode()
            for cmd, target in cfg.console_scripts.items():
                entry = f"{cmd} = {target}"
                if entry in ep_text:
                    _ok(f"entry point registered: {entry}")
                else:
                    passed = _fail(f"entry point missing: {entry}")
        else:
            passed = _fail("entry_points.txt not found")

        # No non-package top-level directories (e.g. scripts/, tests/)
        pkg = cfg.package_name + "/"
        unexpected = {
            n.split("/")[0]
            for n in names
            if "/" in n
            and not n.startswith(pkg)
            and not n.split("/")[0].endswith(".dist-info")
            and not n.split("/")[0].endswith(".data")
        }
        if unexpected:
            passed = _fail(f"unexpected top-level dirs in wheel: {sorted(unexpected)}")
        else:
            _ok("no unexpected top-level directories in wheel")

        # Data files — one representative per recursive-include directory
        for label, wheel_entry in cfg.data_checks:
            if wheel_entry in names_set:
                _ok(label)
            else:
                passed = _fail(f"missing: {label}")

        _info(f"total wheel entries: {len(names)}")

    return passed


# ── venv helpers ──────────────────────────────────────────────────────────────


def _create_venv_with_wheel(
    parent: Path,
    cfg: ProjectConfig,
    wheel_path: Path,
    requested: Optional[str] = None,
) -> Path:
    """
    Find the first compatible Python (from the project's version spec) for
    which all wheel dependencies install cleanly, then return that venv.

    Skips candidates where pip fails (e.g. missing binary wheels for a
    too-new interpreter) rather than hard-coding a version ceiling.
    """
    candidates = [requested] if requested else cfg.python_candidates
    for name in candidates:
        found = shutil.which(name)
        if not found:
            continue
        python_bin = Path(found)
        ver_proc = subprocess.run(
            [python_bin, "--version"], capture_output=True, text=True
        )
        if ver_proc.returncode != 0:
            continue
        ver = ver_proc.stdout.strip()

        venv_path = parent / f"smoketest-{name}"
        subprocess.run(
            [python_bin, "-m", "venv", str(venv_path)], check=True, capture_output=True
        )
        pip = venv_path / "bin" / "pip"
        subprocess.run(
            [pip, "install", "-q", "-U", "pip", "setuptools"],
            check=True,
            capture_output=True,
        )

        r = subprocess.run(
            [pip, "install", "-q", str(wheel_path)], capture_output=True, text=True
        )
        if r.returncode == 0:
            _info(f"Python: {python_bin}  ({ver})")
            return venv_path

        _info(f"skipping {name} ({ver}): wheel install failed (missing binary wheels?)")

    raise RuntimeError(
        f"no compatible Python found among: {candidates}\n"
        "pass --python to specify one explicitly"
    )


def _py(venv_path: Path, stmt: str) -> subprocess.CompletedProcess:
    # cwd="/" prevents '' (project root) from appearing on sys.path,
    # which would make local namespace packages importable as false positives.
    return subprocess.run(
        [venv_path / "bin" / "python", "-c", stmt],
        capture_output=True,
        text=True,
        cwd="/",
    )


def _cli(venv_path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [venv_path / "bin" / "python", "-m", "nucypher.cli.main", *args],
        capture_output=True,
        text=True,
        cwd="/",
    )


# ── runtime checks ────────────────────────────────────────────────────────────


def _subpackages_from_wheel(wheel_path: Path, pkg_name: str) -> list[str]:
    """Return one dotted module path per direct subpackage of pkg_name."""
    with zipfile.ZipFile(wheel_path) as zf:
        names = zf.namelist()
    seen, result = set(), [pkg_name]
    for name in sorted(names):
        parts = name.split("/")
        if len(parts) == 3 and parts[0] == pkg_name and parts[2] == "__init__.py":
            sub = parts[1]
            if sub not in seen:
                seen.add(sub)
                result.append(f"{pkg_name}.{sub}")
    return result


def _cli_subcommands_from_wheel(wheel_path: Path, pkg_name: str) -> list[str]:
    """Discover CLI command names from {pkg}/cli/commands/*.py in the wheel."""
    with zipfile.ZipFile(wheel_path) as zf:
        names = zf.namelist()
    cmds = []
    for name in sorted(names):
        parts = name.split("/")
        if (
            len(parts) == 4
            and parts[0] == pkg_name
            and parts[1] == "cli"
            and parts[2] == "commands"
            and parts[3].endswith(".py")
            and not parts[3].startswith("_")
        ):
            cmds.append(parts[3][:-3])
    return cmds


def _data_runtime_stmt(pkg_name: str, wheel_entry: str) -> str:
    """Build an importlib.resources assertion for a data file in the package."""
    parts = wheel_entry.split("/")
    module = ".".join(parts[:-1])
    filename = parts[-1]
    if filename.endswith(".json"):
        return (
            f"import json, importlib.resources as ir; "
            f"assert json.loads((ir.files({module!r}) / {filename!r}).read_text())"
        )
    return (
        f"import importlib.resources as ir; "
        f"assert (ir.files({module!r}) / {filename!r}).read_text()"
    )


def runtime_checks(venv_path: Path, wheel_path: Path, cfg: ProjectConfig) -> bool:
    _section("runtime checks")
    passed = True

    # — version flag -----------------------------------------------------------
    r = _cli(venv_path, "--version")
    out = (r.stdout + r.stderr).strip()
    if r.returncode == 0 and out:
        _ok(f"--version  →  {out.splitlines()[-1]}")
    elif r.returncode == 0:
        _ok("--version  →  exit 0")
    else:
        passed = _fail(f"--version failed: {_last_stderr_line(r)}")

    # — help + subcommands (derived from wheel) --------------------------------
    for args in [
        ("--help",),
        *(
            (cmd, "--help")
            for cmd in _cli_subcommands_from_wheel(wheel_path, cfg.package_name)
        ),
    ]:
        r = _cli(venv_path, *args)
        label = " ".join(args)
        if r.returncode == 0:
            _ok(f"{label}  →  exit 0")
        else:
            passed = _fail(f"{label} failed: {_last_stderr_line(r)}")

    # — package imports (derived from wheel subpackage structure) --------------
    for module in _subpackages_from_wheel(wheel_path, cfg.package_name):
        r = _py(venv_path, f"import {module}")
        if r.returncode == 0:
            _ok(f"import {module}")
        else:
            passed = _fail(f"import {module}  →  {_last_stderr_line(r)}")

    # — namespace leak guard ---------------------------------------------------
    # No directory adjacent to the package root should be importable.
    r = _py(venv_path, "import scripts")
    if r.returncode != 0:
        _ok("scripts namespace not importable (no leak)")
    else:
        passed = _fail("scripts namespace leaked into site-packages!")

    # — data files accessible at runtime (derived from wheel + manifest) -------
    for label, wheel_entry in cfg.data_checks:
        stmt = _data_runtime_stmt(cfg.package_name, wheel_entry)
        r = _py(venv_path, stmt)
        if r.returncode == 0:
            _ok(f"runtime readable: {label.replace('data: ', '')}")
        else:
            passed = _fail(f"runtime unreadable: {label}  →  {_last_stderr_line(r)}")

    return passed


# ── build + discovery ─────────────────────────────────────────────────────────


def build_package(project_root: Path) -> None:
    _section("build")
    dist_dir = project_root / "dist"
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
        _info("removed existing dist/")
    subprocess.run([sys.executable, "-m", "build", str(project_root)], check=True)
    _ok("build complete")


def find_artifacts(dist_dir: Path) -> tuple[Path, Path]:
    wheels = list(dist_dir.glob("*.whl"))
    sdists = list(dist_dir.glob("*.tar.gz"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected 1 wheel in {dist_dir}, found: {wheels}")
    if len(sdists) != 1:
        raise RuntimeError(f"expected 1 sdist in {dist_dir}, found: {sdists}")
    return sdists[0], wheels[0]


# ── main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Package smoke test — artifact audit + runtime verification"
    )
    parser.add_argument(
        "--build", action="store_true", help="run 'python -m build' before testing"
    )
    parser.add_argument(
        "--dist", default="dist", help="dist directory (default: dist/)"
    )
    parser.add_argument(
        "--python",
        default=None,
        help="Python interpreter for the test venv "
        "(default: auto-detect from pyproject.toml version spec)",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent.parent
    dist_dir = (project_root / args.dist).resolve()

    if args.build:
        build_package(project_root)

    sdist_path, wheel_path = find_artifacts(dist_dir)
    cfg = load_project_config(project_root, wheel_path)

    print(f"\n{BOLD}{CYAN}{cfg.package_name} · package smoke test{RESET}")
    print(f"{DIM}  project : {project_root}{RESET}")
    print(
        f"{DIM}  sdist   : {sdist_path.name}  ({sdist_path.stat().st_size // 1024} KB){RESET}"
    )
    print(
        f"{DIM}  wheel   : {wheel_path.name}  ({wheel_path.stat().st_size // 1024} KB){RESET}"
    )

    results: dict[str, bool] = {}
    results["sdist audit"] = audit_sdist(sdist_path, cfg)
    results["wheel audit"] = audit_wheel(wheel_path, cfg)

    _section("install + runtime")
    with TemporaryDirectory(prefix="smoketest-") as tmpdir:
        venv_path = _create_venv_with_wheel(
            Path(tmpdir), cfg, wheel_path, requested=args.python
        )
        _ok("installed into isolated venv")
        results["runtime"] = runtime_checks(venv_path, wheel_path, cfg)

    _section("summary")
    all_passed = all(results.values())
    for name, ok in results.items():
        (_ok if ok else _fail)(name)

    print()
    if all_passed:
        print(f"  {BOLD}{GREEN}all checks passed ✓{RESET}\n")
        sys.exit(0)
    else:
        print(f"  {BOLD}{RED}some checks failed ✗{RESET}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
