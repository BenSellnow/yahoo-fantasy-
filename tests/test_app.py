"""Front-end tests: run the real Streamlit app headlessly and click through it."""
import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = "../streamlit_app.py"
TABS = ["Pickups", "Lineup", "Matchup", "Playoff odds", "Free agents"]


def run_app(secrets=None):
    at = AppTest.from_file(APP, default_timeout=120)
    for k, v in (secrets or {}).items():
        at.secrets[k] = v
    return at.run()


def texts(at):
    els = list(at.markdown) + list(at.caption) + list(at.subheader) + list(at.title) + \
        list(at.info) + list(at.success) + list(at.warning) + list(at.error)
    return "\n".join(str(e.value) for e in els)


def test_opens_on_basketball_demo_without_setup():
    at = run_app()
    assert not at.exception
    assert at.sidebar.radio[0].value == "Demo: NBA categories league"
    assert at.title[0].value == "Demo Categories League"
    labels = [m.label for m in at.metric]
    for label in ("Week", "Win chance this week", "Playoff odds", "Top pickup"):
        assert label in labels
    assert [t.label for t in at.tabs] == TABS


def test_basketball_tabs_render_content():
    at = run_app()
    body = texts(at)
    assert "Do this" in body                      # pickup plan
    assert "Today's lineup" in body               # daily lineup
    assert "Expected category score" in [m.label for m in at.metric]
    # pickups, lineup, category table, playoff table, free agents
    assert len(at.dataframe) >= 5
    pickups = at.dataframe[0].value
    assert {"Add", "Drop", "Gain", "Games left"} <= set(pickups.columns)
    assert (pickups["Gain"] > 0).all()
    assert (pickups["Games left"] >= 0).all()


def test_switch_to_football_demo():
    at = run_app()
    at.sidebar.radio[0].set_value("Demo: NFL points league").run()
    assert not at.exception
    assert at.title[0].value == "Demo Points League"
    assert "Your projected score" in [m.label for m in at.metric]
    assert "Games left" not in at.dataframe[0].value.columns


def test_settings_change_reruns_cleanly():
    at = run_app()
    at.sidebar.slider[1].set_value(0.9).run()  # focus pickups on this week
    assert not at.exception
    assert "90% this week" in texts(at)


def test_yahoo_without_config_explains_setup():
    at = run_app()
    at.sidebar.radio[0].set_value("My Yahoo league").run()
    assert not at.exception
    assert "Yahoo isn't configured yet" in texts(at)


SECRETS = {"app_password": "hunter2",
           "yahoo": {"client_id": "cid", "client_secret": "sec",
                     "redirect_uri": "https://example.streamlit.app"}}


def test_password_gate_blocks_until_correct():
    at = run_app(SECRETS)
    assert not at.exception
    assert len(at.tabs) == 0 and len(at.text_input) == 1
    at.text_input[0].input("wrong").run()
    assert "Wrong password." in texts(at)
    at.text_input[0].input("hunter2").run()
    assert not at.exception
    # Yahoo is configured, so it defaults to the Yahoo league and offers login.
    assert at.sidebar.radio[0].value == "My Yahoo league"
    assert "Connect your Yahoo account" in texts(at)
