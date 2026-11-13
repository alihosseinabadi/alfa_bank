"""Machine-readable catalog acceptance checks, without source text in reports."""
from collections import Counter
from .contracts import Material, Alias, ContentBlock, Chunk, ChildLink
from .eligibility import can_retrieve

def audit_catalog(materials: list[Material], aliases: list[Alias], blocks: list[ContentBlock],
                  chunks: list[Chunk], public: list[Chunk], links: list[ChildLink], source_manifest: dict) -> dict:
    owners = {m.material_key: m for m in materials}
    block_lookup = {(b.material_key, b.block_id): b for b in blocks}
    checks = {
        "unique_material_keys": len(owners) == len(materials),
        "unique_aliases": len({(a.source_table,a.source_record_id) for a in aliases}) == len(aliases),
        "unique_chunks": len({c.chunk_id for c in chunks}) == len(chunks),
        "all_aliases_resolve": all(a.material_key in owners for a in aliases),
        "all_blocks_resolve": all(b.material_key in owners for b in blocks),
        "all_children_resolve": all(l.material_key in owners for l in links),
        "all_chunk_sources_resolve": all(all((c.material_key,s) in block_lookup for s in c.source_block_ids) for c in chunks),
        "all_chunks_eligible": all(c.material_key in owners and owners[c.material_key].is_discoverable for c in chunks),
        "scope_isolation": all(all(block_lookup[(c.material_key,s)].access_scope == c.access_scope and
            block_lookup[(c.material_key,s)].entitlement_key == c.entitlement_key for s in c.source_block_ids) for c in chunks),
        "protected_chunks_have_entitlement": all(c.entitlement_key for c in chunks if c.access_scope=="entitled"),
        "public_index_has_no_protected_content": all(c.access_scope=="public" and can_retrieve(c,owners[c.material_key]) for c in public),
        "token_limits": all(0 < c.token_count <= 512 for c in chunks),
    }
    counts = {}
    for table, info in source_manifest["files"].items():
        if table in {"Courses","Articles","Documents","Webinars","Podcasts","Glossary","Calculators","CalculatorPages"}:
            represented = sum(a.source_table == table for a in aliases)
            counts[table] = {"source": info["rows"], "represented_by_alias": represented}
    checks["source_counts_reconcile"] = all(x["source"]==x["represented_by_alias"] for x in counts.values())
    checks["lesson_links_reconcile"] = len(links) == source_manifest["files"]["CourseLessonBindings"]["rows"]
    report = {
        "checks": checks, "passed": all(checks.values()), "source_reconciliation": counts,
        "materials": len(materials), "discoverable_by_database_rules": sum(m.is_discoverable for m in materials),
        "by_type": dict(Counter(m.item_type for m in materials)),
        "discovery_exclusions": dict(Counter(r for m in materials for r in m.exclusion_reasons)),
        "url_states": dict(Counter(m.url_state for m in materials)),
        "content_coverage": dict(Counter(m.content_coverage for m in materials)),
        "quality_flags": dict(Counter(r for m in materials for r in m.quality_flags)),
        "aliases":len(aliases), "blocks":len(blocks), "chunks":len(chunks),
        "public_chunks":len(public), "entitled_chunks":sum(c.access_scope=="entitled" for c in chunks),
        "child_links":len(links), "max_chunk_tokens":max((c.token_count for c in chunks),default=0),
        "missing_listed_price":sum(m.listed_price is None for m in materials),
        "raw_missing_price":sum(m.price_is_missing for m in materials),
        "price_rules":dict(Counter(m.price_rule for m in materials)),
        "limitations":["Live URL reachability does not establish entitlement or content correctness.",
                       "Metadata-only recordings have no supplied transcript.",
                       "Only supplied local files are extracted; remote file URLs are not downloaded."],
    }
    if not report["passed"]:
        raise ValueError("Catalog acceptance failed: " + str([k for k,v in checks.items() if not v]))
    return report
