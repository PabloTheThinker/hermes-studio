"""Path confinement, the media-URL guard and the plugin's environment (catalog review 2)."""

from __future__ import annotations

import importlib.util
import json
import os
import socket
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def fake_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".hermes").mkdir(parents=True)
    (home / ".hermes" / ".env").write_text("SECRET=1")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    for k in ("HERMES_STUDIO_MEDIA_ROOTS", "HERMES_STUDIO_OUT_ROOTS"):
        monkeypatch.delenv(k, raising=False)
    return home


# --------------------------------------------------------------------------- addresses


BAD_IPS = ["127.0.0.1", "127.9.9.9", "10.0.0.1", "172.16.0.1", "192.168.1.1", "169.254.169.254",
           "100.64.0.1", "100.127.255.254", "0.0.0.0", "224.0.0.1", "240.0.0.1", "255.255.255.255",
           "198.18.0.1", "::1", "::", "fe80::1", "fc00::1", "fd12:3456::1", "ff02::1",
           "::ffff:127.0.0.1", "::ffff:169.254.169.254", "::ffff:10.0.0.1", "2002:7f00:1::1",
           "64:ff9b::a9fe:a9fe", "2001:db8::1"]
GOOD_IPS = ["8.8.8.8", "1.1.1.1", "2606:4700:4700::1111"]


@pytest.mark.parametrize("ip", BAD_IPS)
def test_non_public_addresses_are_refused(ip):
    from hermes_studio.guard import ip_allowed

    assert not ip_allowed(ip)


@pytest.mark.parametrize("ip", GOOD_IPS)
def test_public_addresses_are_allowed(ip):
    from hermes_studio.guard import ip_allowed

    assert ip_allowed(ip)


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://example.com/a.mp4", "gopher://x/", "http://localhost/a.mp4",
    "http://127.0.0.1:8080/", "http://169.254.169.254/latest/meta-data/", "http://[::1]/",
    "http://[::ffff:127.0.0.1]/", "http://0x7f000001/", "http://2130706433/", "http://10.1.2.3/x.mp4",
    "http://100.64.0.1/", "https:///nohost",
])
def test_check_url_refuses(url):
    from hermes_studio.guard import URLRefused, check_url

    with pytest.raises(URLRefused):
        check_url(url)


def test_engine_entry_points_refuse_private_links(tmp_path, monkeypatch):
    from hermes_studio import api, download

    monkeypatch.setattr(download, "_ytdlp_guarded", lambda: pytest.fail("yt-dlp must not start"))
    for fn in (download.probe, lambda u: download.fetch(u, tmp_path / "w")):
        with pytest.raises(ValueError):
            fn("http://169.254.169.254/latest/meta-data/")
    with pytest.raises(api.HermesStudioError) as exc:
        api.check_source("http://127.0.0.1:3870/x.mp4")
    assert exc.value.code == "bad_input"


# --------------------------------------------------------------------------- redirect hops


class _Redirect(BaseHTTPRequestHandler):
    target = ""

    def do_GET(self):  # noqa: N802
        self.send_response(302)
        self.send_header("Location", self.target)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *a):
        pass


