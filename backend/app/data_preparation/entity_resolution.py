"""Resolve aliases using exact source identities; reject ambiguous matches."""
from .contracts import Alias, Material

def build_aliases(materials: list[Material]) -> list[Alias]:
    aliases = {}
    for material in materials:
        for source in material.source_identities:
            identity = (source.table, source.record_id)
            if identity in aliases and aliases[identity].material_key != material.material_key:
                raise ValueError(f"Ambiguous source identity: {identity}")
            aliases[identity] = Alias(source_table=source.table, source_record_id=source.record_id,
                                      material_key=material.material_key, rule="verified_source_membership")
    return [aliases[k] for k in sorted(aliases)]

def resolve_calculator_pages(calculators: list[dict], pages: list[dict]) -> tuple[list[tuple[dict | None, dict]], list[dict]]:
    calc_by_id = {x["Id"]: x for x in calculators}
    if len(calc_by_id) != len(calculators):
        raise ValueError("Duplicate calculator IDs")
    used = set()
    pairs = []
    for page in pages:
        calc = calc_by_id.get(page["Id"])
        if calc is None:
            matches = [x for x in calculators if page.get("Url") and x.get("Url") == page["Url"]]
            if len(matches) > 1:
                raise ValueError("Ambiguous calculator URL alias")
            calc = matches[0] if matches else None
        if calc is not None:
            if calc["Id"] in used:
                raise ValueError("Several pages resolve to the same calculator")
            if page.get("Url") != calc.get("Url"):
                raise ValueError("Calculator/page identity conflict")
            used.add(calc["Id"])
        pairs.append((calc, page))
    return pairs, [x for x in calculators if x["Id"] not in used]
