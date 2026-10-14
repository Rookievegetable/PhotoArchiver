#!/usr/bin/env python3
"""S4-B-2 Frozen Evaluation Baseline Audit — read-only audit script.

Audits the frozen round-1 calibration evaluation baseline directly against the
production database with a strictly read-only connection (``mode=ro`` URI +
``PRAGMA query_only=ON``). No INSERT/UPDATE/DELETE/ALTER/DROP/VACUUM/migration
and no INSERT+ROLLBACK probes are executed; frozen-only negative behavior is
carried by the formal test suite, not by production probes.

Core semantic ruling under audit (D-2 = Single Human Expert):

    88 GT rows = 44 SOURCE (dataset_id IS NULL)
               + 44 FROZEN membership (dataset_id=<target> AND
                 dataset_version='round-1')
               + 0 other

classified strictly by field lineage (dataset_id / dataset_version), never by
id order, created_at order or rowid.

    Evaluation N = 44 (one frozen membership row = one evaluation unit;
    logical key = (dataset_id, dataset_version, ground_truth_id)).

    The ONLY legal denominator query is
        WHERE dataset_id = <target> AND dataset_version = 'round-1'
    Raw COUNT(*) = 88, source+frozen = 88 and bare 88 are PROHIBITED as
    Precision / Recall / ROC / threshold-search denominators.

This script implements the audit scope of the Owner task book
"S4B2 Frozen Evaluation Baseline Audit" sections 8-18 (the read-only phases of
the audit plan; production write-probe phases are excluded by section 5). It
never starts precision/recall/CI/threshold work.

Exit codes: 0 = PASS, 1 = FAIL, 2 = BLOCKED (including "database could not be
opened read-only").
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATASET_ID = "ac0373d4-5493-4170-afab-ac6816cc515a"
DATASET_VERSION = "round-1"
TARGET_CLUSTER_RUN_ID = "a66943e7-1407-4b1c-836e-27c307a649a7"
EXPERT_ANNOTATOR_ID = "solu"

EXPECTED = {
    "dataset_rows": 1,
    "round1_datasets": 1,
    "frozen_datasets": 1,
    "raw_gt": 88,
    "source_gt": 44,
    "frozen_gt": 44,
    "other_gt": 0,
    "membership": 44,
    "evaluation_n": 44,
    "target_clusters": 44,
    "target_members": 1441,
    "verdicts": {"person": 36, "out_of_roster": 0, "undecidable": 8},
    "undecidable_other": 8,
    "business": {
        "cluster_person_assignments": 0,
        "person_face_embeddings": 0,
        "archive_records": 0,
        "recognition_results": 472,
        "people": 548,
        "photos": 473,
        "face_observations": 2882,
        "face_clusters": 80,
        "face_cluster_members": 1840,
    },
}

REQUIRED_TABLES = [
    "calibration_annotations",
    "calibration_ground_truth",
    "calibration_datasets",
    "recognition_runs",
    "recognition_run_photos",
    "face_observations",
    "face_cluster_runs",
    "face_clusters",
    "face_cluster_members",
    "cluster_person_assignments",
    "person_face_embeddings",
    "archive_records",
    "people",
    "photos",
    "recognition_results",
]

GT_REQUIRED_COLUMNS = {
    "id", "cluster_id", "verdict", "person_id", "difficulty_reason",
    "resolution", "source_annotation_ids", "annotator_count",
    "dataset_id", "dataset_version", "created_at",
}
GT_FORBIDDEN_COLUMNS = {"adjudicated_by"}

# Fields compared between source GT and frozen GT (task section 15).
PAYLOAD_FIELDS = [
    "verdict",
    "person_id",
    "difficulty_reason",
    "resolution",
    "annotator_count",
    "source_annotation_ids",
]


class Audit:
    """Collects check results; FAIL = data violates baseline, BLOCKED = cannot prove."""

    def __init__(self) -> None:
        self.entries: list[dict] = []
        self.current_phase = "?"

    def check(self, check_id: str, expected, actual) -> bool:
        ok = actual == expected
        self.entries.append({
            "phase": self.current_phase, "id": check_id,
            "expected": expected, "actual": actual,
            "verdict": "PASS" if ok else "FAIL",
        })
        flag = "PASS" if ok else "FAIL"
        print(f"  [{flag}] {check_id}: expected={expected!r} actual={actual!r}")
        return ok

    def blocked(self, check_id: str, reason: str) -> None:
        self.entries.append({
            "phase": self.current_phase, "id": check_id,
            "expected": "provable", "actual": f"BLOCKED: {reason}",
            "verdict": "BLOCKED",
        })
        print(f"  [BLOCKED] {check_id}: {reason}")

    def info(self, text: str) -> None:
        print(f"  [info] {text}")

    def phase(self, name: str) -> None:
        self.current_phase = name
        print(f"\n=== {name} ===")

    def verdict(self) -> str:
        flags = {e["verdict"] for e in self.entries}
        if "FAIL" in flags:
            return "FAIL"
        if "BLOCKED" in flags:
            return "BLOCKED"
        return "PASS"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_baseline(repo_root: Path) -> dict:
    out = {}
    for key, args in [
        ("HEAD", ["rev-parse", "HEAD"]),
        ("branch", ["branch", "--show-current"]),
        ("status", ["status", "--short"]),
    ]:
        try:
            result = subprocess.run(
                ["git", *args], cwd=str(repo_root), capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=30)
            out[key] = (result.stdout.strip() if result.returncode == 0
                        else f"<git error: {result.stderr.strip()}>")
        except Exception as exc:  # git absent is a reporting problem, not a DB fact
            out[key] = f"<unavailable: {exc}>"
    return out


def table_counts(con: sqlite3.Connection) -> dict[str, int]:
    tables = [
        row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
            " AND name NOT LIKE 'sqlite_%' ORDER BY name")
    ]
    return {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}


def parse_source_ids(raw: str) -> list[str]:
    value = json.loads(raw)
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ValueError(f"source_annotation_ids is not a list: {raw!r}")
    return [str(v) for v in value]


def finish(audit: Audit, early_block: bool = False) -> int:
    final = "BLOCKED" if early_block else audit.verdict()
    print("\n=== FINAL SUMMARY ===")
    print(f"total checks = {len(audit.entries)}  "
          f"PASS = {sum(1 for e in audit.entries if e['verdict'] == 'PASS')}  "
          f"FAIL = {sum(1 for e in audit.entries if e['verdict'] == 'FAIL')}  "
          f"BLOCKED = {sum(1 for e in audit.entries if e['verdict'] == 'BLOCKED')}")
    for entry in audit.entries:
        if entry["verdict"] != "PASS":
            print(f"  NON-PASS {entry['phase']} / {entry['id']}: "
                  f"expected={entry['expected']!r} actual={entry['actual']!r}")
    print(f"\nFROZEN-EVALUATION-BASELINE = {final}")
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[final]


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    db_path = Path(os.environ["LOCALAPPDATA"]) / "PhotoArchiver" / "photo_archiver.db"
    audit = Audit()

    print("# PhotoArchiver - S4B2 Frozen Evaluation Baseline Audit")
    print("## 2. Audit Mode")
    print("READ-ONLY: SQLite URI mode=ro + PRAGMA query_only=ON; no INSERT/UPDATE/"
          "DELETE/ALTER/DROP/VACUUM/migration/commit; production INSERT+ROLLBACK "
          "probes are FORBIDDEN this round (frozen-only negative behavior is "
          "carried by the formal test suite).")

    # ---- Phase 0: read-only guarantee, file fingerprints, git baseline --------
    audit.phase("Phase 0: read-only guarantee / fingerprints / git baseline")
    if not db_path.is_file():
        audit.blocked("db-exists", f"missing database file: {db_path}")
        return finish(audit, early_block=True)
    sidecars = {suffix: Path(str(db_path) + suffix) for suffix in ("-wal", "-shm")}
    present_before = {name: path for name, path in sidecars.items() if path.exists()}
    hash_before = {db_path.name: sha256_file(db_path)}
    for name, path in present_before.items():
        hash_before[name] = sha256_file(path)
    for name, digest in hash_before.items():
        audit.info(f"sha256 BEFORE {name} = {digest}")

    uri = "file:" + db_path.as_posix().replace(" ", "%20") + "?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True, isolation_level=None)
    except sqlite3.Error as exc:
        audit.blocked("db-open-ro", f"mode=ro open failed: {exc}")
        return finish(audit, early_block=True)
    con.execute("PRAGMA query_only=ON")
    audit.check("PRAGMA-query_only=ON", 1,
                con.execute("PRAGMA query_only").fetchone()[0])
    audit.info(f"journal_mode={con.execute('PRAGMA journal_mode').fetchone()[0]}"
               f" (WAL sidecars present at start: {sorted(present_before)}; readers"
               f" never append WAL frames, -shm is reader coordination memory only)")
    audit.check("connection-read-only-uri", True, uri.endswith("?mode=ro"))

    baseline = git_baseline(repo_root)
    print("## 3. Git Baseline")
    print(f"HEAD = {baseline['HEAD']}")
    print(f"branch = {baseline['branch']}")
    print(f"status --short:\n{baseline['status'] or '  (clean)'}")

    try:
        snapshot_before = table_counts(con)

        # ---- Phase 1: schema presence -----------------------------------------
        audit.phase("Phase 1: schema presence (sqlite_master / PRAGMA table_info)")
        existing = {
            row[0] for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")
        }
        missing = [t for t in REQUIRED_TABLES if t not in existing]
        audit.check("required-tables-present", [], missing)
        gt_cols = {row[1] for row in
                   con.execute("PRAGMA table_info(calibration_ground_truth)")}
        audit.check("gt-required-columns", sorted(GT_REQUIRED_COLUMNS),
                    sorted(GT_REQUIRED_COLUMNS & gt_cols))
        audit.check("gt-adjudicated_by-absent", [],
                    sorted(GT_FORBIDDEN_COLUMNS & gt_cols))

        # ---- Phase 2: dataset identity (task section 8) ------------------------
        audit.phase("Phase 2: dataset identity")
        n_target = con.execute(
            "SELECT COUNT(*) FROM calibration_datasets WHERE id = ?",
            (DATASET_ID,)).fetchone()[0]
        audit.check("target-dataset-exactly-once", EXPECTED["dataset_rows"], n_target)
        row = con.execute(
            "SELECT id, version, status, cluster_count, usable_count, excluded_count,"
            " protocol_version, created_at, notes FROM calibration_datasets"
            " WHERE id = ?", (DATASET_ID,)).fetchone()
        if row is None:
            audit.blocked("dataset-row-readable", "target dataset row missing")
        else:
            audit.info(f"dataset row: id={row[0]} version={row[1]} status={row[2]} "
                       f"cluster/usable/excluded={row[3]}/{row[4]}/{row[5]} "
                       f"protocol={row[6]} created_at={row[7]}")
            audit.check("dataset-version", DATASET_VERSION, row[1])
            audit.check("dataset-status-frozen", "frozen", row[2])
            audit.check("dataset-counts-44/44/0", (44, 44, 0), (row[3], row[4], row[5]))
        audit.check(
            "round-1-dataset-count", EXPECTED["round1_datasets"],
            con.execute("SELECT COUNT(*) FROM calibration_datasets WHERE version = ?",
                        (DATASET_VERSION,)).fetchone()[0])
        audit.check(
            "frozen-dataset-count", EXPECTED["frozen_datasets"],
            con.execute("SELECT COUNT(*) FROM calibration_datasets"
                        " WHERE status = 'frozen'").fetchone()[0])

        # ---- Phase 3: storage lineage classification (task section 8) ----------
        audit.phase("Phase 3: storage lineage classification "
                    "(by dataset_id/dataset_version fields only)")
        audit.info("classification is field-lineage ONLY: never id order, "
                   "created_at order or rowid")
        raw_gt = con.execute(
            "SELECT COUNT(*) FROM calibration_ground_truth").fetchone()[0]
        source_gt = con.execute(
            "SELECT COUNT(*) FROM calibration_ground_truth"
            " WHERE dataset_id IS NULL").fetchone()[0]
        frozen_gt = con.execute(
            "SELECT COUNT(*) FROM calibration_ground_truth"
            " WHERE dataset_id = ? AND dataset_version = ?",
            (DATASET_ID, DATASET_VERSION)).fetchone()[0]
        other_gt = con.execute(
            "SELECT COUNT(*) FROM calibration_ground_truth"
            " WHERE dataset_id IS NOT NULL"
            " AND NOT (dataset_id = ? AND dataset_version = ?)",
            (DATASET_ID, DATASET_VERSION)).fetchone()[0]
        audit.check("raw-gt-rows", EXPECTED["raw_gt"], raw_gt)
        audit.check("source-gt", EXPECTED["source_gt"], source_gt)
        audit.check("frozen-gt", EXPECTED["frozen_gt"], frozen_gt)
        audit.check("other-gt-category", EXPECTED["other_gt"], other_gt)
        audit.check("identity-88=44+44+0", 88, source_gt + frozen_gt + other_gt)
        source_versioned = con.execute(
            "SELECT COUNT(*) FROM calibration_ground_truth"
            " WHERE dataset_id IS NULL AND dataset_version IS NOT NULL"
        ).fetchone()[0]
        audit.check("source-rows-carry-no-dataset_version", 0, source_versioned)

        # ---- Phase 4: evaluation population (task section 9) --------------------
        audit.phase("Phase 4: evaluation population")
        audit.check("dataset-membership", EXPECTED["membership"], frozen_gt)
        audit.check("evaluation-N", EXPECTED["evaluation_n"], frozen_gt)
        audit.info("evaluation unit = one frozen dataset membership row; logical key"
                   " = (dataset_id, dataset_version, ground_truth_id)")
        key_count = con.execute(
            "SELECT COUNT(*) FROM (SELECT DISTINCT dataset_id, dataset_version, id"
            " FROM calibration_ground_truth"
            " WHERE dataset_id = ? AND dataset_version = ?)",
            (DATASET_ID, DATASET_VERSION)).fetchone()[0]
        audit.check("logical-sample-keys-unique", EXPECTED["evaluation_n"], key_count)
        distinct_gt_ids = con.execute(
            "SELECT COUNT(DISTINCT id) FROM calibration_ground_truth"
            " WHERE dataset_id = ? AND dataset_version = ?",
            (DATASET_ID, DATASET_VERSION)).fetchone()[0]
        audit.check("frozen-ground_truth_id-unique", EXPECTED["evaluation_n"],
                    distinct_gt_ids)
        distinct_clusters = con.execute(
            "SELECT COUNT(DISTINCT cluster_id) FROM calibration_ground_truth"
            " WHERE dataset_id = ? AND dataset_version = ?",
            (DATASET_ID, DATASET_VERSION)).fetchone()[0]
        audit.check("frozen-unique-cluster_id", EXPECTED["evaluation_n"],
                    distinct_clusters)
        audit.check("table-wide-gt-id-unique", 88,
                    con.execute("SELECT COUNT(DISTINCT id)"
                                " FROM calibration_ground_truth").fetchone()[0])

        # ---- Phase 5: target cluster set (task section 10) ----------------------
        audit.phase("Phase 5: target cluster set (more than bare COUNT)")
        n_clusters, n_distinct_clusters = con.execute(
            "SELECT COUNT(*), COUNT(DISTINCT id) FROM face_clusters"
            " WHERE cluster_run_id = ?", (TARGET_CLUSTER_RUN_ID,)).fetchone()
        audit.check("target-clusters", EXPECTED["target_clusters"], n_clusters)
        audit.check("target-cluster-ids-distinct", EXPECTED["target_clusters"],
                    n_distinct_clusters)
        n_members, n_distinct_obs = con.execute(
            "SELECT COUNT(*), COUNT(DISTINCT m.observation_id)"
            " FROM face_cluster_members m JOIN face_clusters c ON m.cluster_id = c.id"
            " WHERE c.cluster_run_id = ?", (TARGET_CLUSTER_RUN_ID,)).fetchone()
        audit.check("target-members", EXPECTED["target_members"], n_members)
        audit.check("target-member-distinct-observations", EXPECTED["target_members"],
                    n_distinct_obs)
        member_count_sum, empty_clusters = con.execute(
            "SELECT SUM(member_count), SUM(member_count <= 0) FROM face_clusters"
            " WHERE cluster_run_id = ?", (TARGET_CLUSTER_RUN_ID,)).fetchone()
        audit.check("member_count-column-sum==member-rows", n_members, member_count_sum)
        audit.check("empty-clusters-in-run", 0, empty_clusters)
        stray_members = con.execute(
            "SELECT COUNT(*) FROM face_cluster_members m"
            " JOIN face_clusters c ON m.cluster_id = c.id"
            " WHERE c.cluster_run_id = ? AND NOT EXISTS ("
            "  SELECT 1 FROM face_clusters t WHERE t.id = m.cluster_id"
            "  AND t.cluster_run_id = ?)",
            (TARGET_CLUSTER_RUN_ID, TARGET_CLUSTER_RUN_ID)).fetchone()[0]
        audit.check("members-referencing-out-of-run-clusters", 0, stray_members)
        sizes = [r[0] for r in con.execute(
            "SELECT member_count FROM face_clusters WHERE cluster_run_id = ?"
            " ORDER BY member_count", (TARGET_CLUSTER_RUN_ID,))]
        if sizes:
            audit.info(f"per-cluster size distribution: min={sizes[0]}"
                       f" median={sizes[len(sizes) // 2]} max={sizes[-1]}"
                       f" clusters={len(sizes)} sum={sum(sizes)}")

        # ---- Phase 6: membership reconciliation (task section 11) ----------------
        audit.phase("Phase 6: membership reconciliation "
                    "(FrozenGT cluster set vs Target cluster set)")
        target_ids = {r[0] for r in con.execute(
            "SELECT id FROM face_clusters WHERE cluster_run_id = ?",
            (TARGET_CLUSTER_RUN_ID,))}
        frozen_ids = {r[0] for r in con.execute(
            "SELECT cluster_id FROM calibration_ground_truth"
            " WHERE dataset_id = ? AND dataset_version = ?",
            (DATASET_ID, DATASET_VERSION))}
        audit.check("membership-Missing", 0, len(target_ids - frozen_ids))
        audit.check("membership-Unexpected", 0, len(frozen_ids - target_ids))
        dup = con.execute(
            "SELECT COUNT(*) FROM (SELECT cluster_id FROM calibration_ground_truth"
            " WHERE dataset_id = ? AND dataset_version = ?"
            " GROUP BY cluster_id HAVING COUNT(*) > 1)",
            (DATASET_ID, DATASET_VERSION)).fetchone()[0]
        audit.check("membership-Duplicate", 0, dup)

        # ---- Phase 7: ground-truth lineage (task section 12) ---------------------
        audit.phase("Phase 7: ground-truth lineage Frozen -> Source -> Annotation"
                    " -> Cluster")
        frozen_no_source = con.execute(
            "SELECT COUNT(*) FROM calibration_ground_truth f"
            " WHERE f.dataset_id = ? AND f.dataset_version = ?"
            " AND NOT EXISTS (SELECT 1 FROM calibration_ground_truth s"
            "  WHERE s.dataset_id IS NULL AND s.cluster_id = f.cluster_id)",
            (DATASET_ID, DATASET_VERSION)).fetchone()[0]
        audit.check("frozen-without-source", 0, frozen_no_source)
        source_no_frozen = con.execute(
            "SELECT COUNT(*) FROM calibration_ground_truth s"
            " WHERE s.dataset_id IS NULL"
            " AND NOT EXISTS (SELECT 1 FROM calibration_ground_truth f"
            "  WHERE f.dataset_id = ? AND f.dataset_version = ?"
            "  AND f.cluster_id = s.cluster_id)",
            (DATASET_ID, DATASET_VERSION)).fetchone()[0]
        audit.check("source-without-frozen", 0, source_no_frozen)
        src_groups_bad = con.execute(
            "SELECT COUNT(*) FROM (SELECT cluster_id FROM calibration_ground_truth"
            " WHERE dataset_id IS NULL GROUP BY cluster_id HAVING COUNT(*) <> 1)"
        ).fetchone()[0]
        frz_groups_bad = con.execute(
            "SELECT COUNT(*) FROM (SELECT cluster_id FROM calibration_ground_truth"
            " WHERE dataset_id = ? AND dataset_version = ?"
            " GROUP BY cluster_id HAVING COUNT(*) <> 1)",
            (DATASET_ID, DATASET_VERSION)).fetchone()[0]
        audit.check("one-to-many-pairs", 0, src_groups_bad)
        audit.check("many-to-one-pairs", 0, frz_groups_bad)
        audit.info("pairing key = cluster_id; 44 frozen <-> 44 source bijection")

        src_rows = con.execute(
            "SELECT id, cluster_id, verdict, person_id, difficulty_reason,"
            " resolution, source_annotation_ids, annotator_count, created_at"
            " FROM calibration_ground_truth WHERE dataset_id IS NULL").fetchall()
        ann_by_id = {
            r[0]: r for r in con.execute(
                "SELECT id, cluster_id, annotator_id, role, verdict, person_id,"
                " difficulty_reason, created_at FROM calibration_annotations")
        }
        audit.info(f"annotation roles present: "
                   f"{sorted({r[3] for r in ann_by_id.values()})}")
        lineage_bad = []
        ann_ids_seen = []
        for (gt_id, cluster_id, verdict, person_id, diff, _resolution,
             raw_ids, _count, _created) in src_rows:
            try:
                ids = parse_source_ids(raw_ids)
            except Exception as exc:
                lineage_bad.append(f"{gt_id}: unparseable source_annotation_ids ({exc})")
                continue
            if len(ids) != 1:
                lineage_bad.append(f"{gt_id}: source ids != 1")
                continue
            ann = ann_by_id.get(ids[0])
            if ann is None:
                lineage_bad.append(f"{gt_id}: annotation {ids[0]} missing")
                continue
            if ann[1] != cluster_id:
                lineage_bad.append(f"{gt_id}: annotation cluster mismatch")
                continue
            if (ann[4], ann[5], ann[6]) != (verdict, person_id, diff):
                lineage_bad.append(f"{gt_id}: annotation payload mismatch")
                continue
            if cluster_id not in target_ids:
                lineage_bad.append(f"{gt_id}: cluster outside target run")
                continue
            ann_ids_seen.append(ids[0])
        audit.check("source-gt-annotation-lineage-valid", 44, 44 - len(lineage_bad))
        for item in lineage_bad[:10]:
            audit.info(f"lineage violation: {item}")
        audit.check("annotations-consumed-unique", 44, len(set(ann_ids_seen)))

        # ---- Phase 8: expert protocol (task section 13) ---------------------------
        audit.phase("Phase 8: expert protocol on frozen GT")
        frozen_all = con.execute(
            "SELECT id, cluster_id, resolution, annotator_count, source_annotation_ids"
            " FROM calibration_ground_truth"
            " WHERE dataset_id = ? AND dataset_version = ?",
            (DATASET_ID, DATASET_VERSION)).fetchall()
        audit.check("frozen-rows-loaded", 44, len(frozen_all))
        audit.check("resolution-expert", 44,
                    sum(1 for r in frozen_all if r[2] == "expert"))
        audit.check("annotator-count-1", 44,
                    sum(1 for r in frozen_all if r[3] == 1))
        parsed_frozen = []
        for frow in frozen_all:
            try:
                ids = parse_source_ids(frow[4])
            except Exception:
                ids = []
            parsed_frozen.append((frow, ids))
        audit.check("source-annotation-ids-length-1", 44,
                    sum(1 for _, ids in parsed_frozen if len(ids) == 1))
        solu_n = 0
        annotators = set()
        join_bad = []
        for frow, ids in parsed_frozen:
            if len(ids) != 1:
                join_bad.append(f"{frow[0]}: no single source id")
                continue
            ann = ann_by_id.get(ids[0])
            if ann is None:
                join_bad.append(f"{frow[0]}: annotation {ids[0]} missing")
                continue
            if ann[1] != frow[1]:
                join_bad.append(f"{frow[0]}: annotation cluster mismatch")
                continue
            annotators.add(ann[2])
            if ann[2] == EXPERT_ANNOTATOR_ID:
                solu_n += 1
        audit.check("frozen-joinable-to-own-annotation", 44, 44 - len(join_bad))
        for item in join_bad[:10]:
            audit.info(f"join violation: {item}")
        audit.check("annotator-is-solu", 44, solu_n)
        audit.check("distinct-annotators", 1, len(annotators))

        # ---- Phase 9: verdict distribution (task section 14) ----------------------
        audit.phase("Phase 9: verdict distribution on frozen evaluation set")
        dist = dict(con.execute(
            "SELECT verdict, COUNT(*) FROM calibration_ground_truth"
            " WHERE dataset_id = ? AND dataset_version = ? GROUP BY verdict",
            (DATASET_ID, DATASET_VERSION)).fetchall())
        for verdict_name, expected_n in EXPECTED["verdicts"].items():
            audit.check(f"verdict-{verdict_name}", expected_n, dist.get(verdict_name, 0))
        audit.check("verdict-sum-44", 44, sum(dist.values()))
        und_other = con.execute(
            "SELECT COUNT(*) FROM calibration_ground_truth"
            " WHERE dataset_id = ? AND dataset_version = ?"
            " AND verdict = 'undecidable' AND difficulty_reason = 'other'",
            (DATASET_ID, DATASET_VERSION)).fetchone()[0]
        audit.check("undecidable-difficulty-reason-other",
                    EXPECTED["undecidable_other"], und_other)

        # ---- Phase 10: production write probes — EXCLUDED -------------------------
        audit.phase("Phase 10: production write probes — EXCLUDED (task section 5)")
        audit.info("No INSERT+ROLLBACK probes on production. Frozen-only negative"
                   " behavior (UNIQUE (id,version) reject, draft freeze rejection,"
                   " no update/delete in repo contract) is carried by the 47 formal"
                   " tests; this round reads only.")

        # ---- Phase 11: semantic payload comparison (task section 15) --------------
        audit.phase("Phase 11: semantic payload comparison source vs frozen"
                    " (keyed by cluster_id)")
        pairs = con.execute(
            "SELECT s.cluster_id,"
            " s.verdict, s.person_id, s.difficulty_reason, s.resolution,"
            " s.annotator_count, s.source_annotation_ids,"
            " f.verdict, f.person_id, f.difficulty_reason, f.resolution,"
            " f.annotator_count, f.source_annotation_ids,"
            " s.created_at, f.created_at,"
            " s.dataset_id, s.dataset_version, f.dataset_id, f.dataset_version"
            " FROM calibration_ground_truth s"
            " JOIN calibration_ground_truth f"
            "  ON f.cluster_id = s.cluster_id"
            " AND f.dataset_id = ? AND f.dataset_version = ?"
            " WHERE s.dataset_id IS NULL",
            (DATASET_ID, DATASET_VERSION)).fetchall()
        audit.check("payload-pairs-compared", 44, len(pairs))
        diffs = []
        stamping_bad = []
        # column layout: 0 s.cluster_id | 1-6 s payload | 7-12 f payload
        #                13 s.created_at | 14 f.created_at
        #                15/16 s.dataset_id/version | 17/18 f.dataset_id/version
        for pair in pairs:
            cluster_id = pair[0]
            for i, field in enumerate(PAYLOAD_FIELDS):
                if pair[1 + i] != pair[7 + i]:
                    diffs.append(f"{cluster_id}.{field}")
            if pair[15] is not None or pair[16] is not None:
                stamping_bad.append(f"{cluster_id}: source must be dataset-unstamped")
            if pair[17] != DATASET_ID or pair[18] != DATASET_VERSION:
                stamping_bad.append(f"{cluster_id}: frozen stamp mismatch")
            if not (pair[14] >= pair[13]):
                stamping_bad.append(f"{cluster_id}: frozen.created_at < source.created_at")
        audit.check("semantic-payload-differences", 0, len(diffs))
        for item in diffs[:10]:
            audit.info(f"payload diff: {item}")
        audit.check("dataset-stamping-structure", 0, len(stamping_bad))
        for item in stamping_bad[:10]:
            audit.info(f"stamping issue: {item}")
        audit.info("dataset_id / dataset_version / created_at are NOT semantic fields;"
                   " their change is the expected source->frozen snapshot structure")

        # ---- Phase 12: business isolation (task section 16) ------------------------
        audit.phase("Phase 12: business isolation counts")
        for table, expected_n in EXPECTED["business"].items():
            actual_n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            audit.check(f"business-{table}", expected_n, actual_n)

        # ---- Phase 13: query contract (task section 17) ----------------------------
        audit.phase("Phase 13: query contract")
        contract_sql = (
            "SELECT COUNT(*) FROM calibration_ground_truth "
            "WHERE dataset_id = 'ac0373d4-5493-4170-afab-ac6816cc515a' "
            "AND dataset_version = 'round-1'"
        )
        print(f"  [sql] {contract_sql}")
        contract_n = con.execute(contract_sql).fetchone()[0]
        audit.check("contract-denominator-query", 44, contract_n)
        audit.check("A-membership", contract_n, frozen_gt)
        b_person = con.execute(
            "SELECT COUNT(*) FROM calibration_ground_truth"
            " WHERE dataset_id = ? AND dataset_version = ? AND verdict = 'person'",
            (DATASET_ID, DATASET_VERSION)).fetchone()[0]
        c_und = con.execute(
            "SELECT COUNT(*) FROM calibration_ground_truth"
            " WHERE dataset_id = ? AND dataset_version = ? AND verdict = 'undecidable'",
            (DATASET_ID, DATASET_VERSION)).fetchone()[0]
        o_oor = con.execute(
            "SELECT COUNT(*) FROM calibration_ground_truth"
            " WHERE dataset_id = ? AND dataset_version = ? AND verdict = 'out_of_roster'",
            (DATASET_ID, DATASET_VERSION)).fetchone()[0]
        audit.check("B-PERSON", EXPECTED["verdicts"]["person"], b_person)
        audit.check("C-UNDECIDABLE", EXPECTED["verdicts"]["undecidable"], c_und)
        audit.check("O-OUT_OF_ROSTER", EXPECTED["verdicts"]["out_of_roster"], o_oor)
        audit.check("A=B+C+O", contract_n, b_person + c_und + o_oor)

        # ---- Phase 14: prohibited calibers (task section 18) ------------------------
        audit.phase("Phase 14: prohibited statistical calibers (statement)")
        audit.info(f"PROHIBITED: COUNT(*) FROM calibration_ground_truth = {raw_gt} as"
                   f" Evaluation N (88 = {source_gt} source + {frozen_gt} frozen)")
        audit.info(f"PROHIBITED: source GT + frozen GT = {source_gt + frozen_gt} as"
                   " evaluation sample count")
        audit.info("PROHIBITED: bare 88 as denominator for Precision / Recall / ROC /"
                   " threshold search or any downstream evaluation")
        audit.info("ONLY legal denominator: WHERE dataset_id=<target> AND"
                   " dataset_version='round-1' (= 44)")
    except sqlite3.Error as exc:
        audit.blocked("sql-execution", str(exc))
    except Exception as exc:  # noqa: BLE001 — audit must degrade to BLOCKED, not crash
        audit.blocked("unexpected-error", repr(exc))
    finally:
        try:
            # ---- Phase 15: write-evidence closure ---------------------------------
            audit.phase("Phase 15: write-evidence closure (no change caused by audit)")
            snapshot_after = table_counts(con)
            changed = {t: (snapshot_before[t], snapshot_after[t])
                       for t in snapshot_before
                       if snapshot_before[t] != snapshot_after[t]}
            audit.check("table-counts-invariant", {}, changed)
        except Exception as exc:  # noqa: BLE001
            audit.blocked("closure-counts", repr(exc))
        finally:
            try:
                con.close()
            except Exception:
                pass
        try:
            hash_after = {db_path.name: sha256_file(db_path)}
            for name, path in present_before.items():
                hash_after[name] = sha256_file(path)
            hash_changed = {key: (hash_before[key][:16], hash_after[key][:16])
                            for key in hash_before if hash_before[key] != hash_after[key]}
            audit.check("db-and-wal-bytes-invariant", {}, hash_changed)
            audit.info(f"sha256 AFTER {db_path.name} = {hash_after[db_path.name]}")
            audit.info("read-only connection + query_only=ON + zero write statements"
                       " issued")
        except Exception as exc:  # noqa: BLE001
            audit.blocked("closure-hashes", repr(exc))

    return finish(audit)


if __name__ == "__main__":
    sys.exit(main())
