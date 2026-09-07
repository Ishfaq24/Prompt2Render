"""Unit tests for Universal Spatial Layout Stages and Cross-Domain Widgets."""

from prompt2render.assets.mobjects.stages import (
    FlowStage,
    SplitStage,
    HeroFocusStage,
    BenchmarkStage,
)
from prompt2render.assets.mobjects.network_widgets import (
    ServerNode,
    ClientCluster,
    DatabaseNode,
    ConfigCodeCard,
    MetricBadge,
)
from prompt2render.assets.mobjects.algo_math_widgets import (
    ArrayGrid,
    FormulaCard,
    KeyBadge,
)


def test_flow_stage_creation():
    n1 = ServerNode(name="DNS Resolver")
    n2 = ServerNode(name="Root Server")
    n3 = ServerNode(name="TLD Server")
    stage = FlowStage(nodes=[n1, n2, n3])
    assert stage is not None
    assert len(stage.nodes) == 3
    assert len(stage.conduits) == 2
    pulse = stage.pulse_signal(0, 1)
    assert pulse is not None


def test_split_stage_creation():
    left = ConfigCodeCard(code_lines=["Host github.com", "  IdentityFile ~/.ssh/id_ed25519"], title="ssh_config")
    right = KeyBadge(key_type="PUBLIC KEY", name="id_ed25519.pub")
    stage = SplitStage(left=left, right=right, left_title="Client Config", right_title="Key Identity")
    assert stage is not None
    assert len(stage.elements) >= 3


def test_hero_focus_stage_creation():
    array = ArrayGrid(values=[2, 5, 8, 12, 16, 23, 38], active_index=3)
    b1 = MetricBadge(label="Target", value="12", status="info")
    b2 = MetricBadge(label="Steps", value="1", status="good")
    stage = HeroFocusStage(hero=array, badges=[b1, b2], title="Binary Search: Midpoint Evaluation")
    assert stage is not None
    assert stage.hero is not None


def test_benchmark_stage_creation():
    b1 = MetricBadge(label="Apache (C10K)", value="Crash", status="bad")
    b2 = MetricBadge(label="NGINX (C10K)", value="10,000 req/s", status="good")
    stage = BenchmarkStage(cards=[b1, b2], title="Concurrency Benchmark")
    assert stage is not None
    assert len(stage.cards) == 2


def test_formula_card_creation():
    steps = [
        "252 = 105 * 2 + 42",
        "105 = 42 * 2 + 21",
        "42 = 21 * 2 + 0",
    ]
    card = FormulaCard(steps=steps, title="Euclidean Algorithm: GCD(252, 105)", highlight_step=1)
    assert card is not None
    assert len(card.step_group.submobjects) == 3
