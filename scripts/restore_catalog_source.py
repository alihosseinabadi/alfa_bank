"""Restore the supplied archive only into an empty isolated source database."""
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
COMPOSE=ROOT/"scripts/catalog-source.compose.yml"

def main():
    backup=ROOT/"data/raw/alfa_course_hackathon.backup"
    if not backup.is_file() or backup.open("rb").read(5)!=b"PGDMP":
        raise ValueError("Place the supplied PGDMP archive in data/raw/alfa_course_hackathon.backup")
    base=["docker","compose","-f",str(COMPOSE)]
    subprocess.run(base+["up","-d","--wait"],check=True)
    db=base+["exec","-T","db"]
    count=subprocess.check_output(db+["psql","-X","-At","-U","alfa_ml","-d","alfa_course","-c",
        "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'"],text=True).strip()
    if count!="0":
        raise RuntimeError("Source database is already populated. Restore refused; use export_catalog_sources.py.")
    subprocess.run(db+["pg_restore","--single-transaction","--exit-on-error","--no-owner","--no-acl",
                       "-U","alfa_ml","-d","alfa_course","/backup/source.backup"],check=True)
    print("Source database restored. Organizer tables must remain read-only for preparation.")

if __name__=="__main__":
    main()
