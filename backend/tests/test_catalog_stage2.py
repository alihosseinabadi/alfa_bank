"""Catalog identity, extraction, access and reproducibility acceptance tests."""
import csv
import hashlib
import json
from pathlib import Path
import pytest
from conftest import refresh_manifest
from app.data_preparation.pipeline import build_catalog, load_manifest
from app.data_preparation.content import extract_text, parameter_text
from app.data_preparation.chunking import chunk_blocks, E5Tokenizer
from app.data_preparation.contracts import ContentBlock, Material, SourceIdentity
from app.data_preparation.entity_resolution import resolve_calculator_pages
from app.data_preparation.eligibility import public_chunks, can_retrieve, material_url
from app.data_preparation.audit import audit_catalog
from app.data_preparation.file_text import extract_local_file

def test_realistic_catalog_contract(source_dir,tokenizer):
    materials,aliases,blocks,links,manifest,_=build_catalog(source_dir)
    assert len(materials)==7
    assert len(aliases)==8
    assert len(links)==1
    course=next(m for m in materials if m.item_type=="course")
    assert course.listed_price==0 and course.price_is_missing
    assert course.access_type=="По подписке"
    assert course.price_rule.startswith("Courses.Cost:")
    document=next(m for m in materials if m.item_type=="document")
    assert document.listed_price is None
    chunks=chunk_blocks(materials,blocks,tokenizer,target_tokens=150)
    public=public_chunks(materials,chunks)
    assert not any("СЕКРЕТНЫЙ" in c.text for c in public)
    assert any("СЕКРЕТНЫЙ" in c.text for c in chunks)
    protected=next(c for c in chunks if "СЕКРЕТНЫЙ" in c.text)
    assert not can_retrieve(protected,course)
    assert not can_retrieve(protected,course,{course.material_key})
    assert can_retrieve(protected,course,{protected.entitlement_key})
    assert audit_catalog(materials,aliases,blocks,chunks,public,links,manifest)["passed"]

def test_idempotent_ids_and_source_order(source_dir,tokenizer):
    first=build_catalog(source_dir)
    second=build_catalog(source_dir)
    assert [m.model_dump() for m in first[0]]==[m.model_dump() for m in second[0]]
    assert [c.model_dump() for c in chunk_blocks(first[0],first[2],tokenizer,target_tokens=150)]==[
        c.model_dump() for c in chunk_blocks(second[0],second[2],tokenizer,target_tokens=150)]
    article=[b for b in first[2] if b.source_table=="ArticleEmbedItems"]
    assert [b.source_record_id for b in article]==["ab1","ab2"]

def test_markup_hidden_code_and_boundaries():
    html="<nav>menu</nav><h2>Заголовок</h2><p>Первый&nbsp;текст</p><p>Второй</p><script>attack()</script><span hidden>secret</span>"
    assert extract_text(html)=="Заголовок\n\nПервый текст\n\nВторой"
    assert parameter_text('{"items":["Шаг один","Шаг два"],"url":"secret.js"}')=="Шаг один\n\nШаг два"
    assert parameter_text('{"item":{"title":"Реклама","advCode":"x"}}')==""

def test_long_paragraph_fits_without_losing_text(tokenizer):
    m=Material(material_key="article:a",item_type="article",title="Тема",url="https://example.org/a",
        access_type="Открытый",publication_status="Опубликовано",is_discoverable=True,snapshot_id="s",
        extracted_at="t",source_identities=[SourceIdentity(table="Articles",record_id="a")])
    body="".join(str(i%10) for i in range(3000))
    block=ContentBlock(block_id="b",material_key=m.material_key,source_table="ArticleEmbedItems",
        source_record_id="b",order=1,text=body,access_scope="public")
    chunks=chunk_blocks([m],[block],tokenizer,target_tokens=100)
    assert len(chunks)>20 and all(c.token_count<=100 for c in chunks)
    assert "".join(c.text.split("\n\n",1)[1] for c in chunks)==body

