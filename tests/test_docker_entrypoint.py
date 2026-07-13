import os
import re
import subprocess
from pathlib import Path

import yaml

from src.config import DEFAULT_ALPHASIFT_INSTALL_SPEC


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_docker_entrypoint_has_valid_shell_syntax() -> None:
    subprocess.run(
        ["sh", "-n", str(REPO_ROOT / "docker" / "entrypoint.sh")],
        check=True,
    )


def test_dockerfile_uses_entrypoint_to_drop_privileges() -> None:
    dockerfile = (REPO_ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8")

    assert "gosu" in dockerfile
    assert 'ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]' in dockerfile
    assert "USER dsa" not in dockerfile


def test_docker_runtime_uses_vietnam_timezone() -> None:
    dockerfile = (REPO_ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8")
    compose = yaml.safe_load(
        (REPO_ROOT / "docker" / "docker-compose.yml").read_text(encoding="utf-8")
    )

    assert "ENV TZ=Asia/Ho_Chi_Minh" in dockerfile
    assert "Asia/Shanghai" not in dockerfile
    assert "ENV DATABASE_PATH=/app/data/stock_analysis_vn.db" in dockerfile
    assert "TZ=Asia/Ho_Chi_Minh" in compose["x-common"]["environment"]


def test_local_vietnam_environment_example_is_safe_by_default() -> None:
    defaults = {}
    for raw_line in (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        defaults[key] = value.split("#", 1)[0].strip()

    assert defaults["STOCK_LIST"] == "VNM.VN,MBB.VN"
    assert defaults["ENABLED_MARKETS"] == "vn"
    assert defaults["REPORT_LANGUAGE"] == "vi"
    assert defaults["REPORT_TYPE"] == "full"
    assert defaults["SCHEDULE_TIME"] == "15:10"
    assert defaults["SCHEDULE_TIMES"] == "09:20,15:10"
    assert defaults["SCHEDULE_TIMEZONE"] == "Asia/Ho_Chi_Minh"
    assert defaults["SCHEDULE_RUN_IMMEDIATELY"] == "false"
    assert defaults["TRADING_DAY_CHECK_ENABLED"] == "true"
    assert defaults["MARKET_REVIEW_ENABLED"] == "false"
    assert defaults["DAILY_MARKET_CONTEXT_ENABLED"] == "false"
    assert defaults["STOCK_INDEX_REMOTE_UPDATE_ENABLED"] == "false"
    assert defaults["NOTIFICATION_TIMEZONE"] == "Asia/Ho_Chi_Minh"
    assert defaults["MAX_WORKERS"] == "1"
    assert defaults["ENABLE_VN_ADVANCED_FLOW"] == "false"
    assert defaults["DATABASE_PATH"] == "./data/stock_analysis_vn.db"


def test_dockerfile_bundles_default_alphasift_adapter() -> None:
    dockerfile = (REPO_ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8")
    requirements = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert "git \\" in dockerfile
    assert f"{DEFAULT_ALPHASIFT_INSTALL_SPEC}#egg=alphasift" in requirements
    assert "pip install -r requirements.txt" in dockerfile
    assert "--mount=type=cache,target=/root/.cache/pip" in dockerfile
    assert "import alphasift.dsa_adapter" in dockerfile


def test_docker_entrypoint_repairs_ownership_and_user_permissions() -> None:
    entrypoint = (REPO_ROOT / "docker" / "entrypoint.sh").read_text(encoding="utf-8")

    assert "directory_needs_repair" in entrypoint
    assert "has_unwritable_mount_path" in entrypoint
    assert "can_write_dir_as_app_user" in entrypoint
    assert "DATABASE_FILE" in entrypoint
    assert "/home/dsa/.longbridge" in entrypoint
    assert 'HOME="/home/dsa"' in entrypoint
    assert re.search(r"export\s+HOME\s+exec\s+gosu", entrypoint, re.DOTALL)
    assert re.search(r"\bchown\s+-R\b", entrypoint)
    assert re.search(r"\bchmod\s+-R\s+u\+rwX\b", entrypoint)
    assert re.search(r"gosu\s+\"\$APP_USER:\$APP_GROUP\"\s+test\s+-w", entrypoint)


def test_docker_compose_injects_env_without_single_file_env_mount() -> None:
    compose_text = (REPO_ROOT / "docker" / "docker-compose.yml").read_text(encoding="utf-8")
    compose = yaml.safe_load(compose_text)
    common = compose["x-common"]

    assert "../.env" in common["env_file"]
    assert "../.env:/app/.env" not in common["volumes"]
    assert not any(str(volume).startswith("../.env:") for volume in common["volumes"])
    assert "../longbridge_tokens:/home/dsa/.longbridge" in common["volumes"]


def test_docker_compose_default_memory_recommendation_is_not_512m() -> None:
    compose_text = (REPO_ROOT / "docker" / "docker-compose.yml").read_text(encoding="utf-8")
    compose = yaml.safe_load(compose_text)
    resources = compose["x-common"]["deploy"]["resources"]

    assert resources["limits"]["memory"] == "1G"
    assert resources["reservations"]["memory"] == "512M"
    assert "512M" in compose_text
    assert "MAX_WORKERS=1" in compose_text


def test_docker_memory_guides_describe_resource_profiles() -> None:
    doc_paths = (
        "docs/DEPLOY_EN.md",
        "docs/full-guide_EN.md",
        "docs/docker/zeabur-deployment.md",
    )

    for doc_path in doc_paths:
        doc = (REPO_ROOT / doc_path).read_text(encoding="utf-8")

        assert "512M" in doc
        assert "1G" in doc
        assert "2G+" in doc
        assert "MAX_WORKERS=1" in doc

    assert "[DEPLOY_EN.md](DEPLOY_EN.md)" in (
        REPO_ROOT / "docs" / "DEPLOY.md"
    ).read_text(encoding="utf-8")
    assert "[full-guide_EN.md](full-guide_EN.md)" in (
        REPO_ROOT / "docs" / "full-guide.md"
    ).read_text(encoding="utf-8")


def test_docker_guides_do_not_recommend_single_file_env_bind_mount() -> None:
    forbidden_mount_patterns = [
        r"\$\(pwd\)/\.env:/app/\.env",
        r"\.\./\.env:/app/\.env",
    ]

    for doc_path in ("docs/full-guide_EN.md",):
        doc = (REPO_ROOT / doc_path).read_text(encoding="utf-8")

        assert "--env-file .env" in doc
        assert "env_file:" in doc
        for pattern in forbidden_mount_patterns:
            assert re.search(pattern, doc) is None

    assert "[full-guide_EN.md](full-guide_EN.md)" in (
        REPO_ROOT / "docs" / "full-guide.md"
    ).read_text(encoding="utf-8")


def test_documented_compose_exec_commands_run_as_dsa() -> None:
    safe_exec_prefix = "docker-compose -f ./docker/docker-compose.yml exec -u dsa"
    unsafe_exec_prefix = "docker-compose -f ./docker/docker-compose.yml exec"

    for doc_path in ("docs/DEPLOY_EN.md",):
        doc = (REPO_ROOT / doc_path).read_text(encoding="utf-8")

        assert f"{safe_exec_prefix} stock-analyzer bash" in doc
        assert f"{safe_exec_prefix} stock-analyzer python main.py --no-notify" in doc
        assert f"{unsafe_exec_prefix} stock-analyzer bash" not in doc
        assert (
            f"{unsafe_exec_prefix} stock-analyzer python main.py --no-notify"
            not in doc
        )

    assert "[DEPLOY_EN.md](DEPLOY_EN.md)" in (
        REPO_ROOT / "docs" / "DEPLOY.md"
    ).read_text(encoding="utf-8")


def _write_fake_command(fakebin: Path, name: str, body: str) -> None:
    command = fakebin / name
    command.write_text(f"#!/bin/sh\n{body}", encoding="utf-8")
    command.chmod(0o755)


def _prepare_fake_entrypoint_tools(tmp_path: Path, find_body: str) -> tuple[Path, Path]:
    fakebin = tmp_path / "bin"
    log_dir = tmp_path / "logs"
    fakebin.mkdir()
    log_dir.mkdir()

    _write_fake_command(
        fakebin,
        "id",
        'if [ "${1:-}" = "-u" ]; then printf "0\\n"; else printf "0\\n"; fi\n',
    )
    _write_fake_command(fakebin, "mkdir", "exit 0\n")
    _write_fake_command(fakebin, "find", find_body)
    _write_fake_command(
        fakebin,
        "chown",
        'printf "%s\\n" "$*" >> "$FAKE_LOG_DIR/chown.log"\n'
        'exit "${CHOWN_EXIT:-0}"\n',
    )
    _write_fake_command(
        fakebin,
        "chmod",
        'printf "%s\\n" "$*" >> "$FAKE_LOG_DIR/chmod.log"\n'
        'exit "${CHMOD_EXIT:-0}"\n',
    )
    _write_fake_command(
        fakebin,
        "gosu",
        'shift\n'
        'case "$1" in\n'
        '    sh|test) exit "${GOSU_WRITE_EXIT:-0}" ;;\n'
        'esac\n'
        'exec "$@"\n',
    )

    return fakebin, log_dir


def _run_entrypoint_with_fake_tools(
    fakebin: Path,
    log_dir: Path,
    *,
    gosu_write_exit: int,
    chown_exit: int,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = f"{fakebin}:{env['PATH']}"
    env["FAKE_LOG_DIR"] = str(log_dir)
    env["GOSU_WRITE_EXIT"] = str(gosu_write_exit)
    env["CHOWN_EXIT"] = str(chown_exit)

    return subprocess.run(
        ["sh", str(REPO_ROOT / "docker" / "entrypoint.sh"), "true"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def test_docker_entrypoint_repairs_nested_mount_ownership(tmp_path: Path) -> None:
    fakebin, log_dir = _prepare_fake_entrypoint_tools(
        tmp_path,
        'for arg in "$@"; do\n'
        '    if [ "$arg" = "-maxdepth" ]; then exit 0; fi\n'
        "done\n"
        'printf "%s/nested-root-owned\\n" "$1"\n',
    )

    _run_entrypoint_with_fake_tools(
        fakebin,
        log_dir,
        gosu_write_exit=0,
        chown_exit=0,
    )

    chown_log = (log_dir / "chown.log").read_text(encoding="utf-8")
    chmod_log = (log_dir / "chmod.log").read_text(encoding="utf-8")
    assert "/app/data" in chown_log
    assert "/app/logs" in chown_log
    assert "/app/reports" in chown_log
    assert "/app/data" in chmod_log


def test_docker_entrypoint_skips_owner_chmod_when_chown_fails(tmp_path: Path) -> None:
    fakebin, log_dir = _prepare_fake_entrypoint_tools(
        tmp_path,
        'printf "%s/root-owned\\n" "$1"\n',
    )

    result = _run_entrypoint_with_fake_tools(
        fakebin,
        log_dir,
        gosu_write_exit=1,
        chown_exit=1,
    )

    assert (log_dir / "chown.log").exists()
    assert not (log_dir / "chmod.log").exists()
    assert "skipping owner-only chmod" in result.stderr
    assert "still not writable by dsa" in result.stderr
