"""Look layer: layout choice, split band crops, filters, caption spot, audio, word fixes."""
from hermes_studio import look
from hermes_studio.face import Face, FaceTrack
from hermes_studio.framing import split_geometry
from hermes_studio.layout import frame_filters
from hermes_studio.pipeline import _clean_fixes


def test_make_look_defaults_and_clamps():
    lk = look.make_look({"layout": "nope", "face": "side", "face_ratio": 90, "filter": "sepia", "caption_pos": "x", "audio": "loud"})
    assert lk.layout == "fit" and lk.face == "top" and lk.face_ratio == 0.6
    assert lk.filter == "none" and lk.caption_pos == "auto" and lk.audio == "off"
    assert look.make_look({"face_ratio": 40}).face_ratio == 0.4
    assert look.make_look({"face_box": "76,64,22,30"}).face_box == (0.76, 0.64, 0.22, 0.30)
    assert look.make_look({"filter": "Black & White"}).filter == "bw"
    assert look.make_look({"progress": "true"}).progress is True


def test_auto_layout_reads_the_frame():
    talk = Face(0, 0.4, 0.2, 0.2, 0.35, 0.33)
    cam = Face(0, 0.82, 0.05, 0.09, 0.16, 0.1)
    assert look.choose_layout(None, 1920, 1080, 1080, 1920)[0] == "fit"
    assert look.choose_layout(talk, 1920, 1080, 1080, 1920)[0] == "fill"
    assert look.choose_layout(cam, 1920, 1080, 1080, 1920)[0] == "split"
    assert look.choose_layout(talk, 1080, 1920, 1080, 1920)[0] == "fill"


def test_split_bands_add_up_and_flip():
    cam = Face(0, 0.82, 0.05, 0.09, 0.16, 0.1)
    track = FaceTrack([cam], samples=1)
    lk_top = look.make_look({"layout": "split", "face": "top", "face_ratio": 35})
    g = split_geometry(1920, 1080, 1080, 1920, lk_top, cam)
    assert g["face_h"] + g["body_h"] == 1920 and g["face_h"] % 2 == 0
    for c in (g["face"], g["body"]):
        assert c.x >= 0 and c.y >= 0 and c.x + c.w <= 1920 and c.y + c.h <= 1080
    top = frame_filters(1920, 1080, 1080, 1920, "split", "", look=lk_top, track=track)
    lk_bot = look.make_look({"layout": "split", "face": "bottom", "face_ratio": 35})
    bot = frame_filters(1920, 1080, 1080, 1920, "split", "", look=lk_bot, track=track)
    assert "[fc][bc]vstack" in top and "[bc][fc]vstack" in bot


def test_filters_and_progress():
    for name in look.FILTERS:
        chain = look.post_chain(look.make_look({"filter": name}), 10.0, 1920)
        assert (chain == "") == (name == "none")
    assert "hue=s=0" in look.FILTERS["bw"]
    bar = look.post_chain(look.make_look({"progress": True}), 12.0, 1920)
    assert "0xFFC83D" in bar and "overlay=" in bar
    # drawbox's `t` is thickness, not time: a drawbox bar would be full width at frame 1
    assert "drawbox" not in bar and "t/12.000" in bar


def test_progress_bar_grows_with_time(tmp_path):
    """Render 2 s of black with the bar and measure it: short early, full at the end."""
    import shutil
    import subprocess

    import pytest

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    post = look.post_chain(look.make_look({"progress": True}), 2.0, 320, 180)
    out = tmp_path / "bar.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=180x320:r=30:d=2",
         "-filter_complex", f"[0:v]{post},format=gray[o]", "-map", "[o]", str(out)],
        check=True,
    )

    def lit(ts: float) -> float:
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", str(ts), "-i", str(out), "-frames:v", "1",
             "-vf", "crop=180:2:0:316", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
            capture_output=True, check=True,
        ).stdout
        return sum(1 for b in raw if b > 60) / max(1, len(raw))

    early, late = lit(0.3), lit(1.9)
    assert early < 0.3, early
    assert late > 0.85, late


def test_caption_spot_clears_platform_ui():
    lk = look.make_look({})
    align, mv = look.caption_margin(lk, "fit", 1920, 80)
    assert align == 2 and mv >= int(1920 * 0.15)
    _, seam = look.caption_margin(lk, "split", 1920, 80, seam_y=672)
    assert seam != mv
    top_align, _ = look.caption_margin(look.make_look({"caption_pos": "top"}), "fit", 1920, 80)
    assert top_align == 8


def test_audio_clean_chain():
    assert "afftdn" in look.AUDIO_CLEAN and "loudnorm=I=-14" in look.AUDIO_CLEAN


def test_word_fixes():
    assert _clean_fixes("cloud=Claude, marz = Mars,bad") == {"cloud": "Claude", "marz": "Mars"}
