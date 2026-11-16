"""Artificial catalog fixtures; no organizer records are committed."""
import csv
import hashlib
import json
import sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"backend"))
from app.data_preparation.source import EXPORT_COLUMNS
from app.data_preparation.materials import SOURCES

@pytest.fixture
def source_dir(tmp_path):
    rows={name:[] for name in EXPORT_COLUMNS}
    rows["Statuses"]=[{"Id":"published","Title":"Опубликовано"}]
    rows["CourseTypes"]=[{"Id":"open","Title":"Открытый","IsDeleted":"f"},{"Id":"subscription","Title":"По подписке","IsDeleted":"f"}]
    rows["Topics"]=[{"Id":"topic","Title":"Финансы","IsDeleted":"f","IsPublic":"t"}]
    rows["Tags"]=[{"Id":"tag","Title":"План","IsDeleted":"f"}]
    rows["Industries"]=[{"Id":"industry","Title":"Торговля","IsDeleted":"f"}]
    names={"course":"Courses","article":"Articles","document":"Documents","webinar":"Webinars","podcast":"Podcasts"}
    for _,kind,entity in SOURCES:
        item={"Id":kind+"1","Title":"Учебный "+kind,"Description":"<p>Полезное описание</p>",
              "Url":kind+"-sample","StatusId":"published","TypeId":"subscription" if kind=="course" else "open",
              "IsDeleted":"f","IsClosed":"f","IsPublic":"t","Duration":"1 час 20 мин",
              "Published":"2025-01-01","Cost":"","Content":"","FileId":"file1"}
        rows[names[kind]]=[item]
        settings=kind+"-settings"
        rows["ContentSettings"].append({"Id":settings,"EntityId":item["Id"],"EntityTypeId":entity,
              "StatusId":"published","TypeId":item["TypeId"],"IsDeleted":"f","Published":"2025-01-01"})
        for relation,key,value in [("Topics","TopicId","topic"),("Tags","TagId","tag"),("Industries","IndustryId","industry")]:
            rows["ContentSettings"+relation].append({"ContentSettingsId":settings,key:value,"Order":"1"})
    rows["Glossary"]=[{"Id":"g1","Title":"Маржа","Description":"Определение","Url":"marzha","StatusId":"published","IsDeleted":"f"}]
    rows["Calculators"]=[{"Id":"calc1","Title":"Калькулятор","Description":"Расчёт","Url":"calculator","IsDeleted":"f"}]
    rows["CalculatorPages"]=[{"Id":"calc1","Title":"Калькулятор","Description":"Расчёт","Url":"calculator","StatusId":"published","IsDeleted":"f"}]
    rows["Lessons"]=[{"Id":"l1","Title":"Урок","Description":"","Content":"","IsDeleted":"f","IsGroup":"f"}]
    rows["CourseLessonBindings"]=[{"Id":"binding1","CourseId":"course1","LessonId":"l1","Order":"1","IsTrial":"t","IsClosed":"f","ClosedUntil":""}]
    rows["LessonEmbedItems"]=[{"Id":"lb1","LessonId":"l1","Order":"1","Type":"0","HtmlContent":"<p>СЕКРЕТНЫЙ ТЕКСТ УРОКА</p>","Params":"{}"}]
    rows["ArticleEmbedItems"]=[{"Id":"ab2","ArticleId":"article1","Order":"2","Type":"0","HtmlContent":"<p>Второй абзац</p>","Params":"{}"},
        {"Id":"ab1","ArticleId":"article1","Order":"1","Type":"0","HtmlContent":"<h2>Первый заголовок</h2><p>Первый абзац</p>","Params":"{}"}]
    rows["Files"]=[{"Id":"file1","Title":"Документ","Url":"/file.pdf","Extension":"pdf","Size":"10","IsDeleted":"f"}]
    for name,columns in EXPORT_COLUMNS.items():
        with (tmp_path/(name+".csv")).open("w",encoding="utf-8",newline="") as stream:
            writer=csv.DictWriter(stream,fieldnames=columns,extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows[name])
    refresh_manifest(tmp_path)
    return tmp_path

def refresh_manifest(directory):
    files={}
    for name,columns in EXPORT_COLUMNS.items():
        path=directory/(name+".csv")
        with path.open() as stream:
            count=sum(1 for _ in csv.DictReader(stream))
        files[name]={"filename":path.name,"rows":count,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"columns":list(columns)}
    manifest={"snapshot_id":hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest(),
              "files":files,"extracted_at":"2026-01-01T00:00:00+00:00","source":"artificial_test"}
    (directory/"source_manifest.json").write_text(json.dumps(manifest))

class CharacterTokenizer:
    # A deliberately different budget model catches accidental hard-coded word counts.
    def count(self,text):
        return len(text)+2

@pytest.fixture
def tokenizer():
    return CharacterTokenizer()
