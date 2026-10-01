"""Design + photo: the Canva-style studio that people (desk) and agents (MCP/CLI) share."""

from __future__ import annotations

import base64
import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from hermes_studio import design


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    yield tmp_path


def _png(w=40, h=30, color=(255, 200, 61, 255)) -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGBA", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


def test_every_template_creates_and_renders_every_size():
    for size in design.SIZES:
        for t in design.templates(size):
            doc = design.create(size=size, template=t["id"])
            out = design.render(doc["id"], fmt="jpg")
            assert len(out["files"]) == len(doc["pages"]) == t["pages"]
            w, h = design.SIZES[size][:2]
            from PIL import Image

            assert Image.open(out["files"][0]).size == (w, h)


def test_template_text_stays_on_the_page():
    """Every text layer in every template fits inside the page, wrapped, with no word wider than its box."""
    for size in design.SIZES:
        w, h = design.SIZES[size][:2]
        for t in design.templates(size):
            for p in design.template_pages(t["id"], w, h):
                for lay in p["layers"]:
                    if lay["type"] != "text":
                        continue
                    assert lay["x"] >= 0 and lay["x"] + lay["w"] <= w + 1, (size, t["id"], lay["text"])
                    assert lay["y"] + design.text_height(lay) <= h + 1, (size, t["id"], lay["text"])
                    f = design._font(lay.get("font", "archivo"), lay["size"], lay.get("weight", 400))
                    txt = lay["text"].upper() if lay.get("upper") else lay["text"]
                    for word in txt.split():
                        assert design._text_w(word, f, lay.get("spacing", 0)) <= lay["w"] + 1, (size, t["id"], word)


def test_clean_doc_drops_unknown_and_unsafe_layers():
    doc = design.clean_doc({"w": 1080, "h": 1350, "pages": [{"bg": "javascript:alert(1)", "layers": [
        {"type": "text", "text": "ok", "color": "red; background:url(x)", "font": "../../etc", "size": 1e9},
        {"type": "image", "src": "../../.ssh/id_rsa"},
        {"type": "image", "src": "assets/../../x.png"},
        {"type": "script", "x": 1},
        "not a dict",
    ]}]})
    layers = doc["pages"][0]["layers"]
    assert doc["pages"][0]["bg"] == "#0b0b0c"
    assert len(layers) == 1 and layers[0]["type"] == "text"
    assert layers[0]["color"] == "#f2efe8" and layers[0]["font"] == "archivo" and layers[0]["size"] == 600


def test_ids_and_assets_cannot_escape():
    for bad in ("../x", "d-../../etc", "d-ABC", "", "d-" + "a" * 80):
        assert not design.safe_id(bad)
        with pytest.raises(design.DesignError):
            design.design_dir(bad)
    doc = design.create()
    with pytest.raises(design.DesignError):
        design.asset_path(doc["id"], "assets/../design.json")
    with pytest.raises(design.DesignError):
        design.add_asset(doc["id"], b"<svg onload=alert(1)>")


def test_agent_ops_build_a_design(tmp_path):
    doc = design.create(template="carousel")
    img = tmp_path / "me.png"
    img.write_bytes(_png(200, 300))
    out = design.apply_ops(doc["id"], [
        {"op": "update", "page": 1, "index": 0, "set": {"text": "NEW HOOK"}},
        {"op": "add_image", "page": 1, "path": str(img), "x": 500, "y": 700, "w": 580, "h": 650},
        {"op": "add_page", "bg": "#111111"},
        {"op": "add", "page": 5, "layer": {"type": "rect", "x": 10, "y": 10, "w": 100, "h": 50, "fill": "#ffc83d"}},
        {"op": "background", "page": 2, "color": "#222222"},
        {"op": "remove", "page": 3, "index": 0},
        {"op": "title", "title": "From an agent"},
    ])
    assert out["title"] == "From an agent" and len(out["pages"]) == 5
    assert out["pages"][0]["layers"][0]["text"] == "NEW HOOK"
    assert out["pages"][0]["layers"][-1]["type"] == "image"
    assert out["pages"][1]["bg"] == "#222222"
    with pytest.raises(design.DesignError):
        design.apply_ops(doc["id"], [{"op": "update", "page": 9, "index": 0, "set": {}}])
    with pytest.raises(design.DesignError):
        design.apply_ops(doc["id"], [{"op": "nope"}])
    assert len(design.render(doc["id"])["files"]) == 5


def test_save_drops_images_that_do_not_exist():
    doc = design.create()
    rel = design.add_asset(doc["id"], _png())
    doc["pages"][0]["layers"] = [{"type": "image", "src": rel, "x": 0, "y": 0, "w": 10, "h": 10},
                                 {"type": "image", "src": "assets/ghost-0000000000.png", "x": 0, "y": 0, "w": 10, "h": 10}]
    saved = design.save(doc["id"], doc)
    assert [lay["src"] for lay in saved["pages"][0]["layers"]] == [rel]


