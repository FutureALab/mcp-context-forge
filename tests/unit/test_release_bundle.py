"""Regression tests for complete offline deployment archives."""

# Standard
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tarfile

# Third-Party
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
PACKAGER = runpy.run_path(str(ROOT / ".github/scripts/package_release_bundle.py"))


@pytest.fixture(name="bundle_inputs")
def _bundle_inputs(tmp_path: Path) -> tuple[Path, argparse.Namespace]:
    """Create a committed source fixture and a Docker manifest fixture."""
    root = tmp_path / "repository"
    root.mkdir()
    for filename in PACKAGER["DOCUMENTS"]:
        destination = root / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / filename, destination)
    shutil.copytree(ROOT / "infra/release-bundle", root / "infra/release-bundle")
    shutil.copyfile(ROOT / "docker-compose.phoenix-bundle.yml", root / "docker-compose.phoenix-bundle.yml")
    for filename in (".env", ".env.production", ".codex-memory/current-task.md", ".cursor/local.json", ".codegraph/local.db"):
        path = root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("local-only", encoding="utf-8")
    (root / "application.py").write_text("committed-source", encoding="utf-8")
    for command in (
        ["git", "init", "--quiet"],
        ["git", "add", "."],
        ["git", "-c", "user.name=Release Test", "-c", "user.email=release@example.com", "commit", "--quiet", "-m", "test fixture"],
    ):
        subprocess.run(command, cwd=root, check=True, capture_output=True)
    (root / "application.py").write_text("uncommitted-source", encoding="utf-8")
    refs = ("mcpgateway/mcpgateway:build-test", "arizephoenix/phoenix:test", "postgres:16-alpine")
    archive_path = tmp_path / "images.tar.gz"
    payload = json.dumps([{"RepoTags": [ref], "Layers": []} for ref in refs]).encode()
    with tarfile.open(archive_path, "w:gz") as archive:
        member = tarfile.TarInfo("manifest.json")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))
    metadata_path = tmp_path / "images.json"
    metadata = [{"RepoTags": [ref], "Architecture": "amd64", "Os": "linux", "Id": f"sha256:{index}", "RepoDigests": []} for index, ref in enumerate(refs)]
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    args = argparse.Namespace(
        version="build-test",
        architecture="amd64",
        gateway_image=refs[0],
        phoenix_image=refs[1],
        postgres_image=refs[2],
        image_archive=archive_path,
        image_metadata=metadata_path,
        output_dir=tmp_path / "assets",
        build_url="https://github.com/example/project/actions/runs/123",
    )
    return root, args


@pytest.mark.parametrize("architecture", ["amd64", "arm64"])
def test_complete_archive_and_committed_source(bundle_inputs: tuple[Path, argparse.Namespace], tmp_path: Path, architecture: str) -> None:
    """Require every deployment file, pinned image, and matching checksum."""
    root, args = bundle_inputs
    args.architecture = architecture
    metadata = json.loads(args.image_metadata.read_text())
    for image in metadata:
        image["Architecture"] = architecture
    args.image_metadata.write_text(json.dumps(metadata))
    output = PACKAGER["package"](root, args)
    assert output.with_suffix(".gz.sha256").read_text().split()[0] == hashlib.sha256(output.read_bytes()).hexdigest()
    extracted = tmp_path / "extracted"
    with tarfile.open(output) as archive:
        archive.extractall(extracted, filter="data")
    staging = extracted / f"contextforge-build-test-linux-{architecture}"
    for filename in ("images.tar.gz", "source.tar.gz", "VERSION.json", "README.md", ".env.example", "init-env.sh", "docker-compose.yaml", *PACKAGER["DOCUMENTS"]):
        assert (staging / filename).is_file()
    for line in (staging / "SHA256SUMS").read_text().splitlines():
        digest, filename = line.split("  ", 1)
        assert hashlib.sha256((staging / filename).read_bytes()).hexdigest() == digest
    compose = yaml.safe_load((staging / "docker-compose.yaml").read_text(encoding="utf-8"))
    assert [compose["services"][service]["image"] for service in ("gateway", "phoenix", "postgres")] == [args.gateway_image, args.phoenix_image, args.postgres_image]
    assert compose["services"]["gateway"]["env_file"] == ".env"
    version = json.loads((staging / "VERSION.json").read_text())
    assert version["source_sha"] == subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    assert version["platform"] == f"linux/{architecture}"
    assert len(version["images"]) == 3
    with tarfile.open(staging / "source.tar.gz") as source:
        names = source.getnames()
        stream = source.extractfile("application.py")
        assert stream is not None
        assert stream.read() == b"committed-source"
        assert "infra/release-bundle/.env.example" in names
        assert not any(name.startswith((".env", ".codex-memory", ".cursor", ".codegraph")) for name in names)


