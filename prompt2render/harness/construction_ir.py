"""Construction DSL -- Manim as a compile target, not something the LLM
writes directly.

Tier 2 Phase 6 (docs/ARCHITECTURE_AUDIT.md SS17: "Manim-as-compiler", named
once with no further elaboration anywhere in the repo -- given concrete
meaning here per explicit user direction).

Phase 4's compiler-backed path already deterministically compiles
*choreography* (self.play/self.wait) from typed motion ops, but still has
the LLM freehand-author *object construction* -- one Python
``_state_<name>(self)`` setup method per state
(``renderer_manim._build_setup_prompt``). This module replaces that one
piece: the LLM emits a small, closed, schema-validated JSON
:class:`ConstructionPlan` instead of Python; :func:`compile_construction`
deterministically renders it to the exact same *kind* of Python
``_build_setup_prompt`` would have produced, which then flows into Phase
4's ``_compile_construct_method``/``_splice_construct_method`` unchanged.

Deliberately narrow first vocabulary (same discipline as Phase 3's 5-op
addition -- evidenced gaps only): ``Text``, ``MathTex``, ``Circle``,
``Square``, ``Rectangle``, ``Dot``, ``Line``, ``Arrow``, ``Triangle``,
``VGroup``, plus :class:`RepeatBlock` for the array/list/sequence pattern
(grounded in a real generated scene shown mid-session: a
``for i in range(4): Square(...)`` loop building an array's memory cells).
``Axes``/``Code``/``Table``/``SurroundingRectangle``/``always_redraw`` are
not yet supported -- a future vocabulary expansion, not silently dropped.

Positioning is structurally constrained rather than merely asked-nicely:
``move_to`` only accepts one of three pre-approved named bands (``TITLE``,
``CAPTION``, ``CENTER`` -- matching ``_build_setup_prompt``'s own hardcoded
conventions), never an arbitrary coordinate. General positioning must go
through ``to_edge``/``next_to``(an already-defined object)/group
``arrange`` -- the schema cannot express the "accumulating floating
annotations at independent absolute coordinates" anti-pattern the freehand
prompt's LAYOUT section currently only discourages in prose.

No escape hatch to raw Python anywhere in this module -- that would defeat
the whole premise. A construction need the vocabulary can't express is a
validation failure, handled by the caller's fallback to Phase 4's freehand
path, not a bypass.

Pure module -- no ``SceneContext``, no file I/O, no ``Plugin``. Unlike
Phase 1/3/5's IRs, this data has no upstream/multi-consumer lifecycle: it is
generated per section, at the exact moment the LLM's setup-code prompt would
have run, and consumed immediately by that same call's own compiler step --
so there is no new ``SceneContext`` field or plugin for it.
"""

from __future__ import annotations

import keyword
from dataclasses import dataclass, field
from typing import Any

#: Construction DSL schema version.
CONSTRUCTION_SCHEMA_VERSION = "1.0"

#: Leaf object kinds this DSL can construct (not "VGroup", which is a
#: structural container handled separately).
OBJECT_REQUIRED_PROPS: dict[str, frozenset[str]] = {
    "Text": frozenset({"content"}),
    "MathTex": frozenset({"content"}),
    "Circle": frozenset(),
    "Square": frozenset(),
    "Triangle": frozenset(),
    "Dot": frozenset(),
    "Rectangle": frozenset({"width", "height"}),
    "Line": frozenset(),
    "Arrow": frozenset(),
}

#: Reference-valued properties (point at another node's id) per kind.
OBJECT_REQUIRED_REFS: dict[str, frozenset[str]] = {
    "Line": frozenset({"start_ref", "end_ref"}),
    "Arrow": frozenset({"start_ref", "end_ref"}),
}

#: Optional literal props per kind, with their expected Python type.
OPTIONAL_PROPS: dict[str, dict[str, type]] = {
    "Text": {"font_size": (int, float), "color": str},
    "MathTex": {"font_size": (int, float), "color": str},
    "Circle": {"radius": (int, float), "color": str},
    "Square": {"side_length": (int, float), "color": str},
    "Triangle": {"color": str},
    "Dot": {"color": str},
    "Rectangle": {"color": str},
    "Line": {"color": str},
    "Arrow": {"color": str},
}

KNOWN_KINDS = frozenset(OBJECT_REQUIRED_PROPS)

