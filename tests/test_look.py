"""Look layer: layout choice, split band crops, filters, caption spot, audio, word fixes."""
from hermesclip import look
from hermesclip.layout import frame_filters
from hermesclip.pipeline import _clean_fixes


def test_make_look_defaults_and_clamps():
    lk = look.make_look({"layout": "nope", "face": "side", "face_ratio": 90, "filter": "sepia", "caption_pos": "x", "audio": "loud"})
    assert lk.layout == "fit" and lk.face == "top" and lk.face_ratio == 0.6
    assert lk.filter == "none" and lk.caption_pos == "auto" and lk.audio == "off"
    assert look.make_look({"face_ratio": 40}).face_ratio == 0.4
    assert look.make_look({"face_box": "76,64,22,30"}).face_box == (0.76, 0.64, 0.22, 0.30)
    assert look.make_look({"filter": "Black & White"}).filter == "bw"
    assert look.make_look({"progress": "true"}).progress is True


def test_auto_layout_reads_the_frame():
    assert look.choose_layout(None, 1920, 1080, 1080, 1920)[0] == "fit"
    # Big centred face: talking head -> speaker crop
    assert look.choose_layout((0.4, 0.2, 0.2, 0.35), 1920, 1080, 1080, 1920)[0] == "fill"
    # Small face in a corner: facecam -> split
    assert look.choose_layout((0.82, 0.05, 0.09, 0.16), 1920, 1080, 1080, 1920)[0] == "split"
    # Already vertical
    assert look.choose_layout((0.4, 0.2, 0.2, 0.2), 1080, 1920, 1080, 1920)[0] == "fill"


def test_split_bands_add_up_and_flip():
    box = (0.82, 0.05, 0.09, 0.16)
    lk_top = look.make_look({"layout": "split", "face": "top", "face_ratio": 35})
    g = look.split_geometry(1920, 1080, 1080, 1920, lk_top, box)
    assert g["face_h"] + g["body_h"] == 1920 and g["face_h"] % 2 == 0
    for crop in (g["face"], g["body"]):
        w, h, x, y = crop  # ffmpeg crop order
        assert x >= 0 and y >= 0 and x + w <= 1920 and y + h <= 1080
    top = frame_filters(1920, 1080, 1080, 1920, "split", "", look=lk_top, box=box)
    lk_bot = look.make_look({"layout": "split", "face": "bottom", "face_ratio": 35})
    bot = frame_filters(1920, 1080, 1080, 1920, "split", "", look=lk_bot, box=box)
    assert "vstack" in top and "vstack" in bot and top != bot


def test_filters_and_progress():
    for name in look.FILTERS:
        chain = look.post_chain(look.make_look({"filter": name}), 10.0, 1920)
        assert (chain == "") == (name == "none")
    assert "hue=s=0" in look.FILTERS["bw"]
    bar = look.post_chain(look.make_look({"progress": True}), 12.0, 1920)
    assert "drawbox" in bar and "0xFFC83D" in bar


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