def test_reject_missing_postgres_image(bundle_inputs: tuple[Path, argparse.Namespace]) -> None:
    """Reject an image archive that cannot start the bundled database."""
    root, args = bundle_inputs
    payload = json.dumps([{"RepoTags": [args.gateway_image, args.phoenix_image]}]).encode()
    with tarfile.open(args.image_archive, "w:gz") as archive:
        member = tarfile.TarInfo("manifest.json")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))
    with pytest.raises(ValueError, match="every Compose image"):
        PACKAGER["package"](root, args)
    assert not args.output_dir.exists()


def test_reject_wrong_architecture(bundle_inputs: tuple[Path, argparse.Namespace]) -> None:
    """Reject a dependency image for another CPU architecture."""
    root, args = bundle_inputs
    metadata = json.loads(args.image_metadata.read_text())
    metadata[-1]["Architecture"] = "arm64"
    args.image_metadata.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="linux/amd64"):
        PACKAGER["package"](root, args)


def test_reject_invalid_version(bundle_inputs: tuple[Path, argparse.Namespace]) -> None:
    """Reject versions that can escape the deployment archive directory."""
    root, args = bundle_inputs
    args.version = "../invalid"
    with pytest.raises(ValueError, match="valid Docker tag"):
        PACKAGER["package"](root, args)


def bash_executable() -> str:
    """Find native Bash or Git Bash for workflow regression tests."""
    git = shutil.which("git")
    if os.name == "nt" and git:
        candidate = Path(git).resolve().parents[1] / "bin/bash.exe"
        if candidate.exists():
            return str(candidate)
    bash = shutil.which("bash")
    if not bash:
        raise RuntimeError("Bash is required for workflow regression tests")
    return bash


