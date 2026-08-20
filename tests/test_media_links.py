from app.services.media_downloader import MediaDownloader, is_media_url, media_intent, platform_for_url


def test_supported_media_urls():
    assert is_media_url('https://www.youtube.com/watch?v=abc')
    assert is_media_url('https://youtu.be/abc')
    assert is_media_url('https://youtube.com/shorts/abc')
    assert is_media_url('https://www.tiktok.com/@user/video/123')
    assert is_media_url('https://vm.tiktok.com/abc/')
    assert is_media_url('https://vt.tiktok.com/abc/')
    assert not is_media_url('https://example.com/article')


def test_platform_detection():
    assert platform_for_url('https://youtube.com/shorts/abc') == 'YouTube'
    assert platform_for_url('https://vm.tiktok.com/abc') == 'TikTok'
    assert platform_for_url('https://instagram.com/reel/abc') == 'Instagram'
    assert platform_for_url('https://x.com/user/status/1') == 'X / Twitter'


def test_media_intents():
    assert media_intent('') == 'inspect'
    assert media_intent('скачай это видео') == 'video'
    assert media_intent('скачай только аудио mp3') == 'audio'
    assert media_intent('сделай текст из этого') == 'transcribe'
    assert media_intent('кратко расскажи о чем ролик') == 'summary'
    assert media_intent('выдели главное') == 'main'
    assert media_intent('объясни простыми словами') == 'plain'


def test_safe_filename():
    name = MediaDownloader.safe_filename('Тест / видео: 2026?', '.mp4')
    assert name.endswith('.mp4')
    assert '/' not in name
    assert ':' not in name


def test_fast_json3_subtitle_parser():
    payload = '{"events":[{"segs":[{"utf8":"Привет "},{"utf8":"мир"}]},{"segs":[{"utf8":"Привет мир"}]},{"segs":[{"utf8":"Вторая фраза"}]}]}'
    assert MediaDownloader._parse_json3(payload) == 'Привет мир Вторая фраза'


def test_fast_vtt_subtitle_parser():
    payload = '''WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n<b>Первая фраза</b>\n\n00:00:01.000 --> 00:00:02.000\nПервая фраза\n\n00:00:02.000 --> 00:00:03.000\nВторая фраза\n'''
    assert MediaDownloader._parse_vtt(payload) == 'Первая фраза Вторая фраза'


def test_bot_challenge_is_not_reported_as_private_video():
    text = MediaDownloader._friendly_error("Sign in to confirm you're not a bot")
    assert 'приват' not in text.lower()
    assert 'youtube' in text.lower()
