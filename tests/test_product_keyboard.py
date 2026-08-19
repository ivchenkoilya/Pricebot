from app.bot.keyboards import product_keyboard


def test_unpriced_product_hides_price_actions():
    kb = product_keyboard(1, 'https://example.com/p', price_available=False)
    labels = [button.text for row in kb.inline_keyboard for button in row]
    assert '🎯 Условие' not in labels
    assert '📊 История' not in labels
    assert '🔔 Следить' in labels
    assert '🛒 Открыть' in labels
