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


def test_safe_filename():
    name = MediaDownloader.safe_filename('Тест / видео: 2026?', '.mp4')
    assert name.endswith('.mp4')
    assert '/' not in name
    assert ':' not in name
