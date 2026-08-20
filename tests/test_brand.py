from app.brand import clarify_banner_jpeg


def test_generated_banner_is_valid_jpeg():
    data = clarify_banner_jpeg()
    assert data.startswith(b'\xff\xd8\xff')
    assert data.endswith(b'\xff\xd9')
    assert len(data) > 10_000
