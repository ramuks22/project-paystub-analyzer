#!/usr/bin/env python3
import json
import sys
import hashlib
from pathlib import Path


def compute_sha256(file_path: Path) -> str:
    hash_sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()


def validate_gold_dataset(manifest_path: Path):
    print(f"Validating Gold Dataset: {manifest_path}")
    if not manifest_path.exists():
        print("ERROR: manifest.json not found")
        sys.exit(1)

    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)

    entries = manifest.get("entries", [])

    # 1. Provider Diversity Check (Minimum 5 required)
    providers = {e.get("provider") for e in entries if e.get("provider")}
    print(f"- Providers found ({len(providers)}): {', '.join(providers)}")
    if len(providers) < 5:
        print(f"ERROR: Provider diversity target not met. Found {len(providers)}, need 5+.")
        sys.exit(1)

    # 2. Coverage Checks
    ids = {e["id"] for e in entries}
    required_ids = [
        "adp_standard",
        "gusto_clean",
        "trinet_complex",
        "paychex_classic",
        "workday_modern",
        "ocr_challenge",
    ]
    missing_ids = [rid for rid in required_ids if rid not in ids]
    if missing_ids:
        print(f"ERROR: Missing critical benchmark cases: {missing_ids}")
        sys.exit(1)
    else:
        print("- All critical benchmark cases present.")

    # 3. Integrity Checks (SHA-256)
    base_dir = manifest_path.parent
    for entry in entries:
        eid = entry["id"]
        expected_hashes = entry.get("sha256")
        if not expected_hashes:
            print(f"ERROR: Entry {eid} missing 'sha256' field in manifest.")
            sys.exit(1)

        paystubs_dir = base_dir / entry["inputs"]["paystubs_dir"]
        if not paystubs_dir.exists():
            print(f"ERROR: {eid} paystubs directory not found: {paystubs_dir}")
            sys.exit(1)

        files = list(paystubs_dir.glob("*.pdf"))
        if not files:
            print(f"ERROR: {eid} has no PDF fixtures in {paystubs_dir}")
            sys.exit(1)

        for fpath in files:
            actual_hash = compute_sha256(fpath)
            # Support both dict {filename: hash} and legacy single string
            if isinstance(expected_hashes, dict):
                expected_hash = expected_hashes.get(fpath.name)
                if not expected_hash:
                    # If file is not in manifest but exists in dir, it's an integrity fail
                    print(f"ERROR: Unexpected file {fpath.name} in {eid} directory. Not in manifest.")
                    sys.exit(1)
            else:
                expected_hash = expected_hashes

            if actual_hash != expected_hash:
                print(f"ERROR: SHA-256 mismatch for {eid} ({fpath.name})")
                print(f"  Expected: {expected_hash}")
                print(f"  Actual:   {actual_hash}")
                sys.exit(1)

        print(f"  [OK] {eid}: integrity verified.")

    print("\nSUCCESS: Gold Dataset manifest and fixture integrity verified.")


if __name__ == "__main__":
    manifest_p = Path(__file__).parent.parent / "tests" / "fixtures" / "gold" / "manifest.json"
    validate_gold_dataset(manifest_p)
