"""Face placement: eye line, headroom, lead room, safe zone, camera choice."""
from hermesclip import framing
from hermesclip.face import Face, FaceTrack, main_subject

SRC_W, SRC_H, OUT_W, OUT_H = 1920, 1080, 1080, 1920


def _talk(t=0.0, cx=0.5, yaw=0.0):
    # A talking head: face ~40% of frame height, eyes a third down the box.
    w, h = 0.19, 0.42
    return Face(t, cx - w / 2, 0.17, w, h, 0.17 + h * 0.37, yaw, 0.95)


def _eye_share(face, crop):
    return (face.eye_y * SRC_H - crop.y) / crop.h


def test_eye_line_lands_on_upper_third():
    f = _talk()
    c = framing.still_crop(SRC_W, SRC_H, OUT_W, OUT_H, f)
    assert abs(_eye_share(f, c) - framing.EYE_LINE) < 0.06 or c.y == 0


def test_head_never_cut():
    # Face near the top of the source: the crop must start at or above the head.
    f = Face(0, 0.4, 0.02, 0.2, 0.4, 0.14)
    c = framing.still_crop(SRC_W, SRC_H, OUT_W, OUT_H, f)
    assert c.y <= f.y * SRC_H


def test_lead_room_follows_the_gaze():
    left = framing.still_crop(SRC_W, SRC_H, OUT_W, OUT_H, _talk(yaw=-1))
    right = framing.still_crop(SRC_W, SRC_H, OUT_W, OUT_H, _talk(yaw=1))
    centre = framing.still_crop(SRC_W, SRC_H, OUT_W, OUT_H, _talk(yaw=0))
    # Looking screen-left: the crop slides left to leave space on that side.
    assert left.x < centre.x < right.x


def test_face_sits_left_of_the_button_rail():
    f = _talk()
    c = framing.still_crop(SRC_W, SRC_H, OUT_W, OUT_H, f)
    share = (f.cx * SRC_W - c.x) / c.w
    assert 0.42 < share < 0.5


def test_crop_stays_inside_the_source_and_has_output_aspect():
    for cx in (0.05, 0.5, 0.95):
        c = framing.still_crop(SRC_W, SRC_H, OUT_W, OUT_H, _talk(cx=cx))
        assert 0 <= c.x and c.x + c.w <= SRC_W and 0 <= c.y and c.y + c.h <= SRC_H
        assert abs(c.w / c.h - OUT_W / OUT_H) < 0.01


def test_small_face_gets_a_capped_zoom():
    small = Face(0, 0.47, 0.3, 0.06, 0.1, 0.34)
    c = framing.still_crop(SRC_W, SRC_H, OUT_W, OUT_H, small)
    assert c.h < SRC_H                       # zoomed in
    assert OUT_H / c.h <= framing.MAX_UPSCALE + 0.01


def test_still_subject_gets_a_locked_camera():
    track = FaceTrack([_talk(t, 0.5 + 0.005 * i) for i, t in enumerate((1, 3, 5, 7))], samples=4)
    cam = framing.camera(SRC_W, SRC_H, OUT_W, OUT_H, track)
    assert isinstance(cam, framing.Crop)


def test_moving_subject_gets_a_smooth_capped_pan():
    track = FaceTrack([_talk(t, cx) for t, cx in ((1, 0.35), (3, 0.42), (5, 0.5), (7, 0.55))], samples=4)
    cam = framing.camera(SRC_W, SRC_H, OUT_W, OUT_H, track)
    assert isinstance(cam, framing.CropPath)
    for (t0, x0), (t1, x1) in zip(cam.keys, cam.keys[1:], strict=False):
        if 1e-3 < t1 - t0 < 100:
            assert abs(x1 - x0) / (t1 - t0) <= framing.MAX_PAN_SPEED * SRC_W + 2
    assert "if(lt(t" in cam.ffmpeg()


def test_big_jump_is_a_hard_cut_not_a_whip_pan():
    track = FaceTrack([_talk(1, 0.25), _talk(3, 0.25), _talk(5, 0.78), _talk(7, 0.78)], samples=4)
    cam = framing.camera(SRC_W, SRC_H, OUT_W, OUT_H, track)
    assert isinstance(cam, framing.CropPath)
    assert any(abs(t1 - t0) < 1e-3 and x0 != x1 for (t0, x0), (t1, x1) in zip(cam.keys, cam.keys[1:], strict=False))


def test_main_subject_ignores_a_stray_face():
    person = [_talk(t) for t in (1, 2, 3, 4)]
    poster = Face(2.5, 0.02, 0.02, 0.05, 0.08, 0.05)
    frames = [[person[0]], [person[1], poster], [person[2]], [person[3]]]
    picked = main_subject(frames)
    assert poster not in picked and len(picked) == 4


def test_facecam_band_is_tight_and_manual_box_is_respected():
    from hermesclip.look import make_look

    cam = Face(0, 0.80, 0.74, 0.09, 0.2, 0.81)
    g = framing.split_geometry(SRC_W, SRC_H, OUT_W, OUT_H, make_look({"face_ratio": 35}), cam)
    assert g["face"].h < SRC_H * 0.45
    boxed = framing.split_geometry(SRC_W, SRC_H, OUT_W, OUT_H, make_look({"face_box": "70,60,28,38"}), None)
    f = boxed["face"]
    assert f.x >= int(0.70 * SRC_W) - 2 and f.x + f.w <= int(0.98 * SRC_W) + 2
