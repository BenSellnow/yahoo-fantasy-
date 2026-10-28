import json
from urllib.parse import parse_qs, urlparse

from yahoo_oauth import OAuth2
from yahoo_oauth.oauth import BaseOAuth

from fantasy_optimizer import webauth


def test_authorize_url():
    q = parse_qs(urlparse(webauth.authorize_url("cid", "https://x.streamlit.app")).query)
    assert q == {"client_id": ["cid"], "redirect_uri": ["https://x.streamlit.app"],
                 "response_type": ["code"]}


def test_oauth_file_refreshes_without_terminal_prompt(tmp_path, monkeypatch):
    path = webauth.write_oauth_file("cid", "secret", "refresh-123",
                                    "https://x.streamlit.app", path=str(tmp_path / "o.json"))

    def no_prompt(self):
        raise AssertionError("must not fall back to the interactive login")

    def fake_refresh(self):
        assert self.refresh_token == "refresh-123"
        assert self.callback_uri == "https://x.streamlit.app"
        self.access_token = "fresh"
        return {"access_token": "fresh", "token_type": "bearer",
                "refresh_token": "refresh-123", "token_time": 1e12}

    monkeypatch.setattr(BaseOAuth, "handler", no_prompt)
    monkeypatch.setattr(BaseOAuth, "refresh_access_token", fake_refresh)
    sc = OAuth2(None, None, from_file=path)
    assert sc.access_token == "fresh"
    assert json.load(open(path))["access_token"] == "fresh"


def test_each_session_gets_its_own_token_file():
    a = webauth.write_oauth_file("cid", "sec", "token-A")
    b = webauth.write_oauth_file("cid", "sec", "token-B")
    try:
        assert a != b
        assert json.load(open(a))["refresh_token"] == "token-A"
        assert json.load(open(b))["refresh_token"] == "token-B"
        import os, stat
        assert stat.S_IMODE(os.stat(a).st_mode) == 0o600
    finally:
        webauth.forget(a)
        webauth.forget(b)
    import os
    assert not os.path.exists(a)


def test_yahoo_cache_is_separate_per_account(tmp_path, monkeypatch):
    from yahoo_oauth.oauth import BaseOAuth
    from fantasy_optimizer.yahoo_source import YahooSource

    def fake_refresh(self):
        return {"access_token": "x", "token_type": "bearer",
                "refresh_token": self.refresh_token, "token_time": 1e12}
    monkeypatch.setattr(BaseOAuth, "refresh_access_token", fake_refresh)
    dirs = []
    for token in ("token-A", "token-B"):
        path = webauth.write_oauth_file("cid", "sec", token, path=str(tmp_path / f"{token}.json"))
        dirs.append(YahooSource(path, None, cache_dir=str(tmp_path / "cache")).cache.dir)
    assert dirs[0] != dirs[1]