class _Ok(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = b"secret-metadata"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture()
def hop(monkeypatch):
    """A 'public' server on 127.0.0.1 that redirects to a 'private' one on 127.0.0.2.
    The guard is told only 127.0.0.1 is public, so the second hop must be refused."""
    from hermes_studio import guard

    try:
        priv = ThreadingHTTPServer(("127.0.0.2", 0), _Ok)
    except OSError:
        pytest.skip("127.0.0.2 not bindable here")
    handler = type("R", (_Redirect,), {"target": f"http://127.0.0.2:{priv.server_address[1]}/latest/meta-data/"})
    pub = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    for s in (pub, priv):
        threading.Thread(target=s.serve_forever, daemon=True).start()
    monkeypatch.setattr(guard, "ip_allowed", lambda ip: ip == "127.0.0.1")
    monkeypatch.setattr(socket, "getaddrinfo", guard._guarded_getaddrinfo)
    yield f"http://127.0.0.1:{pub.server_address[1]}/video.mp4"
    pub.shutdown()
    priv.shutdown()


def test_redirect_hop_to_private_address_is_refused_urllib(hop):
    with pytest.raises((urllib.error.URLError, OSError)) as exc:
        urllib.request.urlopen(hop, timeout=5)  # noqa: S310
    assert "127.0.0.2" in str(exc.value)


def test_redirect_hop_to_private_address_is_refused_ytdlp(hop):
    yt_dlp = pytest.importorskip("yt_dlp")
    with yt_dlp.YoutubeDL({"proxy": "", "quiet": True, "no_warnings": True, "noprogress": True}) as ydl:
        with pytest.raises(yt_dlp.utils.DownloadError) as exc:
            ydl.extract_info(hop, download=False)
    assert "non-public address 127.0.0.2" in str(exc.value)


def _proxy_req(proxy: str, raw: bytes) -> bytes:
    host, port = proxy.rsplit("/", 1)[-1].split(":")
    with socket.create_connection((host, int(port)), timeout=5) as s:
        s.sendall(raw)
        s.shutdown(socket.SHUT_WR)
        out = b""
        while chunk := s.recv(65536):
            out += chunk
    return out


def test_child_proxy_checks_every_request(hop):
    from hermes_studio.safe_fetch import start_proxy

    proxy = start_proxy()
    first = _proxy_req(proxy, f"GET {hop} HTTP/1.1\r\nHost: x\r\n\r\n".encode())
    assert first.startswith(b"HTTP/1.0 302") or first.startswith(b"HTTP/1.1 302")
    loc = [ln for ln in first.decode().split("\r\n") if ln.lower().startswith("location:")][0].split(" ", 1)[1]
    second = _proxy_req(proxy, f"GET {loc} HTTP/1.1\r\nHost: x\r\n\r\n".encode())
    assert second.startswith(b"HTTP/1.1 403") and b"secret-metadata" not in second
    port = loc.split(":")[2].split("/")[0]
    tunnel = _proxy_req(proxy, f"CONNECT 127.0.0.2:{port} HTTP/1.1\r\n\r\n".encode())
    assert tunnel.startswith(b"HTTP/1.1 403")


# --------------------------------------------------------------------------- engine paths


def _studio(home: Path) -> Path:
    d = home / ".hermes" / "clips"
    (d / "library").mkdir(parents=True, exist_ok=True)
    return d


def test_duplicate_file_is_confined(fake_home):
    from hermes_studio.edit import duplicate_file
    from hermes_studio.guard import PathRefused

    studio = _studio(fake_home)
    vid = fake_home / "Videos" / "talk.mp4"
    vid.parent.mkdir()
    vid.write_bytes(b"video")
    first = duplicate_file(vid)
    assert first == studio / "edits" / "talk-copy.mp4" and first.read_bytes() == b"video"
    assert duplicate_file(vid) == studio / "edits" / "talk-copy-2.mp4"
    with pytest.raises(ValueError):
        duplicate_file(fake_home / ".hermes" / ".env")  # not media
    link = fake_home / "evil.mp4"
    link.symlink_to(fake_home / ".hermes" / ".env")
    with pytest.raises(ValueError):
        duplicate_file(link)  # .mp4 name, key-file target
    with pytest.raises(PathRefused):
        duplicate_file(vid, fake_home / "Videos" / "out.mp4")  # outside the Studio folder
    with pytest.raises(PathRefused):
        duplicate_file(vid, first)  # existing file
    with pytest.raises(PathRefused):
        duplicate_file(vid, studio / "edits" / "x.txt")  # not a media name


def test_api_edit_refuses_outside_paths(fake_home):
    from hermes_studio import api

    studio = _studio(fake_home)
    outside = fake_home / "Videos" / "talk.mp4"
    outside.parent.mkdir()
    outside.write_bytes(b"v")
    cases = [
        dict(src=str(fake_home / ".hermes" / ".env"), op="duplicate"),
        dict(src="/etc/passwd", op="trim", start=0, end=1),
        dict(src=str(outside), op="duplicate", out="/tmp/x.mp4"),
        dict(src=str(outside), op="trim", start=0, end=1, out=str(outside)),
        dict(src=str(outside), op="drop"),  # drop moves files: Studio folder only
    ]
    for kw in cases:
        with pytest.raises(api.HermesStudioError) as exc:
            api.edit(**kw)
        assert exc.value.code in ("bad_input", "not_found"), kw
    assert outside.read_bytes() == b"v"
    assert not (studio / "edits" / "x.mp4").exists()


def test_out_and_work_dirs_are_confined(fake_home, tmp_path):
    from hermes_studio import api

    studio = _studio(fake_home)
    for bad in ("/tmp/elsewhere", str(fake_home / "Desktop"), str(studio / ".." / "..")):
        with pytest.raises(api.HermesStudioError):
            api._out_dir(bad)
    assert api._out_dir(studio / "exports") == (studio / "exports").resolve()
    with pytest.raises(api.HermesStudioError):
        api._captions_dest(str(fake_home / "captions.mp4"))
    first = api._captions_dest(None)
    first.write_bytes(b"x")
    assert api._captions_dest(None).name == "captions-2.mp4"
    with pytest.raises(api.HermesStudioError):
        api._captions_dest(str(first))  # existing


def test_cli_list_out_is_confined(fake_home, capsys):
    from hermes_studio.cli import main

    _studio(fake_home)
    rc = main(["list", "--out", "/etc", "--json"])
    assert rc != 0
    assert "inside the Studio folder" in capsys.readouterr().out


def test_photo_is_confined(fake_home):
    from hermes_studio import photo

    with pytest.raises(photo.PhotoError):
        photo.run_file("enhance", str(fake_home / ".hermes" / ".env"))
    img = fake_home / "pic.png"
    img.write_bytes(b"not decoded before the path checks")
    with pytest.raises(photo.PhotoError):
        photo.run_file("enhance", str(img), out="/tmp/out.png")
    with pytest.raises(photo.PhotoError):
        photo.run_file("enhance", str(img), out=str(fake_home / "pic.png"))


# --------------------------------------------------------------------------- the plugin


def _plugin():
    spec = importlib.util.spec_from_file_location("hs_plugin_t", ROOT / "hermes_plugin/hermes-studio/__init__.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_plugin_engine_env_is_minimal(monkeypatch):
    m = _plugin()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-pass")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "nope")
    monkeypatch.setenv("HERMES_STUDIO_NAMER", "ollama")
    monkeypatch.setenv("PYTHONPATH", "/x")
    env = m._engine_env({"PYTHONPATH": "/src"})
    assert "OPENAI_API_KEY" not in env and "AWS_SECRET_ACCESS_KEY" not in env
    assert env["HERMES_STUDIO_NAMER"] == "ollama" and env["PYTHONPATH"] == "/src"
    allowed = set(m._ENV_KEEP) | set(m._ENV_KEEP_NT)
    assert all(k in allowed or k.startswith("HERMES_STUDIO_") for k in env)


def test_plugin_env_reaches_engine_subprocess(monkeypatch):
    m = _plugin()
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(kw.get("env") or {})
        raise FileNotFoundError

    monkeypatch.setattr(m, "_engine_available", lambda: True)
    monkeypatch.setattr(m, "_engine_version_ok", lambda *a: True)
    monkeypatch.setattr(m.subprocess, "run", fake_run)
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_no")
    m._run_mod(["list"])
    assert seen and "GITHUB_TOKEN" not in seen


def test_plugin_data_dir_follows_hermes_home(tmp_path, monkeypatch):
    m = _plugin()
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "profile-a"))
    assert m._data_dir() == tmp_path / "profile-a" / "plugin-data" / "hermes-studio"