def test_resize_keeps_text_on_page_and_edges_anchored():
    doc = design.create(template="carousel")
    doc["pages"][0]["layers"].append({"type": "rect", "x": 600, "y": 900, "w": 480, "h": 450, "fill": "#ffffff"})
    design.save(doc["id"], doc)
    for size in ("story", "square", "youtube-thumb"):
        new = design.resize(doc["id"], size)
        w, h = design.SIZES[size][:2]
        assert (new["w"], new["h"]) == (w, h)
        rect = new["pages"][0]["layers"][-1]
        assert abs(rect["x"] + rect["w"] - w) < 1 and abs(rect["y"] + rect["h"] - h) < 1  # still on the corner
        for p in new["pages"]:
            for lay in p["layers"]:
                if lay["type"] == "text":
                    assert -1 <= lay["x"] and lay["x"] + lay["w"] <= w + 1
                    assert lay["y"] + design.text_height(lay) <= h + 1


def test_list_duplicate_delete():
    a = design.create(title="A")
    b = design.duplicate(a["id"])
    assert b["title"] == "A (copy)"
    assert {d["id"] for d in design.list_designs()} == {a["id"], b["id"]}
    design.delete(a["id"])
    assert [d["id"] for d in design.list_designs()] == [b["id"]]


def test_photo_tools(tmp_path):
    pytest.importorskip("cv2")
    from hermes_studio import photo

    src = tmp_path / "p.png"
    src.write_bytes(_png(64, 80, (120, 110, 100, 255)))
    cut = photo.run_file("cutout", str(src))
    assert cut["transparent"] and cut["file"].endswith(".png")
    enh = photo.run_file("enhance", str(src))
    assert enh["w"] == 64 and enh["h"] == 80
    bw = photo.run_file("look", str(src), look_name="bw")
    assert bw["ok"]
    with pytest.raises(photo.PhotoError):
        photo.decode(b"GIF89a....")
    with pytest.raises(photo.PhotoError):
        photo.run_file("look", str(src), look_name="sepia-ish")


def test_cli_design_contract(capsys):
    from hermes_studio.cli import main

    assert main(["design", "new", "--template", "quote", "--size", "square", "--json"]) == 0
    res = json.loads(capsys.readouterr().out)
    assert res["ok"] and res["design"]["w"] == 1080 and res["design"]["h"] == 1080
    assert main(["design", "render", res["id"], "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["files"]
    assert main(["design", "edit", res["id"], '[{"op":"bad"}]', "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "bad_input"
    assert main(["design", "show", "d-missing00", "--json"]) == 4


def test_mcp_lists_and_runs_design_tools():
    from hermes_studio import mcp

    names = {t["name"] for t in mcp.TOOLS}
    assert {"design_new", "design_list", "design_show", "design_edit", "design_render", "design_resize", "photo"} <= names
    res = mcp.call_tool("design_new", {"template": "thumbnail", "size": "youtube-thumb"})
    assert res["design"]["w"] == 1280
    assert mcp.call_tool("design_render", {"id": res["id"]})["files"]


@pytest.fixture()
def desk():
    from hermes_studio.studio import StudioHandler

    srv = ThreadingHTTPServer(("127.0.0.1", 0), StudioHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


def _req(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    h = {"Host": f"127.0.0.1:{port}"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    c.request(method, path, body=data, headers=h)
    r = c.getresponse()
    raw = r.read()
    return r.status, raw


def test_desk_design_routes(desk):
    st, raw = _req(desk, "POST", "/api/design", {"template": "carousel"})
    assert st == 200
    did = json.loads(raw)["design"]["id"]
    st, raw = _req(desk, "POST", f"/api/design/{did}/asset", {"data": "data:image/png;base64," + base64.b64encode(_png()).decode()})
    assert st == 200
    src = json.loads(raw)["src"]
    st, raw = _req(desk, "GET", f"/design/{did}/{src}")
    assert st == 200 and raw.startswith(b"\x89PNG")
    st, raw = _req(desk, "POST", f"/api/design/{did}/export", {"page": 1, "data": base64.b64encode(_png()).decode()})
    assert st == 200
    st, _ = _req(desk, "GET", f"/design/{did}/export/page-1.png")
    assert st == 200
    assert _req(desk, "GET", "/design/fabric.min.js")[0] == 200
    assert _req(desk, "GET", "/design/fonts/Archivo.ttf")[0] == 200


def test_desk_design_routes_refuse_tricks(desk):
    st, raw = _req(desk, "POST", "/api/design", {})
    did = json.loads(raw)["design"]["id"]
    assert _req(desk, "GET", "/design/fonts/..%2f..%2fstudio.py")[0] == 404
    assert _req(desk, "GET", f"/design/{did}/assets/..%2fdesign.json")[0] == 404
    assert _req(desk, "GET", f"/design/{did}/design.json")[0] == 404
    assert _req(desk, "GET", "/design/d-zzzzzz/assets/x-0000.png")[0] == 404
    # writes need JSON + same origin (no CSRF from another tab)
    c = http.client.HTTPConnection("127.0.0.1", desk, timeout=5)
    c.request("POST", "/api/design", body=b"{}", headers={"Host": f"127.0.0.1:{desk}", "Content-Type": "text/plain"})
    assert c.getresponse().status == 415
    st, _ = _req(desk, "POST", "/api/design", {}, headers={"Origin": "https://evil.example"})
    assert st == 403
    st, raw = _req(desk, "POST", f"/api/design/{did}/asset", {"data": base64.b64encode(b"<svg/>").decode()})
    assert st == 400
    st, raw = _req(desk, "POST", f"/api/design/{did}/from-clip", {"job": "../../x", "file": "a.jpg"})
    assert st == 400
