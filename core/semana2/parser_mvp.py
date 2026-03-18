from __future__ import annotations

import re
import unicodedata

from .models import BlockIR, ConditionEdge, ParseResult, TaskIR


_CAPTURE_DATA_TYPES = {
    "entero": "1",
    "decimal": "2",
    "lista_unica": "3",
    "lista_multiple": "4",
    "si_no": "6",
    "foto": "12",
    "texto": "11",
}


class RuleBasedTaskParser:
    """
    Parser MVP determinista para arrancar Semana 2.

    Nota:
    - No usa LLM aún.
    - Sirve como baseline para contratos de I/O y validación.
    """

    def parse(self, prompt: str, context: dict | None = None) -> ParseResult:
        normalized = self._normalize(prompt)
        task_name = self._extract_task_name(prompt)

        blocks: list[BlockIR] = []
        edges: list[ConditionEdge] = []
        warnings: list[str] = []
        assumptions: list[str] = []

        if self._mentions_yes_no(normalized):
            root_id = "b1"
            blocks.append(
                BlockIR(
                    block_id=root_id,
                    capture_data_type=_CAPTURE_DATA_TYPES["si_no"],
                    label="Pregunta Sí/No",
                    mandatory=True,
                )
            )

            if self._mentions_yes_photo(normalized):
                yes_id = "b2"
                blocks.append(
                    BlockIR(
                        block_id=yes_id,
                        capture_data_type=_CAPTURE_DATA_TYPES["foto"],
                        label="Foto rama Sí",
                        mandatory=True,
                        allowed_photos=True,
                        mandatory_photos=True,
                    )
                )
                edges.append(
                    ConditionEdge(
                        parent_block_id=root_id,
                        child_block_id=yes_id,
                        condition_type="stage",
                        condition_value="1",
                    )
                )
            else:
                assumptions.append(
                    "No se detectó bloque explícito para rama Sí; se dejó solo la pregunta Sí/No."
                )

            if self._mentions_no_unique_list(normalized):
                no_id = "b3"
                options = self._extract_options(prompt)
                if not options:
                    option_count = self._extract_option_count(normalized) or 3
                    options = [f"Opción {i}" for i in range(1, option_count + 1)]
                    assumptions.append(
                        "No se detectaron textos de opciones; se generaron opciones genéricas."
                    )

                blocks.append(
                    BlockIR(
                        block_id=no_id,
                        capture_data_type=_CAPTURE_DATA_TYPES["lista_unica"],
                        label="Lista única rama No",
                        mandatory=True,
                        options=options,
                    )
                )
                edges.append(
                    ConditionEdge(
                        parent_block_id=root_id,
                        child_block_id=no_id,
                        condition_type="stage",
                        condition_value="0",
                    )
                )
            else:
                assumptions.append(
                    "No se detectó bloque explícito para rama No con lista única."
                )

        elif "texto" in normalized:
            blocks.append(
                BlockIR(
                    block_id="b1",
                    capture_data_type=_CAPTURE_DATA_TYPES["texto"],
                    label="Campo de texto",
                    mandatory=True,
                )
            )
        else:
            warnings.append(
                "No se detectó un patrón estructural conocido (sí/no, texto). Se creó una base mínima."
            )
            blocks.append(
                BlockIR(
                    block_id="b1",
                    capture_data_type=_CAPTURE_DATA_TYPES["texto"],
                    label="Bloque base",
                    mandatory=False,
                )
            )

        ir = TaskIR(task_name=task_name, blocks=blocks, edges=edges, assumptions=assumptions)
        return ParseResult(ir=ir, warnings=warnings)

    @staticmethod
    def _normalize(text: str) -> str:
        value = unicodedata.normalize("NFD", text.lower())
        value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _extract_task_name(prompt: str) -> str:
        pattern = re.compile(r"(?:llamad[ao]\s+|nombre\s+)([\w\s\-]{4,80})", re.IGNORECASE)
        match = pattern.search(prompt)
        if match:
            return match.group(1).strip().strip('"')
        return "Tarea generada desde lenguaje natural"

    @staticmethod
    def _mentions_yes_no(text: str) -> bool:
        return "si/no" in text or "sí/no" in text or "si no" in text

    @staticmethod
    def _mentions_yes_photo(text: str) -> bool:
        return (
            ("rama si" in text or "si responde si" in text or "si responde sí" in text)
            and "foto" in text
        )

    @staticmethod
    def _mentions_no_unique_list(text: str) -> bool:
        no_tokens = ["rama no", "si responde no", "responde no"]
        return any(token in text for token in no_tokens) and (
            "lista unica" in text or "lista única" in text
        )

    @staticmethod
    def _extract_option_count(text: str) -> int | None:
        match = re.search(r"(\d+)\s+opciones", text)
        if not match:
            return None
        value = int(match.group(1))
        if value < 2:
            return 2
        return value

    @staticmethod
    def _extract_options(prompt: str) -> list[str]:
        pattern = re.compile(r"opciones?\s*[:\-]\s*(.+)$", re.IGNORECASE)
        match = pattern.search(prompt)
        if not match:
            return []

        raw = match.group(1).strip()
        parts = [part.strip() for part in re.split(r",|;|\|", raw) if part.strip()]
        return parts[:20]
