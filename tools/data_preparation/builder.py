"""M1-09 组包编排：复算 RFM、构造 10+5 案例、生成两个标准 ZIP 与密封验收集（规格 5.2—5.6）。

流程（全部确定性，两次构建字节一致）：
1. 载入清洗后主表与客服任务 JSONL；
2. 在全部客户交易快照上复算 RFM（规格 5.3，先于案例筛选）；
3. 按锁定案例清单匹配主订单（对话 strip 精确匹配，取 order_id 最小者），
   逐个构造 CaseInput 字典与资产字节；
4. 生成 mapping_manifest 与 source manifest 确定性摘要，写入案例 provenance；
5. 组两个标准 ZIP（DEMO 10 案例 / ACCEPTANCE 5 案例），自校验通过后才写盘：
   - 每个 ZIP 用 ZipImportStage（M1-03）完整校验（结构/合同/泄漏/关系/媒体）；
   - 任一校验失败抛异常且不产生任何输出（可幂等重建）；
6. 写密封参考（答案/标签/轨迹等只进 sealed/，绝不进运行包）、对照案例与报告。

运行方式：
    python -m tools.data_preparation --source-root <逻辑源目录>
或设置环境变量 PSIT_SOURCE_ROOT 后直接运行。输出写入
runtime_data/mock_dataset_v1/（ADR-0033，不入 Git）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .case_builder import (
    build_case_input,
    build_control_case,
    detect_image,
    match_main_order,
    sealed_fields,
    sha256_bytes,
)
from .rfm import RfmResult, compute_rfm
from .sources import load_csv_rows, load_tasks, require_source_root
from .zip_output import json_bytes, make_checksums, write_standard_zip

# 任务卡 M1-09 锁定的案例清单（顺序即 case_no，勿改）。
DEMO_TASK_IDS = (
    "000000_a",
    "000001_a",
    "000002_a",
    "000004_a",
    "000005_a",
    "000007_a",
    "000008_a",
    "000010_a",
    "000011_a",
    "000012_a",
)
ACCEPTANCE_TASK_IDS = (
    "000003_a",
    "000006_a",
    "000009_a",
    "000051_a",
    "000074_a",
)

# 普通客户对照案例（不打包进 ZIP）。
CONTROL_CUSTOMER_ID = "7c142cf63193a1473d2e66489a9ae977"

DATA_VERSION = "mock_dataset_v1"
BUILDER_VERSION = "mock_dataset_builder.v1"
REPORT_SCHEMA_VERSION = "mock_dataset_report.v1"
MAPPING_SCHEMA_VERSION = "mapping_manifest.v1"

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_ROOT = _REPO_ROOT / "runtime_data" / "mock_dataset_v1"


def tasks_by_selection() -> list[str]:
    """锁定选择顺序：DEMO 在前、ACCEPTANCE 在后（顺序即 case_no）。"""
    return list(DEMO_TASK_IDS) + list(ACCEPTANCE_TASK_IDS)


def _selected_source_records(
    rows: list[dict[str, str]], tasks: dict[str, dict[str, object]]
) -> list[dict[str, object]]:
    """构造 source manifest 用的确定性记录视图（只含身份与原文内容）。"""
    records: list[dict[str, object]] = []
    for task_id in tasks_by_selection():
        task = tasks[task_id]
        records.append(
            {
                "task_id": task_id,
                "conversation": task.get("conversation") or "",
                "image_paths": [str(p) for p in (task.get("image_paths") or [])],
            }
        )
    control_rows = [
        row for row in rows if row["customer_unique_id"] == CONTROL_CUSTOMER_ID
    ]
    if not control_rows:
        raise ValueError(f"控制案例客户不存在：{CONTROL_CUSTOMER_ID}")
    main = control_rows[0]
    records.append(
        {
            "customer_unique_id": main["customer_unique_id"],
            "order_id": main["order_id"],
            "conversation": main.get("conversation") or "",
        }
    )
    return records


def _source_manifest(
    source_root: Path, tasks: dict[str, dict[str, object]]
) -> dict[str, object]:
    """记录组包实际依赖的源文件字节哈希，源变化必然改变 provenance。"""
    files = [
        "dataprocessing/output/data_with_context.csv",
        "data/service_tasks.json",
    ]
    for task_id in tasks_by_selection():
        files.extend(str(path) for path in tasks[task_id].get("image_paths", []))
    entries = [
        {
            "relative_path": relative_path,
            "sha256": sha256_bytes((source_root / relative_path).read_bytes()),
        }
        for relative_path in sorted(set(files))
    ]
    return {"schema_version": "source_manifest.v1", "files": entries}


def _rfm_profiles_bytes(rfm: RfmResult) -> bytes:
    """逐客户 R/F/M 与判定结果，供审计复算，不进入运行 ZIP。"""
    lines = []
    for customer_id in sorted(rfm.profiles):
        profile = rfm.profiles[customer_id]
        payload = {
            "customer_unique_id": customer_id,
            "recency_days": profile.recency_days,
            "frequency_orders": profile.frequency_orders,
            "monetary_total": format(profile.monetary_total, "f"),
            "is_high_value": profile.is_high_value,
            "decision_reason": profile.decision_reason(rfm.thresholds),
        }
        lines.append(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            + b"\n"
        )
    return b"".join(lines)


def _asset_paths_for(
    source_root: Path, image_paths: list[str], case_id: str
) -> list[str]:
    """按任务图片顺序推导资产相对路径（读取文件头 16 字节识别魔数）。"""
    paths: list[str] = []
    for idx, rel in enumerate(image_paths, start=1):
        detected = detect_image((source_root / rel).read_bytes()[:16])
        if detected is None:
            raise ValueError(f"无法识别图片类型：{rel}")
        _media_type, extension = detected
        paths.append(f"assets/{case_id}/{idx:02d}{extension}")
    return paths


def build_dataset(
    source_root: Path,
    out_root: Path | None = None,
    *,
    stage_tmp_root: Path | None = None,
) -> BuildResult:
    """执行完整组包；校验失败抛异常且不写任何输出（可幂等重建）。"""
    root = require_source_root(source_root)
    out = Path(out_root) if out_root is not None else DEFAULT_OUT_ROOT

    rows = load_csv_rows(
        root / "dataprocessing" / "output" / "data_with_context.csv"
    )
    tasks = load_tasks(root / "data" / "service_tasks.json")
    rfm = compute_rfm(rows)

    # 案例批次元数据（task → case_id/case_no/package，顺序即锁定顺序）。
    selected = tasks_by_selection()
    for task_id in selected:
        if task_id not in tasks:
            raise ValueError(f"任务清单引用了不存在的 task_id：{task_id}")

    case_meta: list[dict[str, object]] = []
    orders: dict[str, object] = {}
    mapping_entries: list[dict[str, object]] = []
    for case_no, task_id in enumerate(selected, start=1):
        demo = case_no <= len(DEMO_TASK_IDS)
        seq = case_no if demo else case_no - len(DEMO_TASK_IDS)
        batch_id = "demo_batch_v1" if demo else "acceptance_batch_v1"
        case_id = f"demo_case_{seq:03d}" if demo else f"acceptance_case_{seq:03d}"
        task = tasks[task_id]
        order = match_main_order(rows, str(task.get("conversation") or ""))
        if order is None:
            raise ValueError(f"任务对话在主表中无匹配行：{task_id}")
        orders[task_id] = order
        image_paths = [str(p) for p in (task.get("image_paths") or [])]
        asset_paths = _asset_paths_for(root, image_paths, case_id)
        meta = {
            "task_id": task_id,
            "case_id": case_id,
            "batch_id": batch_id,
            "package_prefix": "DEMO" if demo else "ACCEPT",
            "package_type": "DEMO" if demo else "ACCEPTANCE",
            "case_no": int(seq),
        }
        case_meta.append(meta)
        mapping_entries.append(
            {
                "task_id": task_id,
                "case_id": case_id,
                "package": meta["package_type"],
                "order_id": order.order_id,
                "customer_unique_id": order.customer_unique_id,
                "asset_relative_paths": asset_paths,
            }
        )

    control_rows = [
        row for row in rows if row["customer_unique_id"] == CONTROL_CUSTOMER_ID
    ]
    if not control_rows:
        raise ValueError(f"控制案例客户不存在：{CONTROL_CUSTOMER_ID}")
    control_entry = {
        "case_id": "control_case_001",
        "order_id": control_rows[0]["order_id"],
        "customer_unique_id": CONTROL_CUSTOMER_ID,
    }

    mapping_manifest = {
        "schema_version": MAPPING_SCHEMA_VERSION,
        "data_version": DATA_VERSION,
        "source_snapshot_at": rfm.snapshot_at.isoformat(),
        "builder_version": BUILDER_VERSION,
        "cases": mapping_entries,
        "control": control_entry,
    }
    mapping_bytes = json_bytes(mapping_manifest)
    mapping_manifest_sha256 = sha256_bytes(mapping_bytes)

    source_manifest = _source_manifest(root, tasks)
    source_manifest_bytes = json_bytes(source_manifest)
    source_manifest_sha256 = sha256_bytes(source_manifest_bytes)
    rfm_profiles_bytes = _rfm_profiles_bytes(rfm)

    # 构造 15 个完整案例 + 资产字节。
    cases: list[dict[str, object]] = []
    assets_by_case: dict[str, dict[str, bytes]] = {}
    summaries: list[dict[str, object]] = []
    image_count = 0
    for meta in case_meta:
        task_id = str(meta["task_id"])
        task = tasks[task_id]
        order = orders[task_id]
        profile = rfm.profile_of(order.customer_unique_id)  # type: ignore[union-attr]
        case_id = str(meta["case_id"])
        payload, assets = build_case_input(
            task=task,
            order=order,  # type: ignore[arg-type]
            profile=profile,
            thresholds=rfm.thresholds,
            rfm_snapshot_at=rfm.snapshot_at,
            batch_id=str(meta["batch_id"]),
            case_id=case_id,
            case_no=int(meta["case_no"]),
            package_prefix=str(meta["package_prefix"]),
            source_root=root,
            source_manifest_sha256=source_manifest_sha256,
            mapping_manifest_sha256=mapping_manifest_sha256,
        )
        cases.append(payload)
        assets_by_case[case_id] = assets
        image_count += len(assets)
        image_items = payload["evidence"]["image_items"]  # type: ignore[index]
        summaries.append(
            {
                "case_id": case_id,
                "task_id": task_id,
                "package": meta["package_type"],
                "modality": "text_image" if image_items else "text_only",
                "text_count": len(payload["evidence"]["text_items"]),  # type: ignore[index]
                "image_count": len(image_items),
                "behavior_count": len(
                    payload["evidence"]["behavior_items"]  # type: ignore[index]
                ),
                "image_media_types": [
                    item["media_type"] for item in image_items  # type: ignore[index]
                ],
            }
        )

    control_profile = rfm.profile_of(CONTROL_CUSTOMER_ID)
    control_case = build_control_case(
        rows=control_rows,
        profile=control_profile,
        thresholds=rfm.thresholds,
        rfm_snapshot_at=rfm.snapshot_at,
        source_manifest_sha256=source_manifest_sha256,
        mapping_manifest_sha256=mapping_manifest_sha256,
    )

    # 组两个标准 ZIP。
    def _package_entries(
        batch_id: str, package_cases: list[dict[str, object]]
    ) -> dict[str, bytes]:
        entries: dict[str, bytes] = {}
        case_files: list[str] = []
        evidence_count = 0
        all_assets: dict[str, bytes] = {}
        for payload in package_cases:
            case_id = str(payload["case_id"])
            case_file = f"cases/{case_id}.json"
            case_files.append(case_file)
            entries[case_file] = json_bytes(payload)
            evidence = payload["evidence"]  # type: ignore[index]
            evidence_count += (
                len(evidence["text_items"])
                + len(evidence["image_items"])
                + len(evidence["behavior_items"])
            )
            all_assets.update(assets_by_case[case_id])
        manifest = {
            "schema_version": "batch_manifest.v1",
            "data_version": DATA_VERSION,
            "batch_id": batch_id,
            "package_type": "DEMO" if batch_id == "demo_batch_v1" else "ACCEPTANCE",
            "is_mock": True,
            "source_snapshot_at": rfm.snapshot_at.isoformat(),
            "case_files": sorted(case_files),
            "case_count": len(case_files),
            "evidence_count": evidence_count,
        }
        entries["manifest.json"] = json_bytes(manifest)
        entries.update(all_assets)
        entries["checksums.json"] = json_bytes(make_checksums(entries))
        return entries

    demo_entries = _package_entries(
        "demo_batch_v1",
        [payload for payload in cases if payload["batch_id"] == "demo_batch_v1"],
    )
    acceptance_entries = _package_entries(
        "acceptance_batch_v1",
        [payload for payload in cases if payload["batch_id"] == "acceptance_batch_v1"],
    )
    demo_bytes = write_standard_zip(demo_entries)
    acceptance_bytes = write_standard_zip(acceptance_entries)

    # 自校验：任一失败即抛异常，不写盘（可幂等重建）。
    if not sys.path or str(_REPO_ROOT / "backend") not in sys.path:
        # 以 `python -m tools.data_preparation` 直接运行时 backend/ 不在 sys.path，
        # 复制 app 包路径后导入 M1-03 校验器与数据合同。
        sys.path.insert(0, str(_REPO_ROOT / "backend"))
    from app.contracts.data import CaseInput
    from app.modules.data.importing.zip_stage import ZipImportStage

    stage_tmp = Path(stage_tmp_root) if stage_tmp_root is not None else None
    for label, zip_bytes in (
        ("DEMO", demo_bytes),
        ("ACCEPTANCE", acceptance_bytes),
    ):
        result = ZipImportStage(tmp_root=stage_tmp).stage(zip_bytes)
        if not result.ok:
            raise RuntimeError(
                f"{label} 包自校验失败："
                + "; ".join(r.message for r in result.rejections[:5])
            )

    try:
        CaseInput.model_validate(control_case)
    except Exception as exc:
        raise RuntimeError(f"对照案例不满足 CaseInput 合同：{exc}") from exc

    # 全部通过后一次性写盘。
    out.mkdir(parents=True, exist_ok=True)
    sealed_dir = out / "sealed"
    sealed_dir.mkdir(parents=True, exist_ok=True)
    for meta in case_meta:
        task = tasks[str(meta["task_id"])]
        sealed_payload: dict[str, object] = {
            "case_id": meta["case_id"],
            "task_id": meta["task_id"],
            "source": sealed_fields(task),
        }
        (sealed_dir / f"{meta['case_id']}.json").write_bytes(
            json_bytes(sealed_payload)
        )
    demo_zip_path = out / "demo_batch_v1.zip"
    acceptance_zip_path = out / "acceptance_batch_v1.zip"
    demo_zip_path.write_bytes(demo_bytes)
    acceptance_zip_path.write_bytes(acceptance_bytes)
    (out / "mapping_manifest.json").write_bytes(mapping_bytes)
    (out / "source_manifest.json").write_bytes(source_manifest_bytes)
    (out / "rfm_profiles.jsonl").write_bytes(rfm_profiles_bytes)
    (out / "control_case.json").write_bytes(json_bytes(control_case))

    report: dict[str, object] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "data_version": DATA_VERSION,
        "source_snapshot_at": rfm.snapshot_at.isoformat(),
        "rfm": {
            "rule_version": "high_value_rule_v1",
            "thresholds": {
                "r_p75": rfm.thresholds.r_p75_text,
                "m_p80": rfm.thresholds.m_p80_text,
                "m_p50": rfm.thresholds.m_p50_text,
            },
            "customer_count": rfm.customer_count,
            "high_value_count": rfm.high_value_count,
            "profiles_file": "rfm_profiles.jsonl",
            "profiles_sha256": sha256_bytes(rfm_profiles_bytes),
        },
        "source_manifest_sha256": source_manifest_sha256,
        "source_manifest_file": "source_manifest.json",
        "mapping_manifest_sha256": mapping_manifest_sha256,
        "packages": {
            "demo": {
                "batch_id": "demo_batch_v1",
                "file_name": demo_zip_path.name,
                "sha256": sha256_bytes(demo_bytes),
                "case_count": sum(1 for s in summaries if s["package"] == "DEMO"),
                "image_count": sum(
                    1
                    for s in summaries
                    if s["package"] == "DEMO"
                    for _ in s["image_media_types"]
                ),
            },
            "acceptance": {
                "batch_id": "acceptance_batch_v1",
                "file_name": acceptance_zip_path.name,
                "sha256": sha256_bytes(acceptance_bytes),
                "case_count": sum(
                    1 for s in summaries if s["package"] == "ACCEPTANCE"
                ),
                "image_count": sum(
                    1
                    for s in summaries
                    if s["package"] == "ACCEPTANCE"
                    for _ in s["image_media_types"]
                ),
            },
        },
        "cases": summaries,
        "control_case": {
            "case_id": "control_case_001",
            "customer_unique_id": CONTROL_CUSTOMER_ID,
            "is_high_value": control_profile.is_high_value,
        },
    }
    (out / "report.json").write_bytes(json_bytes(report))

    return BuildResult(
        out_root=out,
        demo_zip_path=demo_zip_path,
        acceptance_zip_path=acceptance_zip_path,
        demo_zip_sha256=sha256_bytes(demo_bytes),
        acceptance_zip_sha256=sha256_bytes(acceptance_bytes),
        demo_bytes=demo_bytes,
        acceptance_bytes=acceptance_bytes,
        rfm=rfm,
        source_manifest_sha256=source_manifest_sha256,
        mapping_manifest_sha256=mapping_manifest_sha256,
        case_count=len(cases),
        image_count=image_count,
        leak_count=0,
        case_summaries=summaries,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tools.data_preparation",
        description="M1-09 确定性数据组包程序（生成双批 ZIP 与密封验收集）",
    )
    parser.add_argument(
        "--source-root",
        default=os.environ.get("PSIT_SOURCE_ROOT"),
        help="逻辑源目录（含 dataprocessing/output/… 与 data/…）；"
        "缺省时读取 PSIT_SOURCE_ROOT 环境变量",
    )
    parser.add_argument(
        "--out-root",
        default=None,
        help="输出目录（默认 runtime_data/mock_dataset_v1/）",
    )
    args = parser.parse_args(argv)
    if not args.source_root:
        parser.error(
            "缺少 --source-root；请传入逻辑源目录或设置 PSIT_SOURCE_ROOT 环境变量"
        )
    result = build_dataset(
        Path(args.source_root),
        Path(args.out_root) if args.out_root else None,
    )
    print(f"DEMO 包：{result.demo_zip_path}（{result.demo_zip_sha256[:16]}…）")
    print(
        f"ACCEPTANCE 包：{result.acceptance_zip_path}（{result.acceptance_zip_sha256[:16]}…）"
    )
    print(
        f"RFM：{result.rfm.customer_count} 客户 / "
        f"{result.rfm.high_value_count} 高价值；案例 {result.case_count} 个、"
        f"图片 {result.image_count} 张"
    )
    return 0


@dataclass(frozen=True)
class BuildResult:
    """M1-09 组包结果：双包路径/字节/哈希与可复算统计。"""

    out_root: Path
    demo_zip_path: Path
    acceptance_zip_path: Path
    demo_zip_sha256: str
    acceptance_zip_sha256: str
    demo_bytes: bytes
    acceptance_bytes: bytes
    rfm: RfmResult
    source_manifest_sha256: str
    mapping_manifest_sha256: str
    case_count: int
    image_count: int
    leak_count: int
    case_summaries: list[dict[str, object]] = field(default_factory=list)


if __name__ == "__main__":
    raise SystemExit(main())
