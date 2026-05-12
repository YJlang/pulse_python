from app.services.promotion_video_service import PromotionVideoService


def test_vertical_reel_omits_reference_images_by_default(monkeypatch):
    monkeypatch.setenv("PROMOTION_VEO_ASPECT_RATIO", "9:16")
    monkeypatch.delenv("PROMOTION_VEO_ALLOW_VERTICAL_REFERENCE_IMAGES", raising=False)

    service = PromotionVideoService()
    reference_images = [object()]

    assert service._reference_images_for_generation(reference_images) is None


def test_vertical_reference_images_can_be_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("PROMOTION_VEO_ASPECT_RATIO", "9:16")
    monkeypatch.setenv("PROMOTION_VEO_ALLOW_VERTICAL_REFERENCE_IMAGES", "true")

    service = PromotionVideoService()
    reference_images = [object()]

    assert service._reference_images_for_generation(reference_images) is reference_images


def test_landscape_generation_keeps_reference_images(monkeypatch):
    monkeypatch.setenv("PROMOTION_VEO_ASPECT_RATIO", "16:9")
    monkeypatch.delenv("PROMOTION_VEO_ALLOW_VERTICAL_REFERENCE_IMAGES", raising=False)

    service = PromotionVideoService()
    reference_images = [object()]

    assert service._reference_images_for_generation(reference_images) is reference_images
