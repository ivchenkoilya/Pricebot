from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEBAPP = ROOT / 'webapp' / 'src'


def test_runtime_localizer_covers_legacy_english_ui_labels():
    source = (WEBAPP / 'RussianUiWidget.tsx').read_text(encoding='utf-8')
    expected = {
        'AI Workspace': 'ИИ-помощник',
        'OWNER': 'ВЛАДЕЛЕЦ',
        'Memory': 'Материалы',
        'AI': 'ИИ',
        'AI INBOX · TELEGRAM': 'ВАЖНОЕ · TELEGRAM',
        'TODAY IN CLARIFY': 'СЕГОДНЯ В CLARIFY',
        'CONTINUE': 'ПРОДОЛЖИТЬ',
        'CLARIFY MEMORY': 'ПАМЯТЬ CLARIFY',
        'SMART SEARCH': 'УМНЫЙ ПОИСК',
        'WRITE WITH CLARIFY': 'НАПИСАТЬ С CLARIFY',
        'AUTONOMOUS COPILOT': 'УМНЫЙ ПОМОЩНИК',
        'AI Inbox': 'Важное',
        'LIVE': 'АКТИВНО',
        'CLARIFY PLANS': 'ТАРИФЫ CLARIFY',
        'BETA · ACTIVE DEVELOPMENT': 'БЕТА · АКТИВНАЯ РАЗРАБОТКА',
    }
    for old, new in expected.items():
        assert repr(old) in source or f"'{old}'" in source
        assert new in source


def test_updated_widgets_do_not_render_known_english_labels_directly():
    files = ['BetaNoticeWidget.tsx', 'CopilotWidget.tsx', 'ReferralProfileWidget.tsx']
    rendered = '\n'.join((WEBAPP / name).read_text(encoding='utf-8') for name in files)
    for old in [
        'BETA · ACTIVE DEVELOPMENT',
        'AUTONOMOUS COPILOT',
        '>AI Inbox<',
        '>LIVE<',
        '>SMART SEARCH<',
        'FULL ANALYSIS',
        'OWNER ANALYTICS',
        'INVITE & EARN',
    ]:
        assert old not in rendered


def test_api_plan_copy_uses_russian_ai_term():
    source = (WEBAPP / 'api.ts').read_text(encoding='utf-8')
    assert ".replaceAll('Smart AI', 'Умный ИИ')" in source
    assert ".replaceAll('Fast AI', 'Быстрый ИИ')" in source
    assert ".replaceAll('AI-запрос', 'ИИ-запрос')" in source
