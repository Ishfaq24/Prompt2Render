# Verification and evidence

## Verifier inventory

Scene-scoped (re-run after every repair):

| Plugin | Evidence | Dimension |
|---|---|---|
| `verifier_execution` | deterministic preflight: syntax, imports, backend mix, known-bad kwargs (checked against the **installed** Manim via `inspect`), undefined identifiers, malformed LaTeX | syntax / execution |
| `verifier_semantic` | LLM critic over preview + narration | semantic |
| `verifier_layout` | LLM/geometry critique over preview + zones | layout |
| `verifier_spatial` | `scenekit.audit` geometry on rendered frames | layout |
| `verifier_motion` | rendered pixel motion vs storyboard motion ops | visual |
| `verifier_temporal` | duration vs narration span | temporal |
| `verifier_lifecycle` | object-identity shell (soft) | temporal |
| `verifier_storyboard` | cue ranges, state/motion conformance | semantic |
| `observer_visual` | per-frame ink/motion observation (feeds artifacts) | visual |

Whole-video (not scene-repairable): `verifier_audio` (caption drift),
`verifier_pedagogy`.

A verifier that crashes, times out, or lacks its required artifact emits
`verification_unavailable` — never a silent pass
(`finding.verification_unavailable`).

## Finding taxonomy

`harness/finding.py`: `finding_id`, `scene_id`, `category`,
`severity` (BLOCKING/WARNING/INFO → fail/warn/pass), `message`,
`finding_type` (the routing key). Verifier-specific evidence
(`location`, `bbox`, `safe_area`, `fix`, `difference`, subtypes) rides on
the same dict — normalized, not flattened.

## Evidence bundle (`evidence.json`)

`harness/evidence.build_evidence_bundle`, written per revision by the
repair controller:

```json
{
  "schema_version": "1.0",
  "scene_id": "06", "revision": 2, "status": "fail",
  "checks": {"syntax": "...", "execution": "...", "layout": "...",
              "visual": "...", "semantic": "...", "pedagogy": "...",
              "temporal": "..."},
  "findings": [ ...full verifier evidence incl. repair_type... ],
  "blocking_count": 1, "warning_count": 0,
  "passing_properties": ["layout", "semantic", "temporal"],
  "locked_properties": {"layout": true, "semantic": true, ...},
  "must_preserve": ["object positions", "caption position", "font sizes", ...],
  "recommended_actions": [...],
  "quality": { ...SceneQuality.to_dict()... }
}
```

## Deterministic Manim preflight (before any render)

`scenes.validate_manim_source` runs in `verifier_execution` and inside the
generator's own retry loop:

- syntax errors, forbidden imports, SceneKit/Manim backend mixing;
- undefined identifiers against the **installed** Manim namespace
  (catches `CAPPTION_Y` before a render is ever attempted);
- invalid keyword arguments checked against the installed Manim's real
  signatures via `inspect` (catches `align_to(..., buff=...)`, while
  `next_to(..., buff=...)` correctly passes);
- **hallucinated methods on MathTex receivers**, checked against the
  installed `MathTex` class — `vec.get_parts_by_tex("0")` on a `MathTex`
  crashes mid-render with the cryptic
  `Mobject.__getattr__ ... getter() takes 1 positional argument` (because a
  missing attribute becomes a property getter, not an `AttributeError`);
  caught statically with an actionable fix (`get_part_by_tex(...)` / build
  the pieces in a `VGroup`);
- **Text-only kwargs on `MathTex`/`Tex`** (`weight=`, `slant=`, `font=`,
  `t2c=` …) — these render through LaTeX, not Pango, so
  `MathTex(..., weight=BOLD)` crashes in `Mobject.__init__`; the message
  tells the model to use color/size instead;
- malformed LaTeX (`&`, `%`, `#` outside tabular/align);
- structural rules: exactly one `Scene` subclass, `construct()`,
  `self.play()`, `self.wait()` present.

Typed `finding_type`s: `undefined_identifier`, `undefined_method`,
`invalid_manim_api`, `execution_failure` — each routed and repaired
distinctly. Because `renderer_manim` sends every freshly written scene
through `check_scene_artifact` before rendering (and retries locally with
the diagnostic as feedback), these crash classes are converted into
actionable repair instructions instead of a wasted Manim subprocess. The
generator prompt states the exact target version (`manimver.target_version()`,
env-overridable via `P2R_MANIM_VERSION`).

## Layout guardrails

`harness/layout_zones.py` is the single source of zone geometry for both
backends. The Manim generation prompt includes the authoritative contract
(safe area, title/content/caption zones, band gutter, caption line and
font-size limits) rendered from the same constants the verifiers measure
against — the two cannot drift apart.

## Reports

- `build/reports/scenes/<stem>.json` — latest canonical scene report.
- `build/revisions/<stem>/revision_NN/{report,evidence,repair,generation,visual_state}.json`
  — the complete per-revision record.
- `build/revisions/<stem>/accepted/` — pointer + small artifacts of the
  accepted revision.
- `build/harness/{events.jsonl,repair_log.jsonl,metrics.json,
  experiment_summary.json}` — run-level telemetry.
