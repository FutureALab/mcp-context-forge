#!/usr/bin/env python3
"""Create an offline deployment archive from images and the checked-out commit."""

from __future__ import annotations

# Standard
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess  # nosec B404
import tarfile
import tempfile

DOCUMENTS = (
    "DEPLOY-INTRANET.md",
    "docs/docs/deployment/intranet-portal-gateway.md",
    "infra/portal-session-bridge/README.md",
    "infra/portal-session-bridge/portal-client.js",
)
LOCAL_PATHS = {".codex-memory", ".codegraph", ".cursor", ".git"}


def checksum(path: Path) -> str:
    """Return the SHA-256 digest of a file.

    Args:
        path: File to read.

    Returns:
        Hexadecimal digest.
    """
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def archive_source(root: Path, destination: Path) -> str:
    """Archive committed engineering files and exclude local configuration.

    Args:
        root: Checked-out repository.
        destination: Compressed source archive path.

    Returns:
        Source commit SHA.
    """
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()  # nosec B603 B607
    with tempfile.TemporaryFile() as raw:
        subprocess.run(["git", "archive", "--format=tar", sha], cwd=root, stdout=raw, check=True)  # nosec B603 B607
        raw.seek(0)
        with tarfile.open(fileobj=raw) as source, tarfile.open(destination, "w:gz") as target:
            for member in source:
                parts = Path(member.name).parts
                if any(part in LOCAL_PATHS or (part.startswith(".env") and part != ".env.example") for part in parts):
                    continue
                target.addfile(member, source.extractfile(member) if member.isfile() else None)
    return sha


def package(root: Path, args: argparse.Namespace) -> Path:
    """Build a deployment archive with pinned images and file checksums.

    Args:
        root: Checked-out repository.
        args: Validated command arguments.

    Returns:
        Deployment archive path.

    Raises:
        ValueError: Image metadata or version is invalid.
    """
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", args.version):
        raise ValueError("Version must be a valid Docker tag and file name")
    refs = (args.gateway_image, args.phoenix_image)
    inspected = json.loads(args.image_metadata.read_text(encoding="utf-8"))
    images = []
    for ref in refs:
        info = next((item for item in inspected if ref in (item.get("RepoTags") or [])), None)
        if info is None or info["Architecture"] != args.architecture or info["Os"] != "linux":
            raise ValueError(f"Missing linux/{args.architecture} image metadata for {ref}")
        images.append({"ref": ref, "id": info["Id"], "digests": info.get("RepoDigests") or []})

    with tarfile.open(args.image_archive, "r:gz") as archive:
        member = next((item for item in archive.getmembers() if item.name.lstrip("./") == "manifest.json"), None)
        stream = archive.extractfile(member) if member else None
        if stream is None:
            raise ValueError("Image archive has no Docker manifest.json")
        manifest = json.load(stream)
        tags = {tag for image in manifest for tag in (image.get("RepoTags") or [])}
        if not set(refs).issubset(tags):
            raise ValueError("Image archive does not contain every Compose image")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    name = f"contextforge-{args.version}-linux-{args.architecture}"
    with tempfile.TemporaryDirectory(dir=args.output_dir) as temporary:
        staging = Path(temporary) / name
        staging.mkdir()
        shutil.copyfile(args.image_archive, staging / "images.tar.gz")
        for filename in ("README.md", ".env.example", "init-env.sh"):
            shutil.copyfile(root / "infra/release-bundle" / filename, staging / filename)
        (staging / "init-env.sh").chmod(0o755)
        for filename in DOCUMENTS:
            destination = staging / filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / filename, destination)

        compose = (root / "docker-compose.phoenix-bundle.yml").read_text(encoding="utf-8")
        for variable, default, ref in zip(("GATEWAY_IMAGE", "PHOENIX_IMAGE"), ("mcpgateway/mcpgateway:latest", "arizephoenix/phoenix:latest"), refs):
            compose = compose.replace(f"image: ${{{variable}:-{default}}}", f"image: {ref}")
        compose = compose.replace("  gateway:\n", "  gateway:\n    env_file: .env\n")
        (staging / "docker-compose.yaml").write_text(compose, encoding="utf-8", newline="\n")
        sha = archive_source(root, staging / "source.tar.gz")
        metadata = {"version": args.version, "source_sha": sha, "platform": f"linux/{args.architecture}", "build_url": args.build_url, "images": images}
        (staging / "VERSION.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        sums = [f"{checksum(path)}  {path.relative_to(staging).as_posix()}\n" for path in sorted(staging.rglob("*")) if path.is_file()]
        (staging / "SHA256SUMS").write_text("".join(sums), encoding="utf-8")
        destination = Path(args.output_dir) / f"{name}.tar.gz"
        with tarfile.open(destination, "w:gz") as archive:
            archive.add(staging, arcname=name)
        destination.with_suffix(".gz.sha256").write_text(f"{checksum(destination)}  {destination.name}\n", encoding="utf-8")
        shutil.copyfile(staging / "docker-compose.yaml", args.output_dir / "docker-compose.yaml")
    return destination


def main() -> None:
    """Read build arguments and create the deployment archive."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--architecture", required=True, choices=("amd64", "arm64"))
    parser.add_argument("--gateway-image", required=True)
    parser.add_argument("--phoenix-image", required=True)
    parser.add_argument("--image-archive", required=True, type=Path)
    parser.add_argument("--image-metadata", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--build-url", default="")
    print(package(Path.cwd(), parser.parse_args()))


if __name__ == "__main__":
    main()
