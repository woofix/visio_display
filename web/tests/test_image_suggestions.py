import io
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from constants import PRIVATE_DATA_DIR, UPLOAD_FOLDER
from services.keyword_recognition_svc import extract_keywords, normalize_text, tokenize


def _png_bytes(color=(180, 40, 30)):
    output = io.BytesIO()
    Image.new("RGB", (32, 20), color).save(output, "PNG")
    return output.getvalue()


class KeywordRecognitionTests(unittest.TestCase):
    def test_normalize_text_removes_accents_punctuation_and_plural(self):
        self.assertEqual(normalize_text("Steaks, frites & gâteau!"), "steaks frites gateau")
        self.assertEqual(tokenize("Steaks, frites & gâteau!"), ["steak", "frite", "gateau"])

    def test_detects_dictionary_keywords_and_aliases(self):
        detected = extract_keywords("Menu: steak frites et gâteau")
        words = [item["keyword"] for item in detected]

        self.assertIn("steak", words)
        self.assertIn("frites", words)
        self.assertIn("dessert", words)

    def test_detects_more_common_menu_words(self):
        detected = extract_keywords("poulet curry, pâtes au saumon et burger")
        words = [item["keyword"] for item in detected]

        self.assertIn("poulet", words)
        self.assertIn("pates", words)
        self.assertIn("saumon", words)
        self.assertIn("burger", words)

    def test_scoring_prefers_direct_keyword(self):
        detected = {item["keyword"]: item["score"] for item in extract_keywords("steak grillade")}

        self.assertEqual(detected["steak"], 100)


