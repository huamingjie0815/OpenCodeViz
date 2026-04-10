from codeviz.server import choose_port


def test_default_port_avoids_common_ports() -> None:
    port = choose_port()
    assert port not in {3000, 5173, 8000, 8080}
    assert port >= 39127

