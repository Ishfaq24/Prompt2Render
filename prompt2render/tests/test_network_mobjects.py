"""Unit tests for cinematic network and architecture Mobjects."""

from prompt2render.assets.mobjects.network_widgets import (
    ServerNode,
    ClientCluster,
    DatabaseNode,
    ConfigCodeCard,
    MetricBadge,
)


def test_server_node_creation():
    node = ServerNode(name="NGINX", subtext="Event-Driven", status="active")
    assert node is not None
    assert hasattr(node, "card")
    assert hasattr(node, "status_dot")
    node.set_status("warning")
    node.set_status("error")


def test_client_cluster_creation():
    cluster = ClientCluster(count=4, label="Clients")
    assert cluster is not None
    assert len(cluster.nodes) == 4


def test_database_node_creation():
    db = DatabaseNode(name="storage_db")
    assert db is not None
    assert hasattr(db, "body")


def test_config_code_card_creation():
    lines = ["upstream backend {", "  server app1:8080;", "}"]
    card = ConfigCodeCard(code_lines=lines, title="nginx.conf")
    assert card is not None
    assert hasattr(card, "frame")
    assert hasattr(card, "code_group")


def test_metric_badge_creation():
    badge = MetricBadge(label="Req/s", value="15,000", status="good")
    assert badge is not None
    assert hasattr(badge, "pill")