#: Closed set of real Manim named-color constants -- rejects hallucinated
#: color names before they ever reach generated source.
KNOWN_COLORS = frozenset({
    "WHITE", "BLACK", "RED", "GREEN", "BLUE", "YELLOW", "PURPLE", "ORANGE",
    "PINK", "GRAY", "GREY", "TEAL", "MAROON", "GOLD",
})

_DIRECTIONS = frozenset({"UP", "DOWN", "LEFT", "RIGHT"})
_BANDS = frozenset({"TITLE", "CAPTION", "CENTER"})


class ConstructionValidationError(ValueError):
    """``validate_and_parse`` rejected one node/repeat block.

    A plain ``ValueError`` (so ``pytest.raises(ValueError, ...)`` keeps
    working) plus the offending ``node_id``, for precise scoping -- same
    pattern as ``animation_ir.AnimationIRValidationError``.
    """

    def __init__(self, message: str, *, node_id: str = "") -> None:
        super().__init__(message)
        self.node_id = node_id


@dataclass
class PositionSpec:
    kind: str              # "to_edge" | "next_to" | "band"
    direction: str = ""    # UP/DOWN/LEFT/RIGHT -- to_edge/next_to
    buff: float = 0.25
    ref: str = ""           # next_to: id of an already-defined node/repeat
    band: str = ""           # band: one of TITLE/CAPTION/CENTER


@dataclass
class ConstructionNode:
    id: str
    kind: str               # OBJECT_REQUIRED_PROPS key, or "VGroup"
    props: dict[str, Any] = field(default_factory=dict)
    refs: dict[str, str] = field(default_factory=dict)
    position: PositionSpec | None = None
    children: list[str] = field(default_factory=list)   # VGroup only
    arrange_direction: str = ""
    arrange_buff: float = 0.15


@dataclass
class RepeatBlock:
    """N structurally-identical instances, auto-grouped under its own
    VGroup id (instances become ``<id>_0`` .. ``<id>_{count-1}``) -- the
    array/list/sequence pattern with no natural single-node representation.
    """

    id: str
    count: int
    kind: str
    props: dict[str, Any] = field(default_factory=dict)
    arrange_direction: str = "RIGHT"
    arrange_buff: float = 0.15
    position: PositionSpec | None = None


@dataclass
class ConstructionPlan:
    schema_version: str
    repeats: list[RepeatBlock] = field(default_factory=list)
    nodes: list[ConstructionNode] = field(default_factory=list)


def _valid_identifier(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.isidentifier()
        and not keyword.iskeyword(value)
    )


def _check_type(value: Any, expected: type | tuple[type, ...]) -> bool:
    # bool is a subclass of int -- explicitly excluded so a stray `true`
    # doesn't silently pass as a numeric prop.
    if isinstance(value, bool):
        return False
    return isinstance(value, expected)


def _parse_position(raw: Any, known_ids: set[str], *, node_id: str) -> PositionSpec | None:
    if raw is None:
        return None

    if not isinstance(raw, dict):
        raise ConstructionValidationError(
            f"{node_id}: position must be an object.", node_id=node_id
        )

    kind = raw.get("kind")

    if kind == "to_edge":
        direction = raw.get("direction")
        if direction not in _DIRECTIONS:
            raise ConstructionValidationError(
                f"{node_id}: to_edge direction must be one of {sorted(_DIRECTIONS)}.",
                node_id=node_id,
            )
        return PositionSpec(
            kind="to_edge", direction=direction, buff=float(raw.get("buff", 0.25))
        )

    if kind == "next_to":
        direction = raw.get("direction")
        ref = raw.get("ref")
        if direction not in _DIRECTIONS:
            raise ConstructionValidationError(
                f"{node_id}: next_to direction must be one of {sorted(_DIRECTIONS)}.",
                node_id=node_id,
            )
        if ref not in known_ids:
            raise ConstructionValidationError(
                f"{node_id}: next_to references undefined id {ref!r}.", node_id=node_id
            )
        return PositionSpec(
            kind="next_to",
            direction=direction,
            ref=ref,
            buff=float(raw.get("buff", 0.25)),
        )

    if kind == "band":
        band = raw.get("band")
        if band not in _BANDS:
            raise ConstructionValidationError(
                f"{node_id}: band must be one of {sorted(_BANDS)}.", node_id=node_id
            )
        return PositionSpec(kind="band", band=band)

    raise ConstructionValidationError(
        f"{node_id}: unknown position kind {kind!r}; must be one of "
        "'to_edge', 'next_to', 'band'.",
        node_id=node_id,
    )