def test_plugin_refuses_paths_and_links_before_the_engine(fake_home, monkeypatch):
    m = _plugin()
    monkeypatch.setattr(m, "_run_mod", lambda *a, **k: pytest.fail("engine must not run"))
    studio = _studio(fake_home)
    clip = studio / "library" / "c.mp4"
    clip.write_bytes(b"v")
    env = str(fake_home / ".hermes" / ".env")
    calls = [
        lambda: m.hermes_studio_edit(src=env, op="duplicate"),
        lambda: m.hermes_studio_edit(src=str(clip), op="duplicate", out=str(fake_home / "x.mp4")),
        lambda: m.hermes_studio_edit(src=str(clip), op="duplicate", out=str(clip)),
        lambda: m.hermes_studio_edit(src=str(fake_home / "v.mp4"), op="drop"),
        lambda: m.hermes_studio_photo(op="enhance", src=env),
        lambda: m.hermes_studio_photo(op="enhance", src=str(clip)),
        lambda: m.hermes_studio_run(src="http://169.254.169.254/latest/meta-data/"),
        lambda: m.hermes_studio_run(src="file:///etc/passwd"),
        lambda: m.hermes_studio_run(src=str(clip), out="/tmp/x"),
        lambda: m.hermes_studio_captions(src=str(clip), lines=[{"text": "a", "start": 0, "end": 1}], out="/tmp/c.mp4"),
        lambda: m.hermes_studio_transcribe(src=str(clip), work="/var/tmp/w"),
        lambda: m.hermes_studio_list(out="/etc"),
        lambda: m.hermes_studio_probe(src="http://[::ffff:127.0.0.1]:3870/"),
        lambda: m.hermes_studio_recommend(src="http://10.0.0.5/a.mp4"),
        lambda: m.hermes_studio_plan(transcript=env),
    ]
    for i, call in enumerate(calls):
        res = json.loads(call())
        assert res["ok"] is False and res["code"] == "refused", (i, res)


