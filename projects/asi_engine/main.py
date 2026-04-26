"""
ASI Engine — reasoning and inference module.
"""
from __future__ import annotations


class ASIEngine:
    def __init__(self, model_id: str = "loom-v1") -> None:
        self.model_id = model_id
        self._context: list[str] = []

    def observe(self, input_text: str) -> None:
        self._context.append(input_text)

    def reason(self) -> str:
        if not self._context:
            return ""
        return f"[{self.model_id}] Processed {len(self._context)} observation(s)."

    def reset(self) -> None:
        self._context.clear()


if __name__ == "__main__":
    engine = ASIEngine()
    engine.observe("Input signal A")
    engine.observe("Input signal B")
    print(engine.reason())