def test_checksum_and_ambiguous_aliases_fail(source_dir):
    path=source_dir/"Courses.csv"
    path.write_text(path.read_text()+"\n")
    with pytest.raises(ValueError,match="checksum"):
        load_manifest(source_dir)
    with pytest.raises(ValueError,match="conflict"):
        resolve_calculator_pages([{"Id":"x","Url":"a"}],[{"Id":"x","Url":"b"}])

def test_orphan_block_fails(source_dir):
    path=source_dir/"ArticleEmbedItems.csv"
    path.write_text(path.read_text().replace("article1","unknown"))
    refresh_manifest(source_dir)
    with pytest.raises(ValueError,match="Orphan"):
        build_catalog(source_dir)

def test_unavailable_url_excluded_without_discarding_material(source_dir,tokenizer):
    materials,_,blocks,_,_,_=build_catalog(source_dir)
    article=next(m for m in materials if m.item_type=="article")
    article.url_state="unavailable"
    chunks=chunk_blocks(materials,blocks,tokenizer,target_tokens=150)
    assert any(c.material_key==article.material_key for c in chunks)
    assert not any(c.material_key==article.material_key for c in public_chunks(materials,chunks))

def test_supplied_file_format_validation(tmp_path):
    invalid=tmp_path/"sample.docx"
    invalid.write_text("not a zip")
    assert extract_local_file(invalid)==("","unsupported_or_invalid_format")
    text=tmp_path/"sample.txt"
    text.write_text("Текст",encoding="utf-8")
    assert extract_local_file(text)==("Текст","text")

def test_route_uses_only_supplied_slug():
    assert material_url("ndfl","calculator")=="https://kurs.alfabank.ru/calculators/ndfl/"
    assert material_url("","article")==""
    assert material_url("javascript:alert(1)","article")==""
    assert material_url("../other","article")==""

def test_pinned_e5_tokenizer_if_prepared(source_dir):
    directory=Path(__file__).resolve().parents[2]/"artifacts/e5-tokenizer"
    if not (directory/"catalog_tokenizer.json").exists():
        pytest.skip("Run prepare_catalog_tokenizer.py for real-tokenizer integration test")
    tokenizer=E5Tokenizer(directory)
    materials,_,blocks,_,_,_=build_catalog(source_dir)
    chunks=chunk_blocks(materials,blocks,tokenizer)
    assert chunks
    assert all(tokenizer.count(c.text)==c.token_count<=512 for c in chunks)

def test_reused_lesson_requires_separate_entitlements(source_dir,tokenizer):
    def append_copy(name,changes):
        path=source_dir/(name+".csv")
        with path.open() as f:
            reader=csv.DictReader(f)
            fields=reader.fieldnames
            rows=list(reader)
        row=dict(rows[0]); row.update(changes); rows.append(row)
        with path.open("w",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    append_copy("Courses",{"Id":"course2","Url":"course-2"})
    append_copy("ContentSettings",{"Id":"second-settings","EntityId":"course2"})
    append_copy("CourseLessonBindings",{"Id":"binding2","CourseId":"course2"})
    refresh_manifest(source_dir)
    materials,_,blocks,_,_,_=build_catalog(source_dir)
    chunks=chunk_blocks(materials,blocks,tokenizer,target_tokens=150)
    secret=[c for c in chunks if "СЕКРЕТНЫЙ" in c.text]
    assert len(secret)==2
    assert len({c.entitlement_key for c in secret})==2
    owners={m.material_key:m for m in materials}
    assert not can_retrieve(secret[1],owners[secret[1].material_key],{secret[0].entitlement_key})

def test_pdf_without_text_is_explicitly_marked(tmp_path):
    from pypdf import PdfWriter
    path=tmp_path/"scan.pdf"
    writer=PdfWriter(); writer.add_blank_page(width=100,height=100); writer.write(path)
    assert extract_local_file(path)==("","image_only_or_unreadable")

def test_docx_text_preserves_paragraphs(tmp_path):
    from zipfile import ZipFile
    path=tmp_path/"supplied.docx"
    with ZipFile(path,"w") as archive:
        archive.writestr("word/document.xml",'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Первый</w:t></w:r></w:p><w:p><w:r><w:t>Второй</w:t></w:r></w:p></w:body></w:document>')
    assert extract_local_file(path)==("Первый\n\nВторой","text")
