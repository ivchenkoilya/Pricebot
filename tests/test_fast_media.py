from app.services.fast_media import youtube_video_id


def test_youtube_video_id_variants():
    assert youtube_video_id('https://www.youtube.com/watch?v=abcdefghijk') == 'abcdefghijk'
    assert youtube_video_id('https://youtu.be/abcdefghijk?t=5') == 'abcdefghijk'
    assert youtube_video_id('https://youtube.com/shorts/abcdefghijk') == 'abcdefghijk'
    assert youtube_video_id('https://youtube.com/embed/abcdefghijk') == 'abcdefghijk'


def test_youtube_video_id_rejects_other_urls():
    assert youtube_video_id('https://example.com/watch?v=abcdefghijk') == ''
    assert youtube_video_id('https://youtube.com/') == ''
