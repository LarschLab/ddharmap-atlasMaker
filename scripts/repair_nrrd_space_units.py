#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import sys
import tempfile


DEFAULT_SPACE_UNIT = "microns"


class NrrdRepairError(ValueError):
    pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rewrite NRRD space units without recomputing image data."
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="NRRD files or preprocessed output directories to repair.",
    )
    parser.add_argument(
        "--unit",
        default=DEFAULT_SPACE_UNIT,
        help=f"Replacement unit token. Defaults to {DEFAULT_SPACE_UNIT!r}.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report files that would change without rewriting them.",
    )
    args = parser.parse_args()

    try:
        files = _collect_nrrd_files(args.paths)
        changed = 0
        for path in files:
            result = repair_nrrd_space_units(path, unit=args.unit, dry_run=args.dry_run)
            status = "would update" if args.dry_run and result else "updated"
            if result:
                changed += 1
                print(f"{status}: {path}")
            else:
                print(f"unchanged: {path}")
        change_label = "would change" if args.dry_run else "changed"
        print(f"{changed} of {len(files)} file(s) {change_label}.")
    except NrrdRepairError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def repair_nrrd_space_units(
    path: Path,
    *,
    unit: str = DEFAULT_SPACE_UNIT,
    dry_run: bool = False,
) -> bool:
    header, data_offset = _read_nrrd_header(path)
    new_header, changed = _replace_space_units(header, unit=unit)
    if not changed or dry_run:
        return changed

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(new_header)
            with path.open("rb") as source:
                source.seek(data_offset)
                shutil.copyfileobj(source, out)
        shutil.copystat(path, temp_path)
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return True


def _collect_nrrd_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.glob("*.nrrd")))
        elif path.is_file() and path.suffix.lower() == ".nrrd":
            files.append(path)
        else:
            raise NrrdRepairError(f"Expected a .nrrd file or directory: {path}")
    if not files:
        raise NrrdRepairError("No .nrrd files found.")
    return files


def _read_nrrd_header(path: Path) -> tuple[bytes, int]:
    header_lines: list[bytes] = []
    with path.open("rb") as source:
        while True:
            line = source.readline()
            if line == b"":
                raise NrrdRepairError(f"Could not find NRRD header delimiter: {path}")
            header_lines.append(line)
            if line in (b"\n", b"\r\n"):
                break
        data_offset = source.tell()
    header = b"".join(header_lines)
    if not header.startswith(b"NRRD"):
        raise NrrdRepairError(f"Expected NRRD magic header: {path}")
    return header, data_offset


def _replace_space_units(header: bytes, *, unit: str) -> tuple[bytes, bool]:
    lines = header.splitlines(keepends=True)
    replacement = f'space units: "{unit}" "{unit}" "{unit}"\n'.encode("ascii")
    for index, line in enumerate(lines):
        if not line.lower().startswith(b"space units:"):
            continue
        if line == replacement:
            return header, False
        newline = b"\r\n" if line.endswith(b"\r\n") else b"\n"
        lines[index] = replacement.rstrip(b"\n") + newline
        return b"".join(lines), True
    raise NrrdRepairError("NRRD header does not contain a space units field.")


if __name__ == "__main__":
    raise SystemExit(main())
