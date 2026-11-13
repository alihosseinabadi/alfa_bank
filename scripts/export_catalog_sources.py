"""Export only catalog tables, with per-file hashes and a snapshot manifest."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.data_preparation.source import EXPORT_COLUMNS, read_source_table

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compose-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/interim")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    for table in sorted(EXPORT_COLUMNS):
        frame = read_source_table(table, args.compose_file)
        path = args.output_dir / (table + ".csv")
        frame.to_csv(path, index=False, encoding="utf-8")
        files[table] = {"filename": path.name, "rows": len(frame), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "columns": list(frame.columns)}
        print(f"{table}: {len(frame)}")
    snapshot = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    manifest = {"snapshot_id": snapshot, "extracted_at": datetime.now(timezone.utc).isoformat(), "files": files,
                "source": "organizer_backup", "contains_user_history": False}
    (args.output_dir / "source_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("snapshot:", snapshot)

if __name__ == "__main__":
    main()
