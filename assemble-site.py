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

ALLOWED_ORIGIN = "https://mtomanxx.github.io"
ALLOWED_SITE_PATH = "/englishstudylab/"
SOURCE_BASE = ALLOWED_ORIGIN + ALLOWED_SITE_PATH.rstrip("/")


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


def apply_textbook_overlay(root, output):
    """Layer readable, versioned presentation files onto the verified course."""
    entry = output / "index.html"
    template = entry.read_text(encoding="utf-8")
    marker = "  </head>"
    if template.count(marker) != 1 or 'id="root"' not in template:
        raise ValueError("Unexpected entry point for the textbook overlay")
    tags = []
    for name, element in (
        ("textbook.css", '<link rel="stylesheet" href="{path}">'),
        ("textbook.js", '<script defer src="{path}"></script>'),
    ):
        artifact = output / "assets" / name
        if artifact.exists():
            raise ValueError(f"Textbook asset already exists: {name}")
        data = (root / "book-overlay" / name).read_bytes()
        version = hashlib.sha256(data).hexdigest()[:12]
        artifact.write_bytes(data)
        tags.append("    " + element.format(path=f"assets/{name}?v={version}"))
    membership = output / "membership"
    membership.mkdir(exist_ok=False)
    for name in ("index.html", "membership.css", "membership.js", "config.js", "enabled.js"):
        (membership / name).write_bytes((root / "book-overlay" / "membership" / name).read_bytes())
    practice = output / "practice"
    practice.mkdir(exist_ok=False)
    for name in ("index.html", "practice.css", "practice.js", "exams.json"):
        (practice / name).write_bytes((root / "book-overlay" / "practice" / name).read_bytes())
    flag_hash = hashlib.sha256((membership / "enabled.js").read_bytes()).hexdigest()[:12]
    tags.insert(0, f'    <script defer src="membership/enabled.js?v={flag_hash}"></script>')
    entry.write_text(template.replace(marker, "\n".join(tags) + "\n" + marker), encoding="utf-8")


def apply_course_overlay(root, output):
    marker = root / "course-overlay.json"
    if not marker.exists():
        return
    data = json.loads(marker.read_text(encoding="utf-8"))
    if data.get("version") != 1 or data["archive"]["filename"] != "course-overlay.tar.gz":
        raise ValueError("Invalid course overlay specification")
    expected = {}
    permitted_replacements = {"assets/index-af0557abe4eb.js", "assets/index-DGCIrGSb.css", "index.html"}
    for spec in data["files"]:
        path = spec["path"]
        safe_path(path)
        if path in expected or not (path in permitted_replacements or path == "course-library-release.json" or path.startswith("course-audio/") and path.endswith(".mp3") and len(path.split("/")) == 2):
            raise ValueError(f"Unexpected course overlay output: {path}")
        before = output / path
        if path in permitted_replacements:
            baseline = spec["previous"]
            verified_bytes(before.read_bytes(), baseline)
        elif before.exists():
            raise ValueError(f"Course overlay would overwrite an existing file: {path}")
        expected[path] = spec
    verified_bytes((root / data["archive"]["filename"]).read_bytes(), data["archive"])
    seen = set()
    with tarfile.open(root / data["archive"]["filename"], mode="r:gz") as archive:
        for member in archive:
            safe_path(member.name)
            spec = expected.get(member.name)
            if spec is None or member.name in seen or not member.isfile() or member.size != spec["size"]:
                raise ValueError(f"Unexpected course overlay archive member: {member.name}")
            write_verified(output, archive.extractfile(member).read(spec["size"] + 1), spec)
            seen.add(member.name)
    if seen != set(expected):
        raise ValueError("Course overlay archive did not contain all declared files")
    print(f"Verified native course overlay: {len(seen)} files", flush=True)


