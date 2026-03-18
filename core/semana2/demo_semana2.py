from __future__ import annotations

import argparse
import json
import os

from .autofix_stub import NoOpAutoCorrector
from .evidence import EvidenceStore
from .executor_h3 import PlaybookExecutor
from .orchestrator import Semana2Orchestrator
from .parser_mvp import RuleBasedTaskParser
from .validator import TaskIRValidator


def run_demo(prompt: str, output_dir: str | None = None) -> dict:
    orchestrator = Semana2Orchestrator(
        parser=RuleBasedTaskParser(),
        validator=TaskIRValidator(),
        executor=PlaybookExecutor(),
        auto_corrector=NoOpAutoCorrector(),
        max_retries=1,
    )

    result = orchestrator.run(prompt=prompt)
    payload = result.to_dict()

    if output_dir and result.execution_result is not None:
        store = EvidenceStore(output_dir)
        jsonl_path, summary_path = store.write_execution(
            case_id="demo_semana2",
            execution_result=result.execution_result,
        )
        payload["artifacts"] = {
            "jsonl": os.path.abspath(jsonl_path),
            "summary": os.path.abspath(summary_path),
        }

    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Semana 2 MVP - Demo parser+validator+orquestador (dry-run)."
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        default="crear una tarea con pregunta sí/no, rama sí con foto obligatoria y rama no con lista única con 3 opciones",
        help="Descripción en lenguaje natural de la tarea.",
    )
    parser.add_argument(
        "--output-dir",
        default="docs/runs",
        help="Carpeta para guardar evidencia JSONL/summary.",
    )

    args = parser.parse_args()
    payload = run_demo(args.prompt, output_dir=args.output_dir)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
