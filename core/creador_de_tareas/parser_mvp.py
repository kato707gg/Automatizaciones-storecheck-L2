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
            root_label = self._extract_question_label(prompt) or "Pregunta Sí/No"
            handled_any_response_photo = False
            blocks.append(
                BlockIR(
                    block_id=root_id,
                    capture_data_type=_CAPTURE_DATA_TYPES["si_no"],
                    label=root_label,
                    mandatory=True,
                )
            )

            if self._mentions_any_response_photo(normalized):
                yes_id = "b2"
                no_id = "b3"
                blocks.append(
                    BlockIR(
                        block_id=yes_id,
                        capture_data_type=_CAPTURE_DATA_TYPES["foto"],
                        label="Foto respuesta Sí",
                        mandatory=True,
                        allowed_photos=True,
                        mandatory_photos=True,
                    )
                )
                blocks.append(
                    BlockIR(
                        block_id=no_id,
                        capture_data_type=_CAPTURE_DATA_TYPES["foto"],
                        label="Foto respuesta No",
                        mandatory=True,
                        allowed_photos=True,
                        mandatory_photos=True,
                    )
                )
                edges.append(
                    ConditionEdge(
                        parent_block_id=root_id,
                        child_block_id=yes_id,
                        condition_type="answer",
                        condition_value="1",
                    )
                )
                edges.append(
                    ConditionEdge(
                        parent_block_id=root_id,
                        child_block_id=no_id,
                        condition_type="answer",
                        condition_value="0",
                    )
                )
                assumptions.append(
                    "Se detectó instrucción de foto para cualquier respuesta; se generaron ramas Sí/No con condición de tipo answer."
                )
                handled_any_response_photo = True
            elif self._mentions_yes_photo(normalized):
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
            elif self._mentions_yes_text(normalized):
                yes_id = "b2"
                blocks.append(
                    BlockIR(
                        block_id=yes_id,
                        capture_data_type=_CAPTURE_DATA_TYPES["texto"],
                        label="Texto rama Sí",
                        mandatory=True,
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

            if handled_any_response_photo:
                pass
            elif self._mentions_no_unique_list(normalized):
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
            elif self._mentions_no_text(normalized):
                no_id = "b3"
                blocks.append(
                    BlockIR(
                        block_id=no_id,
                        capture_data_type=_CAPTURE_DATA_TYPES["texto"],
                        label="Texto rama No",
                        mandatory=True,
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
        any_response_tokens = [
            "cual sea la respuesta",
            "cualquiera sea la respuesta",
            "sea cual sea la respuesta",
            "independientemente de la respuesta",
            "sin importar la respuesta",
        ]
        if any(token in text for token in any_response_tokens):
            return True

        if "si/no" in text or "sí/no" in text or "si no" in text:
            return True

        yes_tokens = ["si responde si", "si responde que si", "rama si", "si responde sí", "si responde que sí"]
        no_tokens = ["si responde no", "si responde que no", "rama no", "responde no"]
        return any(token in text for token in yes_tokens) and any(token in text for token in no_tokens)

    @staticmethod
    def _mentions_any_response_photo(text: str) -> bool:
        any_response_tokens = [
            "cual sea la respuesta",
            "cualquiera sea la respuesta",
            "sea cual sea la respuesta",
            "independientemente de la respuesta",
            "sin importar la respuesta",
        ]
        return any(token in text for token in any_response_tokens) and "foto" in text

    @staticmethod
    def _mentions_yes_photo(text: str) -> bool:
        return (
            (
                "rama si" in text
                or "si responde si" in text
                or "si responde sí" in text
                or "si responde que si" in text
                or "si responde que sí" in text
            )
            and "foto" in text
        )

    @staticmethod
    def _mentions_yes_text(text: str) -> bool:
        yes_tokens = ["rama si", "si responde si", "si responde sí", "si responde que si", "si responde que sí"]
        text_tokens = ["texto", "explicar", "motivo", "comentario", "describir"]
        return any(token in text for token in yes_tokens) and any(token in text for token in text_tokens)

    @staticmethod
    def _mentions_no_unique_list(text: str) -> bool:
        no_tokens = ["rama no", "si responde no", "responde no"]
        return any(token in text for token in no_tokens) and (
            "lista unica" in text or "lista única" in text
        )

    @staticmethod
    def _mentions_no_text(text: str) -> bool:
        no_tokens = ["rama no", "si responde no", "si responde que no", "responde no"]
        text_tokens = ["texto", "explicar", "motivo", "comentario", "describir"]
        return any(token in text for token in no_tokens) and any(token in text for token in text_tokens)

    @staticmethod
    def _extract_question_label(prompt: str) -> str | None:
        quoted = re.search(r'["“”](.+?)["“”]', prompt)
        if quoted:
            value = quoted.group(1).strip()
            if value:
                return value[:120]

        question_like = re.search(r"pregunte\s+(.+?)(?:si responde|$)", prompt, re.IGNORECASE)
        if question_like:
            value = question_like.group(1).strip(" :.-\n\t")
            if value:
                return value[:120]

        return None

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
