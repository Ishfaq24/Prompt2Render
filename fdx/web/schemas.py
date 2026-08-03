"""Request models for the pipeline API, and the CLI-argument builders that
turn a validated model into the exact flags `fdx.py`'s own argparse setup
already defines for that stage. Kept as an explicit allowlist per stage
rather than a generic passthrough -- every flag here is a literal 1:1 match
with an existing `add_argument()` in `fdx.py`.
"""
from __future__ import annotations

from pydantic import BaseModel


class VoiceOpts(BaseModel):
    backend: str | None = None        # kokoro | edge | own
    voice: str | None = None
    speed: float | None = None
    lufs: float | None = None
    audio_profile: str | None = None  # tts | voice
    pause_sentence: int | None = None
    pause_paragraph: int | None = None
    only: str | None = None
    force: bool = False


class AlignOpts(BaseModel):
    only: str | None = None
    force: bool = False
    no_asr: bool = False


class ScenesOpts(BaseModel):
    section: int | None = None
    retries: int = 3


class StillsOpts(BaseModel):
    section: int | None = None
    check: bool = False


class PlanOpts(BaseModel):
    motion: str | None = None         # none | dissolve | dissolve+reveal
    lead_ms: int | None = None


class EncodeOpts(BaseModel):
    limit: int = 10
    all: bool = False
    preview: bool = False
    jobs: int | None = None


class FinishOpts(BaseModel):
    burn: bool = False
    style: str = "srt"                # srt | ass


class CheckOpts(BaseModel):
    strict: bool = False


class BuildOpts(BaseModel):
    motion: str | None = None
    speed: float | None = None
    voice: str | None = None
    lufs: float | None = None
    burn: bool = False
    strict: bool = False
    jobs: int | None = None


MODELS: dict[str, type[BaseModel]] = {
    "voice": VoiceOpts, "align": AlignOpts, "scenes": ScenesOpts,
    "stills": StillsOpts, "plan": PlanOpts, "encode": EncodeOpts,
    "finish": FinishOpts, "check": CheckOpts,
}


def voice_args(o: VoiceOpts) -> list[str]:
    args = []
    if o.backend: args += ["--backend", o.backend]
    if o.voice: args += ["--voice", o.voice]
    if o.speed is not None: args += ["--speed", str(o.speed)]
    if o.lufs is not None: args += ["--lufs", str(o.lufs)]
    if o.audio_profile: args += ["--audio-profile", o.audio_profile]
    if o.pause_sentence is not None: args += ["--pause-sentence", str(o.pause_sentence)]
    if o.pause_paragraph is not None: args += ["--pause-paragraph", str(o.pause_paragraph)]
    if o.only: args += ["--only", o.only]
    if o.force: args.append("--force")
    return args


def align_args(o: AlignOpts) -> list[str]:
    args = []
    if o.only: args += ["--only", o.only]
    if o.force: args.append("--force")
    if o.no_asr: args.append("--no-asr")
    return args


def scenes_args(o: ScenesOpts) -> list[str]:
    args = []
    if o.section is not None: args += ["--section", str(o.section)]
    args += ["--retries", str(o.retries)]
    return args


def stills_args(o: StillsOpts) -> list[str]:
    args = []
    if o.section is not None: args += ["--section", str(o.section)]
    if o.check: args.append("--check")
    return args


def plan_args(o: PlanOpts) -> list[str]:
    args = []
    if o.motion: args += ["--motion", o.motion]
    if o.lead_ms is not None: args += ["--lead-ms", str(o.lead_ms)]
    return args


def encode_args(o: EncodeOpts) -> list[str]:
    args = ["--limit", str(o.limit)]
    if o.all: args.append("--all")
    if o.preview: args.append("--preview")
    if o.jobs is not None: args += ["--jobs", str(o.jobs)]
    return args


def finish_args(o: FinishOpts) -> list[str]:
    args = ["--style", o.style]
    if o.burn: args.append("--burn")
    return args


def check_args(o: CheckOpts) -> list[str]:
    return ["--strict"] if o.strict else []


def build_args(o: BuildOpts) -> list[str]:
    args = []
    if o.motion: args += ["--motion", o.motion]
    if o.speed is not None: args += ["--speed", str(o.speed)]
    if o.voice: args += ["--voice", o.voice]
    if o.lufs is not None: args += ["--lufs", str(o.lufs)]
    if o.burn: args.append("--burn")
    if o.strict: args.append("--strict")
    if o.jobs is not None: args += ["--jobs", str(o.jobs)]
    return args


ARG_BUILDERS = {
    "voice": voice_args, "align": align_args, "scenes": scenes_args,
    "stills": stills_args, "plan": plan_args, "encode": encode_args,
    "finish": finish_args, "check": check_args,
}
