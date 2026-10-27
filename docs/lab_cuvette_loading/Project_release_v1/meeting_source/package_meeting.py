"""Package only the published meeting DOCX and two unchanged native videos.

No document authoring, GPU/model calls or network access. Run after the parent
has pushed and independently verified the supplied publication commit.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
DOC = "LabSim_环境与评测进展_20261028.docx"
EXPECTED = [DOC, "teacher_full.mp4", "pi05_collision.mp4"]
TRACKED_DOC = "docs/lab_cuvette_loading/Project_release_v1/report/" + DOC


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--published-commit", required=True)
    p.add_argument("--publication-receipt", type=Path, required=True,
                   help="Existing actual remote-SHA/CI receipt checked by parent")
    args = p.parse_args()
    source = args.source_dir.resolve(strict=True)
    target = args.output.resolve()
    if target.exists():
        raise ValueError("Refuse to overwrite an existing meeting package: " + str(target))
    if sorted(x.name for x in source.iterdir()) != sorted(EXPECTED):
        raise ValueError("Meeting source must contain only one DOCX and two named videos")
    commit = subprocess.check_output(["git", "rev-parse", args.published_commit + "^{commit}"],
                                    cwd=ROOT, text=True).strip()
    blob = subprocess.check_output(["git", "show", commit + ":" + TRACKED_DOC], cwd=ROOT)
    if hashlib.sha256(blob).hexdigest() != sha(source / DOC):
        raise ValueError("DOCX differs from the explicitly published commit")
    publication = args.publication_receipt.resolve(strict=True)
    media_receipt = json.loads((HERE / "meeting_build_receipt.json").read_text())
    media = {item["file"]: item for item in media_receipt["media"]}
    for name in EXPECTED[1:]:
        item = media[name]
        if sha(source / name) != item["sha256"] or sha(item["source"]) != item["sha256"]:
            raise ValueError("Media is not the unchanged original native video: " + name)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "x", zipfile.ZIP_STORED) as z:
        for name in EXPECTED:
            z.write(source / name, name)
    checks = []
    relative_links = []
    with tempfile.TemporaryDirectory(prefix="labsim-meeting-relocated-") as tmp:
        moved = Path(tmp) / "moved_directory"
        moved.mkdir()
        with zipfile.ZipFile(target) as z:
            if sorted(z.namelist()) != sorted(EXPECTED):
                raise ValueError("Unexpected member in meeting archive")
            z.extractall(moved)
        with zipfile.ZipFile(moved / DOC) as z:
            rels = ET.fromstring(z.read("word/_rels/document.xml.rels"))
            for rel in rels:
                link = rel.get("Target", "")
                if rel.get("TargetMode") == "External" and not link.startswith(("http:", "https:")):
                    if link not in EXPECTED[1:] or not (moved / link).is_file():
                        raise ValueError("Unresolved moved DOCX link: " + link)
                    relative_links.append(link)
        for name in EXPECTED:
            actual = moved / name
            if sha(actual) != sha(source / name):
                raise ValueError("Moved archive member hash differs: " + name)
            if actual.suffix == ".mp4":
                subprocess.run(["/usr/bin/ffmpeg", "-hide_banner", "-loglevel", "error",
                                "-i", str(actual), "-f", "null", "-"], check=True)
            checks.append({"file": name, "bytes": actual.stat().st_size,
                           "sha256": sha(actual), "moved_hash_verified": True,
                           "full_CPU_decode_passed": actual.suffix == ".mp4"})
    receipt = dict(schema="labsim.Project_release_v1.meeting_package.v1", archive=str(target),
        archive_bytes=target.stat().st_size, archive_SHA256=sha(target),
        published_commit=commit, tracked_doc=TRACKED_DOC,
        publication_receipt=str(publication), publication_receipt_SHA256=sha(publication),
        publication_remote_status_scope="Parent's actual receipt; packager performs no network query",
        exact_three_files=True, files=checks, relocated_relative_links=relative_links,
        source_media_unchanged=True, no_extra_documents_logs_JSON_CSV_code_or_images=True,
        source_dir=str(source), DOCX_QA=str(HERE / "meeting_final_media_QA.json"))
    (HERE / "meeting_final_package_receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"archive": str(target), "bytes": target.stat().st_size,
                      "sha256": receipt["archive_SHA256"], "files": 3}, ensure_ascii=False))


if __name__ == "__main__":
    main()
