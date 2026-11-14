"""Local file orchestration for prior ranking; no database or online learning."""
import json
from collections import defaultdict
from pathlib import Path
from app.ml.profile_contracts import UserProfile, ExplicitPreferences, PROFILE_SCHEMA_VERSION
from app.ml.user_profile import build_user_profile
from app.ml.request_context import build_request_context
from app.ml.ranking_contracts import RankingMaterial, ProgressSnapshot, ProgressEvidence
from app.ml.profile_policy import fingerprint
from app.ml.feature_registry import registry_document, REGISTRY_HASH
from .history_contracts import LearningState
from .history_io import resolve_bundle, load_catalog, read_jsonl, verify_files, publish_bundle, file_hash
from .retrieval_bundle import load_index

def load_ranking_catalog(index_dir, catalog_dir):
    catalog, _, _, manifest = load_catalog(Path(catalog_dir))
    index, search = load_index(Path(index_dir), catalog_bundle_id=manifest["bundle_id"])
    materials = [RankingMaterial(**{name: getattr(m, name) for name in RankingMaterial.model_fields}) for m in catalog]
    return index, search, materials

def project_progress(profile, states):
    grouped = defaultdict(list)
    if profile.mode == "historical":
        if states:
            raise ValueError("Historical context cannot use current learning state")
    else:
        for state in states:
            if state.user_key == profile.user_key:
                grouped[state.material_key].append(state)
    entries = []
    for key, rows in sorted(grouped.items()):
        fractions = [min(len(set(s.completed_lesson_ids)) / s.active_leaf_lesson_count, 1.0)
                     for s in rows if s.active_leaf_lesson_count > 0]
        entries.append(ProgressEvidence(material_key=key, completed=any(s.is_completed for s in rows),
            progress_fraction=max(fractions) if fractions else None))
    return ProgressSnapshot(user_key=profile.user_key, history_bundle_id=profile.history_bundle_id,
        mode=profile.mode, cutoff_month=profile.cutoff_month, entries=entries)

def load_ranking_context(materials, index_manifest, task, constraints, *, user_key=None,
                         profiles_dir=None, history_dir=None, explicit_preferences=None):
    states = []
    if user_key is None:
        profile = build_user_profile("synthetic:anonymous-demo", [], materials,
            explicit_preferences or ExplicitPreferences(),
            catalog_bundle_id=index_manifest["catalog_bundle_id"])
    else:
        if explicit_preferences is not None:
            raise ValueError("Persist onboarding through the profile pipeline before loading a saved user")
        path = resolve_bundle(Path(profiles_dir))
        manifest = json.loads((path / "manifest.json").read_text())
        verify_files(path, manifest)
        if (manifest["config"]["schema_version"] != PROFILE_SCHEMA_VERSION
                or manifest["catalog_bundle_id"] != index_manifest["catalog_bundle_id"]):
            raise ValueError("Incompatible profile/catalog bundle")
        profile = next((p for p in read_jsonl(path / "profiles.jsonl", UserProfile) if p.user_key == user_key), None)
        if profile is None:
            raise ValueError("Profile not found; omit --user-key for an anonymous context")
        if (profile.catalog_bundle_id != manifest["catalog_bundle_id"]
                or profile.history_bundle_id != manifest["history_bundle_id"]):
            raise ValueError("Profile/manifest mismatch")
        history_path = resolve_bundle(Path(history_dir))
        history = json.loads((history_path / "manifest.json").read_text())
        verify_files(history_path, history)
        if history["bundle_id"] != profile.history_bundle_id:
            raise ValueError("Profile/history mismatch")
        if profile.mode == "current":
            states = read_jsonl(history_path / "learning_state.jsonl", LearningState)
    context = build_request_context(profile, task, constraints, states)
    return profile, context, project_progress(profile, states)

def save_ranking(result, policy, output_dir, root):
    paths = list((root / "backend/app/ml").glob("*.py"))
    paths += [Path(__file__), root / "backend/app/data_preparation/retrieval_bundle.py",
              root / "backend/app/data_preparation/e5_bundle.py", root / "scripts/rank_materials.py"]
    metadata = {"ranking_version": result.version, "feature_registry_hash": REGISTRY_HASH,
        "policy_id": policy.identity(), "index_bundle_id": result.index_bundle_id,
        "catalog_bundle_id": result.catalog_bundle_id, "profile_version": result.profile_version,
        "retrieval_policy_id": result.retrieval_policy_id,
        "code_sha256": {str(p.relative_to(root)): file_hash(p) for p in sorted(paths)}}
    outputs = {"ranking.json": result.model_dump(), "policy.json": policy.model_dump(),
               "feature_registry.json": registry_document()}
    identity = fingerprint({"metadata": metadata, "outputs": outputs})
    return publish_bundle(Path(output_dir), identity, outputs, metadata)
