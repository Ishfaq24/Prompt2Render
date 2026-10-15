"""Language-independent educational specification and multilingual intermediate representation.

Represents educational concept structures, formulas, prerequisites, scene sequences,
and visual elements independently of surface presentation language.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class VisualElementSpec:
    element_id: str
    element_type: str  # e.g. "flow_stage", "split_stage", "array_grid", "code_card", "formula_card", "node"
    properties: dict[str, Any] = field(default_factory=dict)
    position: dict[str, float] = field(default_factory=dict)  # {"x": 0.0, "y": 0.0}
    immutable_tokens: list[str] = field(default_factory=list)  # equations, code, variable names


@dataclass
class SceneSpec:
    scene_index: int
    stem: str
    learning_objective: str
    narration_text: str
    on_screen_text: str
    visual_elements: list[VisualElementSpec] = field(default_factory=list)
    math_expressions: list[str] = field(default_factory=list)
    code_snippets: list[str] = field(default_factory=list)
    estimated_duration_sec: float = 15.0
    layout_stage: str = "hero_focus"  # "flow", "split", "hero_focus", "benchmark"
    direction: str = "ltr"


@dataclass
class EducationalSpecification:
    topic: str
    learning_objectives: list[str]
    prerequisites: list[str] = field(default_factory=list)
    source_language: str = "en"
    target_language: str = "en"
    target_script: str = "Latn"
    educational_level: str = "undergraduate computer science"
    scenes: list[SceneSpec] = field(default_factory=list)
    mathematical_formulas: list[str] = field(default_factory=list)
    technical_terms: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert specification to JSON-serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EducationalSpecification:
        """Create specification from dictionary."""
        scenes_data = data.get("scenes", [])
        scenes = []
        for s in scenes_data:
            elements_data = s.get("visual_elements", [])
            elements = [
                VisualElementSpec(
                    element_id=el.get("element_id", ""),
                    element_type=el.get("element_type", "node"),
                    properties=el.get("properties", {}),
                    position=el.get("position", {}),
                    immutable_tokens=el.get("immutable_tokens", []),
                )
                for el in elements_data
            ]
            scenes.append(
                SceneSpec(
                    scene_index=int(s.get("scene_index", 1)),
                    stem=s.get("stem", "01"),
                    learning_objective=s.get("learning_objective", ""),
                    narration_text=s.get("narration_text", ""),
                    on_screen_text=s.get("on_screen_text", ""),
                    visual_elements=elements,
                    math_expressions=s.get("math_expressions", []),
                    code_snippets=s.get("code_snippets", []),
                    estimated_duration_sec=float(s.get("estimated_duration_sec", 15.0)),
                    layout_stage=s.get("layout_stage", "hero_focus"),
                    direction=s.get("direction", "ltr"),
                )
            )

        return cls(
            topic=data.get("topic", ""),
            learning_objectives=data.get("learning_objectives", []),
            prerequisites=data.get("prerequisites", []),
            source_language=data.get("source_language", "en"),
            target_language=data.get("target_language", "en"),
            target_script=data.get("target_script", "Latn"),
            educational_level=data.get("educational_level", "undergraduate computer science"),
            scenes=scenes,
            mathematical_formulas=data.get("mathematical_formulas", []),
            technical_terms=data.get("technical_terms", []),
        )

    def to_json(self, indent: int = 2) -> str:
        """Serialize specification to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> EducationalSpecification:
        """Deserialize specification from JSON string."""
        return cls.from_dict(json.loads(json_str))