def test_plugin_passes_confined_paths(fake_home, monkeypatch):
    m = _plugin()
    seen = []
    monkeypatch.setattr(m, "_run_mod", lambda argv, **k: seen.append(argv) or {"ok": True})
    studio = _studio(fake_home)
    clip = studio / "library" / "c.mp4"
    clip.write_bytes(b"v")
    assert json.loads(m.hermes_studio_edit(src=str(clip), op="duplicate", out=str(studio / "edits" / "n.mp4")))["ok"]
    assert seen[-1][:2] == ["edit", str(clip.resolve())]


def test_plugin_desk_schema_has_no_host():
    m = _plugin()
    tools = {}

    class Ctx:
        def register_tool(self, name, schema, **kw):
            tools[name] = schema

        def register_command(self, *a, **k):
            pass

    m.register(Ctx())
    assert set(tools["hermes_studio_desk"]["parameters"]["properties"]) == {"port"}


def test_plugin_hint_points_at_a_tag():
    m = _plugin()
    hint = m._missing_engine()["hint"]
    assert "@v" in hint and "/main/" not in hint
    readme = (ROOT / "hermes_plugin/hermes-studio/README.md").read_text()
    assert "/main/" not in readme


def test_plugin_refuses_an_old_engine(monkeypatch):
    m = _plugin()

    class P:
        stdout = "hermes-studio 0.6.1\n"

    monkeypatch.setattr(m, "_engine_available", lambda: True)
    monkeypatch.setattr(m.subprocess, "run", lambda *a, **k: P())
    res = m._run_mod(["list"])
    assert res["code"] == "missing_dependency" and "older" in res["error"]


def test_cues_and_log_are_not_hardcoded():
    src = (ROOT / "hermes_plugin/hermes-studio/__init__.py").read_text()
    assert '".hermes" / "clips" / "agent-cues' not in src and "studio.log" in src
    assert "{**os.environ" not in src
    assert os.environ.get("NEVER_SET_X") is None
