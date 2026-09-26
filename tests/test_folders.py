"""Platform folders: every source gets a clear home."""
from hermesclip.folders import folder_name, platform_of, pretty_title, youtube_id


def test_platforms_by_url():
    cases = {
        "https://www.youtube.com/watch?v=VQRSnDst6Mc": "YouTube",
        "https://youtu.be/VQRSnDst6Mc": "YouTube",
        "https://www.twitch.tv/somestreamer": "Twitch",
        "https://kick.com/somestreamer": "Kick",
        "https://x.com/user/status/1": "X",
        "https://www.tiktok.com/@user/video/1": "TikTok",
        "https://rumble.com/v123": "Rumble",
        "https://m.facebook.com/watch?v=1": "Facebook",
        "https://www.newsite.tv/live/abc": "Newsite",
    }
    for url, want in cases.items():
        assert platform_of(url) == want, url


def test_platforms_for_files():
    assert platform_of("/videos/Youtube_Nmrg1Rn7Ht4.mp4") == "YouTube"
    assert platform_of("/cache/hermesclip-VQRSnDst6Mc/source.mp4") == "YouTube"
    assert platform_of("/videos/talk.mp4") == "Local files"
    assert platform_of("/videos/twitch_vod_1.mp4") == "Twitch"


def test_titles_and_folder_names():
    assert youtube_id("/videos/Youtube_Nmrg1Rn7Ht4.mp4") == "Nmrg1Rn7Ht4"
    assert youtube_id("https://youtu.be/VQRSnDst6Mc?t=3") == "VQRSnDst6Mc"
    assert pretty_title("Youtube_Nmrg1Rn7Ht4", "/v/Youtube_Nmrg1Rn7Ht4.mp4") == "Nmrg1Rn7Ht4"
    assert folder_name('How: I "Won" / Lost?', "abc123") == "How I Won Lost [abc123]"