def _parse_props_and_refs(
    raw_props: Any,
    raw_refs: Any,
    kind: str,
    known_ids: set[str],
    *,
    node_id: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    props = raw_props if isinstance(raw_props, dict) else {}
    refs = raw_refs if isinstance(raw_refs, dict) else {}

    required_props = OBJECT_REQUIRED_PROPS.get(kind, frozenset())
    required_refs = OBJECT_REQUIRED_REFS.get(kind, frozenset())
    optional = OPTIONAL_PROPS.get(kind, {})

    missing_props = sorted(required_props - props.keys())
    missing_refs = sorted(required_refs - refs.keys())

    if missing_props or missing_refs:
        missing = missing_props + missing_refs
        raise ConstructionValidationError(
            f"{node_id}: {kind} is missing required key(s) {missing}.", node_id=node_id
        )

    allowed_prop_keys = required_props | set(optional)
    unknown_props = sorted(set(props) - allowed_prop_keys)

    if unknown_props:
        raise ConstructionValidationError(
            f"{node_id}: {kind} has unrecognized prop key(s) {unknown_props}.",
            node_id=node_id,
        )

    unknown_refs = sorted(set(refs) - required_refs)

    if unknown_refs:
        raise ConstructionValidationError(
            f"{node_id}: {kind} has unrecognized ref key(s) {unknown_refs}.",
            node_id=node_id,
        )

    for key, value in props.items():
        if key == "color":
            if value not in KNOWN_COLORS:
                raise ConstructionValidationError(
                    f"{node_id}: unknown color {value!r}; must be one of "
                    f"{sorted(KNOWN_COLORS)}.",
                    node_id=node_id,
                )
            continue

        if key == "content":
            if not isinstance(value, str) or not value.strip():
                raise ConstructionValidationError(
                    f"{node_id}: content must be a non-empty string.", node_id=node_id
                )
            continue

        if key in ("width", "height"):
            if not _check_type(value, (int, float)) or value <= 0:
                raise ConstructionValidationError(
                    f"{node_id}: {key} must be a positive number.", node_id=node_id
                )
            continue

        # Any other key reaching here is optional (required, non-special-
        # cased keys don't exist in the current vocabulary -- content/
        # width/height are the only ones, all handled above).
        expected = optional.get(key)

        if expected is not None and not _check_type(value, expected):
            raise ConstructionValidationError(
                f"{node_id}: {key} must be of type {expected}.", node_id=node_id
            )

    for key, ref_id in refs.items():
        if ref_id not in known_ids:
            raise ConstructionValidationError(
                f"{node_id}: {key} references undefined id {ref_id!r}.", node_id=node_id
            )

    return dict(props), dict(refs)


def _parse_repeat(raw: dict[str, Any], known_ids: set[str]) -> RepeatBlock:
    node_id = raw.get("id")

    if not _valid_identifier(node_id):
        raise ConstructionValidationError(
            f"repeat id {node_id!r} must be a valid Python identifier.",
            node_id=str(node_id),
        )

    if node_id in known_ids:
        raise ConstructionValidationError(
            f"{node_id}: id is already defined.", node_id=node_id
        )

    count = raw.get("count")

    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        raise ConstructionValidationError(
            f"{node_id}: count must be a positive integer.", node_id=node_id
        )

    kind = raw.get("kind")

    if kind not in KNOWN_KINDS:
        raise ConstructionValidationError(
            f"{node_id}: unknown kind {kind!r}; must be one of {sorted(KNOWN_KINDS)}.",
            node_id=node_id,
        )

    props, _refs = _parse_props_and_refs(
        raw.get("props"), {}, kind, known_ids, node_id=node_id
    )

    arrange_direction = raw.get("arrange_direction", "RIGHT") or "RIGHT"

    if arrange_direction not in _DIRECTIONS:
        raise ConstructionValidationError(
            f"{node_id}: arrange_direction must be one of {sorted(_DIRECTIONS)}.",
            node_id=node_id,
        )

    position = _parse_position(raw.get("position"), known_ids, node_id=node_id)

    return RepeatBlock(
        id=node_id,
        count=count,
        kind=kind,
        props=props,
        arrange_direction=arrange_direction,
        arrange_buff=float(raw.get("arrange_buff", 0.15)),
        position=position,
    )


def _parse_node(raw: dict[str, Any], known_ids: set[str]) -> ConstructionNode:
    node_id = raw.get("id")

    if not _valid_identifier(node_id):
        raise ConstructionValidationError(
            f"node id {node_id!r} must be a valid Python identifier.",
            node_id=str(node_id),
        )

    if node_id in known_ids:
        raise ConstructionValidationError(
            f"{node_id}: id is already defined.", node_id=node_id
        )

    kind = raw.get("kind")

    if kind == "VGroup":
        children = raw.get("children")

        if not isinstance(children, list) or not children:
            raise ConstructionValidationError(
                f"{node_id}: VGroup children must be a non-empty list.", node_id=node_id
            )

        unknown = [c for c in children if c not in known_ids]

        if unknown:
            raise ConstructionValidationError(
                f"{node_id}: VGroup references undefined id(s) {unknown}.",
                node_id=node_id,
            )

        arrange_direction = raw.get("arrange_direction", "") or ""

        if arrange_direction and arrange_direction not in _DIRECTIONS:
            raise ConstructionValidationError(
                f"{node_id}: arrange_direction must be one of {sorted(_DIRECTIONS)}.",
                node_id=node_id,
            )

        position = _parse_position(raw.get("position"), known_ids, node_id=node_id)

        return ConstructionNode(
            id=node_id,
            kind="VGroup",
            children=list(children),
            arrange_direction=arrange_direction,
            arrange_buff=float(raw.get("arrange_buff", 0.15)),
            position=position,
        )

    if kind not in KNOWN_KINDS:
        raise ConstructionValidationError(
            f"{node_id}: unknown kind {kind!r}; must be one of "
            f"{sorted(KNOWN_KINDS | {'VGroup'})}.",
            node_id=node_id,
        )

    props, refs = _parse_props_and_refs(
        raw.get("props"), raw.get("refs"), kind, known_ids, node_id=node_id
    )
    position = _parse_position(raw.get("position"), known_ids, node_id=node_id)

    return ConstructionNode(id=node_id, kind=kind, props=props, refs=refs, position=position)


def validate_and_parse(raw: dict[str, Any]) -> ConstructionPlan:
    """Validate and convert the LLM's raw construction-DSL JSON response.

    Repeats are validated (and, in :func:`compile_construction`, always
    compiled) before nodes -- a node may reference an earlier repeat's or
    node's id, never a later one. Raises :class:`ConstructionValidationError`
    with a precise, node-scoped message on any structural problem.
    """

    if not isinstance(raw, dict):
        raise ConstructionValidationError("construction plan must be an object.")

    raw_repeats = raw.get("repeats") or []
    raw_nodes = raw.get("nodes") or []

    if not isinstance(raw_repeats, list):
        raise ConstructionValidationError("repeats must be a list.")

    if not isinstance(raw_nodes, list):
        raise ConstructionValidationError("nodes must be a list.")

    known_ids: set[str] = set()
    repeats: list[RepeatBlock] = []
    nodes: list[ConstructionNode] = []

    for raw_repeat in raw_repeats:
        if not isinstance(raw_repeat, dict):
            raise ConstructionValidationError("repeats entries must be objects.")

        repeat = _parse_repeat(raw_repeat, known_ids)
        known_ids.add(repeat.id)
        repeats.append(repeat)

    for raw_node in raw_nodes:
        if not isinstance(raw_node, dict):
            raise ConstructionValidationError("nodes entries must be objects.")

        node = _parse_node(raw_node, known_ids)
        known_ids.add(node.id)
        nodes.append(node)

    return ConstructionPlan(
        schema_version=CONSTRUCTION_SCHEMA_VERSION, repeats=repeats, nodes=nodes
    )


def _render_position(position: PositionSpec | None) -> str:
    if position is None:
        return ""

    if position.kind == "to_edge":
        return f".to_edge({position.direction}, buff={position.buff})"

    if position.kind == "next_to":
        return f".next_to(self.{position.ref}, {position.direction}, buff={position.buff})"

    # band
    if position.band == "TITLE":
        return ".to_edge(UP, buff=0.35)"
    if position.band == "CAPTION":
        return ".move_to(DOWN * 3.15)"
    return ".move_to(ORIGIN)"  # CENTER


#: Props rendered as a leading positional argument (the real Manim
#: constructor signatures for these classes take it positionally --
#: ``Text(text, ...)``/``MathTex(*tex_strings, ...)`` -- not as a keyword;
#: there is no ``content=`` parameter on either).
_POSITIONAL_PROP = "content"


def _render_kwargs(kind: str, props: dict[str, Any]) -> str:
    """Render literal-valued props as keyword arguments, excluding
    ``content`` (rendered positionally by the caller -- see
    ``_POSITIONAL_PROP``) -- reference-valued props (Line/Arrow's
    start_ref/end_ref) are rendered separately too, never through this
    function."""

    keys = (
        sorted(OBJECT_REQUIRED_PROPS.get(kind, frozenset()) - {_POSITIONAL_PROP})
        + sorted(
            set(props)
            - OBJECT_REQUIRED_PROPS.get(kind, frozenset())
            - {_POSITIONAL_PROP}
        )
    )

    return ", ".join(_render_kwarg(key, props[key]) for key in keys)


def _render_kwarg(key: str, value: Any) -> str:
    if key == "color":
        return f"{key}={value}"  # bare Manim color constant, not a string literal

    if isinstance(value, str):
        return f"{key}={value!r}"

    return f"{key}={value}"


def _render_call_args(kind: str, props: dict[str, Any]) -> str:
    """Full constructor argument list for a leaf object: ``content`` (if
    this kind takes one) rendered positionally first, then keyword args."""

    args: list[str] = []

    if _POSITIONAL_PROP in props:
        args.append(repr(str(props[_POSITIONAL_PROP])))

    kwargs = _render_kwargs(kind, props)

    if kwargs:
        args.append(kwargs)

    return ", ".join(args)


def compile_construction_lines(plan: ConstructionPlan) -> list[tuple[str, str]]:
    """Like :func:`compile_construction`, but returns ``(owning_id, line)``
    pairs instead of one joined string, so a caller that needs to attribute
    each construction to the state that first requires it (e.g. splitting
    across several ``_state_<name>(self)`` methods) can group by id. A
    :class:`RepeatBlock`'s instance lines and its own group line all share
    the block's ``id`` -- referencing anything about it always means the
    whole block.
    """

    lines: list[tuple[str, str]] = []

    for repeat in plan.repeats:
        for i in range(repeat.count):
            args = _render_call_args(repeat.kind, repeat.props)
            lines.append((repeat.id, f"self.{repeat.id}_{i} = {repeat.kind}({args})"))

        members = ", ".join(f"self.{repeat.id}_{i}" for i in range(repeat.count))
        group_line = f"self.{repeat.id} = VGroup({members})"
        group_line += f".arrange({repeat.arrange_direction}, buff={repeat.arrange_buff})"
        group_line += _render_position(repeat.position)
        lines.append((repeat.id, group_line))

    for node in plan.nodes:
        if node.kind == "VGroup":
            members = ", ".join(f"self.{child}" for child in node.children)
            line = f"self.{node.id} = VGroup({members})"
            if node.arrange_direction:
                line += f".arrange({node.arrange_direction}, buff={node.arrange_buff})"
            line += _render_position(node.position)
            lines.append((node.id, line))
            continue

        if node.kind in ("Line", "Arrow"):
            start_ref = node.refs["start_ref"]
            end_ref = node.refs["end_ref"]
            kwargs = _render_kwargs(node.kind, node.props)
            args = f"self.{start_ref}.get_center(), self.{end_ref}.get_center()"
            all_args = f"{args}, {kwargs}" if kwargs else args
            lines.append(
                (
                    node.id,
                    f"self.{node.id} = {node.kind}({all_args})"
                    + _render_position(node.position),
                )
            )
            continue

        args = _render_call_args(node.kind, node.props)
        lines.append(
            (
                node.id,
                f"self.{node.id} = {node.kind}({args})" + _render_position(node.position),
            )
        )

    return lines


def compile_construction(plan: ConstructionPlan) -> str:
    """Deterministically render a validated :class:`ConstructionPlan` into
    Manim Python source -- one ``self.<id> = ...`` statement per repeat
    instance/group and per node, in the same shape a hand-written
    ``_state_<name>(self)`` setup method already takes.
    """

    return "\n".join(line for _id, line in compile_construction_lines(plan))