def apply_phrasal_overlay(root, output):
    marker = root / "phrasal-overlay.json"
    if not marker.exists():
        return
    data = json.loads(marker.read_text(encoding="utf-8"))
    if data.get("version") != 1 or data["archive"]["filename"] != "phrasal-overlay.tar.gz":
        raise ValueError("Invalid phrasal-verb overlay specification")
    expected = {}
    exact = {"index.html", "assets/esl-phrasal-discover.js", "assets/esl-phrasal-discover.css",
             "phrasal-verbs/index.html", "phrasal-verbs/reader.css", "phrasal-verbs/reader.js",
             "phrasal-verbs/entries.js", "phrasal-verbs/release.json"}
    for spec in data["files"]:
        path = spec["path"]
        safe_path(path)
        audio = path.startswith("phrasal-verbs/audio/") and len(path.split("/")) == 3 and path.endswith(("-term.mp3", "-example.mp3"))
        if path in expected or (path not in exact and not audio):
            raise ValueError(f"Unexpected phrasal output: {path}")
        before = output / path
        if path == "index.html":
            verified_bytes(before.read_bytes(), spec["previous"])
        elif before.exists():
            raise ValueError(f"Phrasal overlay would overwrite an existing file: {path}")
        expected[path] = spec
    verified_bytes((root / data["archive"]["filename"]).read_bytes(), data["archive"])
    seen = set()
    with tarfile.open(root / data["archive"]["filename"], mode="r:gz") as archive:
        for member in archive:
            safe_path(member.name)
            spec = expected.get(member.name)
            if spec is None or member.name in seen or not member.isfile() or member.size != spec["size"]:
                raise ValueError(f"Unexpected phrasal overlay archive member: {member.name}")
            write_verified(output, archive.extractfile(member).read(spec["size"] + 1), spec)
            seen.add(member.name)
    if seen != set(expected):
        raise ValueError("Phrasal overlay archive did not contain all declared files")
    print(f"Verified phrasal overlay: {len(seen)} files", flush=True)


def apply_golden_exam_overlay(root, output):
    marker = root / "golden-exam-overlay.json"
    if not marker.exists():
        return
    data = json.loads(marker.read_text(encoding="utf-8"))
    if data.get("version") != 1 or data["archive"]["filename"] != "golden-exam-overlay.tar.gz":
        raise ValueError("Invalid golden exam overlay specification")
    exact = {"index.html", "practice/index.html", "practice/practice.js",
             "phrasal-verbs/index.html", "membership/index.html",
             "assets/index-af0557abe4eb.js", "assets/esl-golden-theme.css",
             "practice/release.json"}
    replacements = exact - {"assets/esl-golden-theme.css", "practice/release.json"}
    expected = {}
    for spec in data["files"]:
        path = spec["path"]
        safe_path(path)
        if path not in exact or path in expected:
            raise ValueError(f"Unexpected golden exam output: {path}")
        before = output / path
        if path in replacements:
            verified_bytes(before.read_bytes(), spec["previous"])
        elif before.exists():
            raise ValueError(f"Golden exam overlay would overwrite an existing file: {path}")
        expected[path] = spec
    if set(expected) != exact:
        raise ValueError("Golden exam overlay file set mismatch")
    verified_bytes((root / data["archive"]["filename"]).read_bytes(), data["archive"])
    seen = set()
    with tarfile.open(root / data["archive"]["filename"], mode="r:gz") as archive:
        for member in archive:
            safe_path(member.name)
            spec = expected.get(member.name)
            if spec is None or member.name in seen or not member.isfile() or member.size != spec["size"]:
                raise ValueError(f"Unexpected golden exam archive member: {member.name}")
            write_verified(output, archive.extractfile(member).read(spec["size"] + 1), spec)
            seen.add(member.name)
    if seen != exact:
        raise ValueError("Golden exam overlay archive did not contain all declared files")
    print(f"Verified golden exam workbook overlay: {len(seen)} files", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("_site"))
    parser.add_argument("--local-assets", type=Path, help="Offline validation only; workflow always downloads public files")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / "asset-manifest.json").read_text(encoding="utf-8"))
    if manifest["format"] != 1 or manifest["source_base"] != SOURCE_BASE:
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
            url = SOURCE_BASE + "/" + quote(spec["path"], safe="/")
            for attempt in range(3):
                try:
                    request = Request(url, headers={"User-Agent": "EnglishStudyLab-GitHubPages-Migration/1.0", "Accept-Encoding": "identity"})
                    with urlopen(request, timeout=60) as response:
                        final = urlparse(response.geturl())
                        if response.status != 200 or f"{final.scheme}://{final.netloc}" != ALLOWED_ORIGIN or not final.path.startswith(ALLOWED_SITE_PATH):
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
    apply_textbook_overlay(root, output)
    print("Textbook overlay added; verified content and media are unchanged", flush=True)
    apply_course_overlay(root, output)
    apply_phrasal_overlay(root, output)
    apply_golden_exam_overlay(root, output)


if __name__ == "__main__":
    main()
