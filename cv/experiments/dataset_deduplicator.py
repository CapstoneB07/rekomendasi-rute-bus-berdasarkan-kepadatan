import argparse
import csv
import hashlib
import shutil
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def sha256_file(path, chunk_size=1024 * 1024):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def phash(image, hash_size=8, highfreq_factor=4):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    size = hash_size * highfreq_factor
    gray = cv2.resize(gray, (size, size), interpolation=cv2.INTER_AREA)
    dct = cv2.dct(np.float32(gray))
    low = dct[:hash_size, :hash_size]
    med = np.median(low.flatten()[1:])
    return (low > med).astype(np.uint8).flatten()


def hamming(a, b):
    return int(np.count_nonzero(a != b))


def quality(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    contrast = float(gray.std())
    return blur, brightness, contrast


def unique_path(path):
    if not path.exists():
        return path
    for n in range(2, 100000):
        p = path.with_name(f"{path.stem}_{n}{path.suffix}")
        if not p.exists():
            return p
    raise RuntimeError("Terlalu banyak file dengan nama sama.")


def rel(path, root):
    return str(path.relative_to(root)).replace("\\", "/")


def main():
    parser = argparse.ArgumentParser(
        description="Deduplicate dataset ESP32-CAM dengan SHA256 + pHash."
    )
    parser.add_argument("--input", default="raw_dataset")
    parser.add_argument("--output", default="dataset_cleaned")
    parser.add_argument("--hash-threshold", type=int, default=5,
                        help="pHash Hamming distance <= nilai ini dianggap mirip.")
    parser.add_argument("--window", type=int, default=30,
                        help="Bandingkan dengan N gambar terakhir yang dipertahankan.")
    parser.add_argument("--blur-threshold", type=float, default=30.0)
    parser.add_argument("--dark-threshold", type=float, default=25.0)
    parser.add_argument("--bright-threshold", type=float, default=245.0)
    parser.add_argument("--contrast-threshold", type=float, default=10.0)
    args = parser.parse_args()

    root = Path(args.input).resolve()
    out = Path(args.output).resolve()
    clean = out / "clean_dataset"
    dup = out / "removed" / "duplicate"
    clean.mkdir(parents=True, exist_ok=True)
    dup.mkdir(parents=True, exist_ok=True)

    files = sorted(
        [p for p in root.rglob("*")
         if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS],
        key=lambda p: str(p).lower()
    )

    if not files:
        print(f"Tidak ada gambar di {root}")
        return

    exact_seen = {}
    recent = []  # (path, phash)
    rows = []
    stats = Counter()

    for i, path in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {path.name}", end="")

        image = cv2.imread(str(path))
        filename = rel(path, root)

        if image is None:
            stats["corrupt"] += 1
            rows.append([filename, "flagged", "corrupt_or_unreadable", "", "", "", "", ""])
            print(" -> CORRUPT")
            continue

        digest = sha256_file(path)

        if digest in exact_seen:
            original = exact_seen[digest]
            target = unique_path(dup / path.name)
            shutil.copy2(path, target)
            stats["exact_duplicate"] += 1
            rows.append([filename, "removed", "exact_duplicate",
                         rel(original, root), 0, digest, "", ""])
            print(f" -> EXACT DUPLICATE ({original.name})")
            continue

        exact_seen[digest] = path

        blur, brightness, contrast = quality(image)
        current_hash = phash(image)

        nearest = None
        nearest_dist = None

        for kept_path, kept_hash in recent:
            d = hamming(current_hash, kept_hash)
            if nearest_dist is None or d < nearest_dist:
                nearest_dist = d
                nearest = kept_path

        if nearest_dist is not None and nearest_dist <= args.hash_threshold:
            target = unique_path(dup / path.name)
            shutil.copy2(path, target)
            stats["near_duplicate"] += 1
            rows.append([filename, "removed", "near_duplicate",
                         rel(nearest, root), nearest_dist, digest,
                         round(blur, 3), round(brightness, 3)])
            print(f" -> NEAR DUPLICATE dist={nearest_dist} ({nearest.name})")
            continue

        target = unique_path(clean / path.name)
        shutil.copy2(path, target)
        recent.append((path, current_hash))
        if args.window > 0 and len(recent) > args.window:
            recent.pop(0)

        flags = []
        if blur < args.blur_threshold:
            flags.append("blurry")
        if brightness < args.dark_threshold:
            flags.append("too_dark")
        if brightness > args.bright_threshold:
            flags.append("too_bright")
        if contrast < args.contrast_threshold:
            flags.append("low_contrast")

        status = "kept_flagged" if flags else "kept"
        reason = "quality:" + "|".join(flags) if flags else "kept"
        stats[status] += 1

        rows.append([filename, status, reason, "",
                     nearest_dist if nearest_dist is not None else "",
                     digest, round(blur, 3), round(brightness, 3)])
        print(" -> " + status.upper() + (f" [{','.join(flags)}]" if flags else ""))

    report = out / "dedup_report.csv"
    with open(report, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "filename", "status", "reason", "similar_to",
            "phash_distance", "sha256", "blur_score", "brightness"
        ])
        writer.writerows(rows)

    print("\n=== SELESAI ===")
    print(f"Input             : {len(files)}")
    print(f"Kept              : {stats['kept']}")
    print(f"Kept + quality    : {stats['kept_flagged']}")
    print(f"Exact duplicate   : {stats['exact_duplicate']}")
    print(f"Near duplicate    : {stats['near_duplicate']}")
    print(f"Corrupt           : {stats['corrupt']}")
    print(f"Clean dataset     : {clean}")
    print(f"Duplicates        : {dup}")
    print(f"Report            : {report}")


if __name__ == "__main__":
    main()
