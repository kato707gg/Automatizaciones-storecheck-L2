from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime
from typing import Any

from .contracts import ExecutionResult, ExecutionStepEvidence


class EvidenceStore:
    def __init__(self, base_dir: str) -> None:
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def _now_slug(self) -> str:
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def write_execution(self, case_id: str, execution_result: ExecutionResult) -> tuple[str, str]:
        slug = self._now_slug()
        jsonl_path = os.path.join(self.base_dir, f"{slug}_{case_id}.jsonl")
        summary_path = os.path.join(self.base_dir, f"{slug}_{case_id}.summary.json")

        with open(jsonl_path, "w", encoding="utf-8") as fp:
            for step in execution_result.steps:
                payload = {
                    "timestamp": datetime.now().isoformat(),
                    "step": self._serialize_step(step),
                }
                fp.write(json.dumps(payload, ensure_ascii=False) + "\n")

        summary = {
            "executed": execution_result.executed,
            "success": execution_result.success,
            "steps_count": len(execution_result.steps),
            "network_steps_with_reqid": len([s for s in execution_result.steps if s.reqid is not None]),
            "final_snapshot": execution_result.final_snapshot,
        }

        with open(summary_path, "w", encoding="utf-8") as fp:
            json.dump(summary, fp, ensure_ascii=False, indent=2)

        return jsonl_path, summary_path

    @staticmethod
    def _serialize_step(step: ExecutionStepEvidence) -> dict[str, Any]:
        return asdict(step)