def workflow_step(job: str, name: str) -> str:
    """Read an executable workflow step by job and step name."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/docker-release-bundle.yml").read_text(encoding="utf-8"))
    return str(next(step["run"] for step in workflow["jobs"][job]["steps"] if step["name"] == name))


@pytest.mark.parametrize("event,release_tag,architectures", [("workflow_dispatch", "", "amd64"), ("workflow_dispatch", "v1.2.3", "both"), ("release", "v1.2.3", "")])
def test_workflow_resolves_actual_source(bundle_inputs: tuple[Path, argparse.Namespace], tmp_path: Path, event: str, release_tag: str, architectures: str) -> None:
    """Require automatic Release creation and immutable source metadata."""
    root, _ = bundle_inputs
    output = tmp_path / "outputs"
    env = os.environ | {
        "EVENT_NAME": event,
        "RELEASE_TAG": release_tag if event == "release" else "",
        "INPUT_RELEASE_TAG": release_tag if event != "release" else "",
        "INPUT_SOURCE_REF": "other-source-branch",
        "INPUT_ARCHITECTURES": architectures,
        "INPUT_PHOENIX_IMAGE": "registry.example:5000/phoenix",
        "INPUT_POSTGRES_IMAGE": "postgres:16-alpine",
        "REF": "refs/heads/dispatched-branch",
        "SHA": "incorrect-dispatched-sha",
        "REPOSITORY": "Example/Project",
        "RUN_ID": "123",
        "RUN_ATTEMPT": "2",
        "GITHUB_OUTPUT": output.as_posix(),
        "GITHUB_STEP_SUMMARY": (tmp_path / "summary").as_posix(),
    }
    subprocess.run([bash_executable(), "-c", workflow_step("prepare", "Resolve tag, version and build matrix")], cwd=root, env=env, check=True, capture_output=True)
    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    assert values["checkout_ref"] == sha
    assert values["release_tag"] == (release_tag or f"build-{sha[:7]}-123-2")
    assert values["upload_release"] == "true"
    assert values["phoenix_image"] == "registry.example:5000/phoenix:latest"
    expected = ["amd64", "arm64"] if event == "release" or architectures == "both" else ["amd64"]
    assert [entry["suffix"] for entry in json.loads(values["matrix"])] == expected


def test_init_env_preserves_existing_secrets(tmp_path: Path) -> None:
    """Generate secrets once and reject an existing deployment configuration."""
    shutil.copyfile(ROOT / "infra/release-bundle/init-env.sh", tmp_path / "init-env.sh")
    shutil.copyfile(ROOT / "infra/release-bundle/.env.example", tmp_path / ".env.example")
    command = [bash_executable(), "init-env.sh"]
    subprocess.run(command, cwd=tmp_path, check=True, capture_output=True)
    original = (tmp_path / ".env").read_bytes()
    values = dict(line.split("=", 1) for line in original.decode().splitlines())
    for key in ("JWT_SECRET_KEY", "AUTH_ENCRYPTION_SECRET", "PLATFORM_ADMIN_PASSWORD", "DEFAULT_USER_PASSWORD", "POSTGRES_PASSWORD"):
        assert len(values[key]) >= 32
    assert len({values[key] for key in ("JWT_SECRET_KEY", "AUTH_ENCRYPTION_SECRET", "PLATFORM_ADMIN_PASSWORD", "DEFAULT_USER_PASSWORD")}) == 4
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, check=False)
    assert result.returncode != 0
    assert (tmp_path / ".env").read_bytes() == original


@pytest.mark.parametrize("failure", ["", "source", "upload", "assets"])
def test_publish_only_complete_release(tmp_path: Path, failure: str) -> None:
    """Keep failed uploads and mismatched sources from publishing a new Release."""
    commands = tmp_path / "bin"
    commands.mkdir()
    gh = commands / "gh"
    gh.write_text(
        "#!/usr/bin/env bash\n"
        'printf "%s\\n" "$*" >> "${GH_TEST_LOG}"\n'
        'case "$1 $2" in\n'
        '  "release view")\n'
        '    if [[ "$*" == *"--json assets"* ]]; then printf "%s\\n" "${GH_TEST_ASSETS}";\n'
        '    elif [[ "$*" == *"--json url"* ]]; then echo "https://github.com/example/project/releases/tag/build-test";\n'
        "    else exit 1; fi ;;\n"
        '  "api "*) printf "%s\\n" "${GH_TEST_SOURCE}" ;;\n'
        '  "release upload") [[ "${GH_TEST_FAIL_UPLOAD}" != true ]] ;;\n'
        '  "release create"|"release edit") exit 0 ;;\n'
        "  *) exit 99 ;;\n"
        "esac\n",
        encoding="utf-8",
        newline="\n",
    )
    gh.chmod(0o755)
    runner = commands / "python3"
    runner.write_text(f"#!/usr/bin/env bash\nexec '{Path(sys.executable).as_posix()}' \"$@\"\n", encoding="utf-8", newline="\n")
    runner.chmod(0o755)
    assets = tmp_path / "release-assets"
    assets.mkdir()
    (assets / "bundle.tar.gz").write_bytes(b"test")
    log = tmp_path / "commands.log"
    env = os.environ | {
        "GH_TEST_LOG": log.as_posix(),
        "GH_TEST_ASSETS": json.dumps({"assets": [{"name": "bundle.tar.gz", "size": 0 if failure == "assets" else 4}]}),
        "GH_TEST_SOURCE": "other-commit" if failure == "source" else "built-commit",
        "GH_TEST_FAIL_UPLOAD": "true" if failure == "upload" else "false",
        "RELEASE_TAG": "build-test",
        "SOURCE_SHA": "built-commit",
        "GITHUB_REPOSITORY": "example/project",
        "GITHUB_RUN_ID": "123",
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_STEP_SUMMARY": (tmp_path / "summary").as_posix(),
    }
    command_path = f"/{commands.drive[0].lower()}{commands.as_posix()[2:]}" if os.name == "nt" else commands.as_posix()
    script = f'export PATH="{command_path}:$PATH"\n' + workflow_step("publish-release", "Create or update the complete GitHub Release")
    result = subprocess.run([bash_executable(), "-c", script], cwd=tmp_path, env=env, capture_output=True, check=False)
    assert log.exists(), result.stderr.decode("utf-8", errors="replace")
    calls = log.read_text().splitlines()
    assert any(call.startswith("release create ") and "--draft" in call for call in calls)
    assert (result.returncode == 0) == (failure == "")
    assert any(call.startswith("release edit ") and "--draft=false" in call for call in calls) == (failure == "")
    if failure == "source":
        assert not any(call.startswith("release upload ") for call in calls)
