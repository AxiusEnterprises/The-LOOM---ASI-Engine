#!/usr/bin/env python3
"""
Compile all projects under ./projects/ into individual and combined zip archives
for upload to external software platforms.
"""

import argparse
import hashlib
import json
import os
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# Files/dirs to exclude from every zip
EXCLUDE_PATTERNS = {
    "__pycache__",
    ".git",
    ".gitkeep",
    ".DS_Store",
    "*.pyc",
    "*.pyo",
    "node_modules",
    ".env",
    ".venv",
    "venv",
    "dist",
    "build",
    "*.egg-info",
    ".pytest_cache",
    ".mypy_cache",
    "Thumbs.db",
}


def should_exclude(path: Path) -> bool:
    for pattern in EXCLUDE_PATTERNS:
        if pattern.startswith("*"):
            if path.suffix == pattern[1:] or path.name.endswith(pattern[1:]):
                return True
        elif path.name == pattern:
            return True
    return False


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_files(project_dir: Path) -> list[Path]:
    files = []
    for item in sorted(project_dir.rglob("*")):
        if item.is_file() and not any(
            should_exclude(Path(part)) for part in item.relative_to(project_dir).parts
        ) and not should_exclude(item):
            files.append(item)
    return files


def zip_project(project_dir: Path, output_path: Path) -> dict:
    files = collect_files(project_dir)
    file_entries = []

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for f in files:
            arcname = f.relative_to(project_dir.parent)
            zf.write(f, arcname)
            file_entries.append({
                "path": str(arcname),
                "sha256": sha256_file(f),
                "size": f.stat().st_size,
            })

    return {
        "name": project_dir.name,
        "zip": output_path.name,
        "sha256": sha256_file(output_path),
        "size": output_path.stat().st_size,
        "file_count": len(file_entries),
        "files": file_entries,
    }


def find_projects(projects_root: Path) -> list[Path]:
    return sorted(
        p for p in projects_root.iterdir()
        if p.is_dir() and not should_exclude(p)
    )


def compile_all(projects_root: Path, output_dir: Path, combined: bool) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    projects = find_projects(projects_root)
    if not projects:
        print(f"No projects found in {projects_root}")
        sys.exit(1)

    print(f"Found {len(projects)} project(s): {[p.name for p in projects]}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest = {
        "generated": timestamp,
        "projects_root": str(projects_root),
        "projects": [],
    }

    individual_zips: list[Path] = []

    for project_dir in projects:
        zip_name = f"{project_dir.name}_{timestamp}.zip"
        zip_path = output_dir / zip_name
        print(f"  Packaging {project_dir.name} -> {zip_path.name} ...", end=" ", flush=True)
        entry = zip_project(project_dir, zip_path)
        manifest["projects"].append(entry)
        individual_zips.append(zip_path)
        print(f"done ({entry['file_count']} files, {entry['size']:,} bytes)")

    if combined and len(projects) > 1:
        combined_name = f"all_projects_{timestamp}.zip"
        combined_path = output_dir / combined_name
        print(f"  Creating combined archive -> {combined_name} ...", end=" ", flush=True)
        with zipfile.ZipFile(combined_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for zip_path in individual_zips:
                zf.write(zip_path, zip_path.name)
        manifest["combined"] = {
            "zip": combined_name,
            "sha256": sha256_file(combined_path),
            "size": combined_path.stat().st_size,
        }
        print(f"done ({combined_path.stat().st_size:,} bytes)")

    manifest_path = output_dir / f"manifest_{timestamp}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"\nManifest written to {manifest_path}")
    print(f"Output directory: {output_dir.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile LOOM projects into zip archives for upload.",
    )
    parser.add_argument(
        "--projects-dir",
        default="projects",
        help="Directory containing project subdirectories (default: ./projects)",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory to write zip files (default: ./output)",
    )
    parser.add_argument(
        "--no-combined",
        action="store_true",
        help="Skip creating the combined all_projects zip",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List discovered projects without packaging",
    )
    args = parser.parse_args()

    root = Path(__file__).parent
    projects_root = root / args.projects_dir
    output_dir = root / args.output_dir

    if not projects_root.exists():
        print(f"Error: projects directory not found: {projects_root}")
        sys.exit(1)

    if args.list:
        projects = find_projects(projects_root)
        if not projects:
            print("No projects found.")
        else:
            for p in projects:
                files = collect_files(p)
                print(f"  {p.name}  ({len(files)} files)")
        return

    compile_all(projects_root, output_dir, combined=not args.no_combined)


if __name__ == "__main__":
    main()