class ImageSuggestionServiceTests(unittest.TestCase):
    def setUp(self):
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        for entry in os.listdir(UPLOAD_FOLDER):
            os.remove(os.path.join(UPLOAD_FOLDER, entry))
        cache_path = os.path.join(PRIVATE_DATA_DIR, "cache", "image_suggestions")
        os.makedirs(cache_path, exist_ok=True)
        for entry in os.listdir(cache_path):
            os.remove(os.path.join(cache_path, entry))
        self.cfg = {
            "order": [],
            "disabled": [],
            "groups": {},
            "media_keywords": {},
            "features": {"videos": True},
        }

    def _write_media(self, filename, color=(180, 40, 30)):
        path = os.path.join(UPLOAD_FOLDER, filename)
        Image.new("RGB", (64, 36), color).save(path)
        return path

    def test_local_suggestions_use_media_keywords_first(self):
        from services import image_suggestions_svc

        self._write_media("cantine.jpg")
        self.cfg["media_keywords"] = {"cantine.jpg": ["steak"]}

        with patch.object(image_suggestions_svc, "load_config", return_value=self.cfg):
            data = image_suggestions_svc.suggest_images("steak frites")

        self.assertFalse(data["fallback"])
        self.assertEqual(data["suggestions"][0]["source"], "local")
        self.assertEqual(data["suggestions"][0]["filename"], "cantine.jpg")

    def test_fallback_without_image(self):
        from services import image_suggestions_svc

        with patch.object(image_suggestions_svc, "load_config", return_value=self.cfg):
            data = image_suggestions_svc.suggest_images("steak frites")

        self.assertTrue(data["fallback"])
        self.assertEqual(data["suggestions"], [])

    def test_absence_of_api_key_does_not_trigger_external_search_by_default(self):
        from services import image_suggestions_svc

        with (
            patch.object(image_suggestions_svc, "load_config", return_value=self.cfg),
            patch.object(image_suggestions_svc, "pexels_search", side_effect=AssertionError("external called")),
        ):
            data = image_suggestions_svc.suggest_images("pizza")

        self.assertTrue(data["fallback"])

    def test_external_provider_failure_is_non_blocking(self):
        from services import image_suggestions_svc

        with (
            patch.object(image_suggestions_svc, "load_config", return_value=self.cfg),
            patch.object(image_suggestions_svc, "pexels_search", side_effect=RuntimeError("offline")),
        ):
            data = image_suggestions_svc.suggest_images("pizza", include_external=True)

        self.assertTrue(data["fallback"])

    def test_cache_download_reuses_existing_file(self):
        from services import image_suggestions_svc

        response = Mock()
        response.url = "https://images.pexels.com/photos/pizza.png"
        response.headers = {"Content-Type": "image/png"}
        response.content = _png_bytes()
        response.raise_for_status.return_value = None

        with patch.object(image_suggestions_svc.requests, "get", return_value=response) as get:
            first = image_suggestions_svc.cache_external_image(response.url)
            second = image_suggestions_svc.cache_external_image(response.url)

        self.assertEqual(first["local_path"], second["local_path"])
        self.assertTrue(first["local_path"].startswith(os.path.join(PRIVATE_DATA_DIR, "cache", "image_suggestions")))
        self.assertTrue(os.path.exists(first["local_path"]))
        self.assertEqual(get.call_count, 1)

    def test_announcement_editor_does_not_embed_menu_suggestions(self):
        template = Path(__file__).resolve().parents[1] / "templates" / "admin_announcements.html"
        html = template.read_text(encoding="utf-8")

        self.assertIn('id="announcement-form"', html)
        self.assertIn('id="layout-json"', html)
        self.assertNotIn('id="suggest-images-btn"', html)

    def test_menu_page_has_specialized_suggestion_button(self):
        template = Path(__file__).resolve().parents[1] / "templates" / "admin_menus.html"
        html = template.read_text(encoding="utf-8")

        self.assertIn('id="menu-form"', html)
        self.assertIn('id="menu-suggest-btn"', html)
        self.assertIn('id="menu-image-choices"', html)
        self.assertIn('name="starter_text"', html)
        self.assertIn('name="main_text"', html)
        self.assertIn('name="dessert_text"', html)
        self.assertIn("menu-image-carousel", html)
        self.assertIn("menu-preview-zoom", html)
        self.assertIn("first.local_url || imageUrl || first.external_url", html)
        self.assertNotIn("loadSuggestions();", html)
        self.assertNotIn(">salade composée</textarea>", html)
        self.assertNotIn(">steak frites", html)
        self.assertNotIn(">dessert du jour</textarea>", html)

    def test_announcement_pexels_results_can_open_large_preview(self):
        template = Path(__file__).resolve().parents[1] / "templates" / "admin_announcements.html"
        html = template.read_text(encoding="utf-8")

        self.assertIn('class="thumb"', html)
        self.assertIn('data-src="${esc(item.thumb_data || item.url || \'\')}"', html)
        self.assertIn('data-fallback-src="${esc(item.thumb_data || \'\')}"', html)

    def test_menu_lines_are_parsed_for_quick_menu(self):
        from services.menu_svc import parse_menu_lines

        self.assertEqual(parse_menu_lines(" steak frites \n\n- pizza\n salade "), ["steak frites", "pizza", "salade"])

    def test_menu_sections_are_parsed_for_quick_menu(self):
        from services.menu_svc import parse_menu_sections

        sections = parse_menu_sections({
            "starter": " salade ",
            "main": "- steak frites\npizza",
            "dessert": "tarte",
        })

        self.assertEqual([section["key"] for section in sections], ["starter", "main", "dessert"])
        self.assertEqual(sections[1]["lines"], ["steak frites", "pizza"])

    def test_menu_analysis_uses_external_suggestions_when_no_local_image(self):
        from services import image_suggestions_svc
        from services import menu_svc

        external = {
            "title": "Pizza",
            "url": "https://images.pexels.com/photos/pizza.jpeg",
            "thumb_url": "https://images.pexels.com/photos/pizza-small.jpeg",
            "source": "pexels",
        }
        with (
            patch.object(image_suggestions_svc, "load_config", return_value=self.cfg),
            patch.object(menu_svc, "load_config", return_value=self.cfg),
            patch.object(image_suggestions_svc, "pexels_search", return_value=[]),
        ):
            items = menu_svc.suggest_menu_lines("pizza")

        self.assertEqual(items[0]["suggestions"], [])

        with (
            patch.object(image_suggestions_svc, "load_config", return_value=self.cfg),
            patch.object(menu_svc, "load_config", return_value=self.cfg),
            patch.object(image_suggestions_svc, "pexels_search", return_value=[external]),
        ):
            items = menu_svc.suggest_menu_lines("pizza")

        self.assertEqual(items[0]["suggestions"][0]["source"], "pexels")
        self.assertEqual(items[0]["suggestions"][0]["preview_url"], "https://images.pexels.com/photos/pizza-small.jpeg")

    def test_external_suggestions_use_only_pexels(self):
        from services import image_suggestions_svc

        pexels = {
            "title": "Salad bowl",
            "url": "https://images.pexels.com/photos/salad.jpeg",
            "thumb_url": "https://images.pexels.com/photos/salad-small.jpeg",
            "source": "pexels",
        }
        with (
            patch.object(image_suggestions_svc, "load_config", return_value=self.cfg),
            patch.object(image_suggestions_svc, "pexels_search", return_value=[pexels]) as pexels_search,
        ):
            data = image_suggestions_svc.suggest_images("salade", include_external=True)

        self.assertGreaterEqual(pexels_search.call_count, 1)
        pexels_queries = [call.args[0] for call in pexels_search.call_args_list]
        self.assertIn("salad food", " ".join(pexels_queries))
        self.assertEqual(data["suggestions"][0]["source"], "pexels")

    def test_external_suggestions_try_full_dish_before_keywords(self):
        from services import image_suggestions_svc

        dish = {
            "title": "Steak and chips",
            "url": "https://images.pexels.com/photos/steak-chips.jpeg",
            "thumb_url": "https://images.pexels.com/photos/steak-chips-small.jpeg",
            "source": "pexels",
        }
        with (
            patch.object(image_suggestions_svc, "load_config", return_value=self.cfg),
            patch.object(image_suggestions_svc, "pexels_search", return_value=[dish]) as pexels_search,
        ):
            data = image_suggestions_svc.suggest_images("steak frites", include_external=True)

        self.assertIn("steak frite food dish", pexels_search.call_args_list[0].args[0])
        self.assertEqual(data["suggestions"][0]["title"], "Steak and chips")

    def test_pexels_is_skipped_without_api_key(self):
        from services import announcement_svc

        with (
            patch.object(announcement_svc, "pexels_api_key", return_value=""),
            patch.object(announcement_svc.requests, "get", side_effect=AssertionError("network called")),
        ):
            self.assertEqual(announcement_svc.pexels_search("pizza food", limit=3), [])

    def test_pexels_results_are_used_for_external_suggestions(self):
        from services import image_suggestions_svc

        pexels = {
            "title": "Pizza from Pexels",
            "url": "https://images.pexels.com/photos/pizza.jpeg",
            "thumb_url": "https://images.pexels.com/photos/pizza-small.jpeg",
            "source": "pexels",
        }
        with (
            patch.object(image_suggestions_svc, "load_config", return_value=self.cfg),
            patch.object(image_suggestions_svc, "pexels_search", return_value=[pexels]),
        ):
            data = image_suggestions_svc.suggest_images("pizza", include_external=True)

        self.assertEqual(data["suggestions"][0]["source"], "pexels")

    def test_menu_image_choices_are_parsed_and_cached(self):
        from services import menu_svc

        choice_json = '{"salade":{"source":"pexels","external_url":"https://images.pexels.com/photos/salad.png","preview_url":"data:image/png;base64,abc"}}'
        cached = {
            "filename": "salad.png",
            "local_path": os.path.join(PRIVATE_DATA_DIR, "cache", "image_suggestions", "salad.png"),
            "local_url": "/admin/announcements/suggestion-cache/salad.png",
        }
        with patch.object(menu_svc, "cache_external_image", return_value=cached):
            choices = menu_svc.parse_menu_image_choices(choice_json)

        self.assertEqual(choices["salade"]["source"], "cache")
        self.assertEqual(choices["salade"]["local_path"], cached["local_path"])

    def test_quick_menu_creates_animated_mp4_when_ffmpeg_succeeds(self):
        from services import menu_svc

        def fake_ffmpeg(args, **_kwargs):
            Path(args[-1]).write_bytes(b"mp4")
            return Mock(returncode=0)

        with (
            patch.object(menu_svc, "suggest_images", return_value={"keywords": [], "suggestions": []}),
            patch.object(menu_svc, "load_config", return_value={"order": []}),
            patch.object(menu_svc, "save_config"),
            patch.object(menu_svc, "generate_standard_renditions") as renditions,
            patch.object(menu_svc, "log_activity"),
            patch.object(menu_svc.subprocess, "run", side_effect=fake_ffmpeg),
        ):
            filename = menu_svc.create_menu_from_text(
                "Menu animé",
                sections={"starter": "salade", "main": "poulet", "dessert": "tarte"},
                duration=6,
                screens=["__default__"],
                username="admin",
            )

        self.assertTrue(filename.endswith(".mp4"))
        self.assertTrue(os.path.exists(os.path.join(UPLOAD_FOLDER, filename)))
        renditions.assert_called_once_with(filename)

    def test_quick_menu_falls_back_to_png_when_animation_fails(self):
        from services import menu_svc

        with (
            patch.object(menu_svc, "suggest_images", return_value={"keywords": [], "suggestions": []}),
            patch.object(menu_svc, "load_config", return_value={"order": []}),
            patch.object(menu_svc, "save_config"),
            patch.object(menu_svc, "generate_standard_renditions") as renditions,
            patch.object(menu_svc, "log_activity"),
            patch.object(menu_svc.subprocess, "run", side_effect=RuntimeError("ffmpeg failed")),
        ):
            filename = menu_svc.create_menu_from_text(
                "Menu statique",
                sections={"starter": "salade", "main": "poulet", "dessert": "tarte"},
                duration=6,
                screens=["__default__"],
                username="admin",
            )

        self.assertTrue(filename.endswith(".png"))
        self.assertTrue(os.path.exists(os.path.join(UPLOAD_FOLDER, filename)))
        renditions.assert_called_once_with(filename)
