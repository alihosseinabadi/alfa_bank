"""Export a private immutable history snapshot with a separate allowlist."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.data_preparation.history_source import HISTORY_EXPORT_COLUMNS,read_history_table
from app.data_preparation.history_io import file_hash,write_json,verify_files
from app.data_preparation.chunking import digest

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--compose-file",type=Path,default=ROOT/"scripts/catalog-source.compose.yml")
    parser.add_argument("--output-dir",type=Path,default=ROOT/"data/interim/history")
    args=parser.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".export-",dir=args.output_dir) as directory:
        stage=Path(directory); files={}
        for name in sorted(HISTORY_EXPORT_COLUMNS):
            frame=read_history_table(name,args.compose_file)
            path=stage/(name+".csv")
            frame.to_csv(path,index=False,encoding="utf-8")
            files[name]={"filename":path.name,"columns":list(frame.columns),"rows":len(frame),"sha256":file_hash(path)}
            print(f"{name}: {len(frame)}",flush=True)
        identity=digest(files)
        manifest={"snapshot_id":identity,"files":files,"extracted_at":datetime.now(timezone.utc).isoformat(),
                  "source":"organizer_backup","contains_personal_history":True,
                  "timestamp_policy":"archive-month-v1","excluded_fields":["IP","CreatedById","ModifiedById"]}
        write_json(stage/"manifest.json",manifest)
        target=args.output_dir/identity
        if target.exists():
            existing=json.loads((target/"manifest.json").read_text())
            verify_files(target,existing)
            if existing["files"]!=files:
                raise ValueError("History snapshot collision")
        else:
            # Copy from a temp tree; publication rename remains on the same FS.
            stage.rename(target)
        pointer=args.output_dir/"CURRENT.tmp"
        pointer.write_text(identity+"\n")
        pointer.replace(args.output_dir/"CURRENT")
    print("History snapshot:",identity)

if __name__=="__main__":
    main()
