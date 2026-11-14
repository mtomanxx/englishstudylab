#!/usr/bin/env python3
"""Restore a complete Pages artifact; verify every file before publication."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

ALLOWED_ORIGIN = "https://toman-yds-study-lab.mtoman.chatgpt.site"


def safe_path(value):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value or "?" in value or "#" in value or path.as_posix() != value:
        raise ValueError(f"Unsafe artifact path: {value!r}")
    return path


def verified_bytes(data, spec):
    if len(data) != spec["size"] or hashlib.sha256(data).hexdigest() != spec["sha256"]:
        raise ValueError(f"Size/hash mismatch: {spec.get('path', spec.get('filename'))}")
    return data


def write_verified(output, data, spec):
    target = output / safe_path(spec["path"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(verified_bytes(data, spec))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("_site"))
    parser.add_argument("--local-assets", type=Path, help="Offline validation only; workflow always downloads public files")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / "asset-manifest.json").read_text(encoding="utf-8"))
    if manifest["format"] != 1 or manifest["source_base"] != ALLOWED_ORIGIN:
        raise ValueError("Unexpected package format or source origin")
    expected = {}
    for spec in manifest["files"]:
        safe_path(spec["path"])
        if spec["path"] in expected or spec["source"] not in {"core", "public"} or not isinstance(spec["size"], int) or spec["size"] < 0:
            raise ValueError("Invalid or duplicate file specification")
        if len(spec["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in spec["sha256"]):
            raise ValueError("Invalid SHA256")
        expected[spec["path"]] = spec
    if len(expected) != manifest["summary"]["file_count"] or "index.html" not in expected:
        raise ValueError("Manifest file count/entry mismatch")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Output must be empty; refusing to overwrite existing files")
    core = manifest["core"]
    if core["filename"] != "site-core.tar.gz":
        raise ValueError("Unexpected core archive filename")
    verified_bytes((root / core["filename"]).read_bytes(), core)
    extracted = set()
    with tarfile.open(root / core["filename"], mode="r:gz") as archive:
        for member in archive:
            safe_path(member.name)
            spec = expected.get(member.name)
            if not member.isfile() or spec is None or spec["source"] != "core" or member.name in extracted or member.size != spec["size"]:
                raise ValueError(f"Unexpected archive member: {member.name}")
            fileobj = archive.extractfile(member)
            write_verified(output, fileobj.read(spec["size"] + 1), spec)
            extracted.add(member.name)
    if extracted != {path for path, spec in expected.items() if spec["source"] == "core"}:
        raise ValueError("Core archive file list mismatch")

    def fetch_file(spec):
        if args.local_assets:
            data = (args.local_assets / spec["path"]).read_bytes()
        else:
            url = ALLOWED_ORIGIN + "/" + quote(spec["path"], safe="/")
            for attempt in range(3):
                try:
                    request = Request(url, headers={"User-Agent": "EnglishStudyLab-GitHubPages-Migration/1.0", "Accept-Encoding": "identity"})
                    with urlopen(request, timeout=60) as response:
                        final = urlparse(response.geturl())
                        if response.status != 200 or f"{final.scheme}://{final.netloc}" != ALLOWED_ORIGIN:
                            raise ValueError(f"Unexpected HTTP response for {spec['path']}")
                        length = response.headers.get("Content-Length")
                        if length is not None and int(length) != spec["size"]:
                            raise ValueError(f"Unexpected response size for {spec['path']}")
                        data = response.read(spec["size"] + 1)
                    break
                except HTTPError as error:
                    if error.code < 500 or attempt == 2:
                        raise RuntimeError(f"Asset request failed: {spec['path']} (HTTP {error.code})") from None
                    time.sleep(attempt + 1)
                except (URLError, TimeoutError):
                    if attempt == 2:
                        raise RuntimeError(f"Asset request timed out: {spec['path']}") from None
                    time.sleep(attempt + 1)
        write_verified(output, data, spec)
        return spec["path"]

    downloads = [spec for spec in expected.values() if spec["source"] == "public"]
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(fetch_file, spec) for spec in downloads]
        try:
            for done, future in enumerate(as_completed(futures), 1):
                future.result()
                if done % 50 == 0 or done == len(downloads):
                    print(f"Verified public assets: {done}/{len(downloads)}", flush=True)
        except Exception:
            for future in futures:
                future.cancel()
            raise
    actual = {file.relative_to(output).as_posix() for file in output.rglob("*") if file.is_file()}
    if actual != set(expected):
        raise ValueError("Final artifact file list mismatch")
    for path, spec in expected.items():
        verified_bytes((output / path).read_bytes(), spec)
    total = sum(spec["size"] for spec in expected.values())
    audio_count = sum(path.endswith(".mp3") for path in expected)
    if total != manifest["summary"]["total_bytes"] or audio_count != manifest["summary"]["mp3_count"]:
        raise ValueError("Final artifact summary mismatch")
    print(f"Complete artifact verified: {len(actual)} files, {audio_count} MP3s, {total} bytes", flush=True)


if __name__ == "__main__":
    main()
