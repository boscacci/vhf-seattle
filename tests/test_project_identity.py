import subprocess
import tomllib
from pathlib import Path

OLD_REPO_SLUGS = ("-".join(("rpi", "for", "something")), "_".join(("rpi", "for", "something")))


def test_python_distribution_uses_elliott_bay_vhf_name() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["name"] == "elliott-bay-vhf"


def test_tracked_project_files_do_not_refer_to_placeholder_repo_name() -> None:
    tracked_files = subprocess.check_output(
        ["git", "ls-files", "-z"],
        text=True,
        encoding="utf-8",
    ).split("\0")

    stale_paths = []
    for raw_path in tracked_files:
        if not raw_path:
            continue
        path = Path(raw_path)
        if path.suffix in {".png", ".jpg", ".jpeg", ".webp", ".ico"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(old_slug in text for old_slug in OLD_REPO_SLUGS):
            stale_paths.append(raw_path)

    assert stale_paths == []


def test_native_mobile_app_development_scaffolding_is_removed() -> None:
    tracked_files = subprocess.check_output(
        ["git", "ls-files", "-z"],
        text=True,
        encoding="utf-8",
    ).split("\0")

    mobile_paths = [
        path
        for path in tracked_files
        if path.startswith("mobile/")
        or path in {
            "scripts/write_mobile_auth_env.sh",
            "scripts/configure_dev_google_cognito_idp.sh",
            "tests/test_mobile_app_shell.py",
        }
    ]

    assert mobile_paths == []
    assert not Path("mobile").exists()
