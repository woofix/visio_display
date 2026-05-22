import io
import os
import sys
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
        os.environ["MEDIA_DIR"] = os.path.dirname(UPLOAD_FOLDER)
        os.environ["PRIVATE_DIR"] = PRIVATE_DATA_DIR
        for module_name in (
            "constants",
            "services.announcement_svc",
            "services.image_suggestions_svc",
            "services.menu_svc",
        ):
            sys.modules.pop(module_name, None)
        services_pkg = sys.modules.get("services")
        if services_pkg is not None:
            for attr in ("announcement_svc", "image_suggestions_svc", "menu_svc"):
                if hasattr(services_pkg, attr):
                    delattr(services_pkg, attr)
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
        self.assertIn("menu-image-choice-list", html)
        self.assertIn("menu-image-choice", html)
        self.assertIn("menu-preview-zoom", html)
        self.assertIn("first.local_url || imageUrl || first.external_url", html)
        self.assertNotIn("\n    }\n    }\n    async function loadSuggestions", html)
        self.assertNotIn("loadSuggestions();", html)
        self.assertNotIn(">salade composée</textarea>", html)
        self.assertNotIn(">steak frites", html)
        self.assertNotIn(">dessert du jour</textarea>", html)

    def test_announcement_editor_has_qr_tool(self):
        template = Path(__file__).resolve().parents[1] / "templates" / "admin_announcements.html"
        html = template.read_text(encoding="utf-8")

        self.assertIn('id="qr-tool"', html)
        self.assertIn('id="qr-panel"', html)
        self.assertIn('/admin/announcements/qr-code', html)
        self.assertIn('value="wpa3"', html)

    def test_wifi_qr_payload_escapes_special_characters_and_keeps_wpa3_mobile_compatible(self):
        from services.qr_svc import build_qr_payload

        payload = build_qr_payload({
            "type": "wifi",
            "ssid": 'Mon:Wifi;Invite"',
            "password": r"pa\ss;word,42",
            "security": "wpa3",
            "hidden": True,
        })

        self.assertEqual(payload, r"WIFI:T:WPA;S:Mon\:Wifi\;Invite\";P:pa\\ss\;word\,42;H:true;;")

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

    def test_external_suggestions_try_exact_dish_before_keywords(self):
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

        self.assertEqual("steak frites", pexels_search.call_args_list[0].args[0])
        self.assertEqual("", pexels_search.call_args_list[0].kwargs["orientation"])
        self.assertEqual("", pexels_search.call_args_list[0].kwargs["size"])
        self.assertEqual(data["suggestions"][0]["title"], "Steak and chips")

    def test_external_suggestions_try_augmented_dish_when_exact_has_no_results(self):
        from services import image_suggestions_svc

        dish = {
            "title": "Steak and chips",
            "url": "https://images.pexels.com/photos/steak-chips.jpeg",
            "thumb_url": "https://images.pexels.com/photos/steak-chips-small.jpeg",
            "source": "pexels",
        }

        def fake_pexels(query, **_kwargs):
            if query == "steak frites":
                return []
            return [dish]

        with (
            patch.object(image_suggestions_svc, "load_config", return_value=self.cfg),
            patch.object(image_suggestions_svc, "pexels_search", side_effect=fake_pexels) as pexels_search,
        ):
            data = image_suggestions_svc.suggest_images("steak frites", include_external=True)

        pexels_queries = [call.args[0] for call in pexels_search.call_args_list]
        self.assertEqual(["steak frites", "steak frite food dish"], pexels_queries[:2])
        self.assertEqual(data["suggestions"][0]["title"], "Steak and chips")

    def test_pexels_is_skipped_without_api_key(self):
        from services import announcement_svc

        with (
            patch.object(announcement_svc, "pexels_api_key", return_value=""),
            patch.object(announcement_svc.requests, "get", side_effect=AssertionError("network called")),
        ):
            self.assertEqual(announcement_svc.pexels_search("pizza food", limit=3), [])

    def test_pexels_api_key_reads_plain_env_value(self):
        from services import announcement_svc

        with patch.dict(os.environ, {"PEXELS_API_KEY": " plain-key "}, clear=False):
            self.assertEqual(announcement_svc.pexels_api_key(), "plain-key")

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

    def test_pexels_search_keeps_results_when_thumbnail_embedding_fails(self):
        from services import announcement_svc

        response = Mock()
        response.json.return_value = {
            "photos": [
                {
                    "alt": "Pizza",
                    "photographer": "Pexels",
                    "url": "https://www.pexels.com/photo/pizza-1/",
                    "src": {
                        "large": "https://images.pexels.com/photos/pizza.jpeg",
                        "medium": "https://images.pexels.com/photos/pizza-small.jpeg",
                    },
                }
            ]
        }
        response.raise_for_status.return_value = None

        with (
            patch.object(announcement_svc, "pexels_api_key", return_value="api-key"),
            patch.object(announcement_svc.requests, "get", return_value=response) as requests_get,
            patch.object(announcement_svc, "fetch_thumbnail_bytes", side_effect=RuntimeError("thumbnail blocked")),
        ):
            results = announcement_svc.pexels_search("pizza", limit=1)

        self.assertEqual(requests_get.call_args.kwargs["params"]["orientation"], "landscape")
        self.assertEqual(requests_get.call_args.kwargs["params"]["size"], "large")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["thumb_url"], "https://images.pexels.com/photos/pizza-small.jpeg")
        self.assertNotIn("thumb_data", results[0])

    def test_pexels_search_can_skip_visual_filters(self):
        from services import announcement_svc

        response = Mock()
        response.json.return_value = {"photos": []}
        response.raise_for_status.return_value = None

        with (
            patch.object(announcement_svc, "pexels_api_key", return_value="api-key"),
            patch.object(announcement_svc.requests, "get", return_value=response) as requests_get,
        ):
            announcement_svc.pexels_search("tarte citron", limit=1, orientation="", size="")

        params = requests_get.call_args.kwargs["params"]
        self.assertEqual(params["query"], "tarte citron")
        self.assertNotIn("orientation", params)
        self.assertNotIn("size", params)

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

    def test_quick_menu_video_duration_is_locked_to_15_seconds(self):
        from services import menu_svc

        saved_configs = []

        def fake_ffmpeg(args, **_kwargs):
            Path(args[-1]).write_bytes(b"mp4")
            return Mock(returncode=0)

        with (
            patch.object(menu_svc, "suggest_images", return_value={"keywords": [], "suggestions": []}),
            patch.object(menu_svc, "load_config", return_value={"order": []}),
            patch.object(menu_svc, "save_config", side_effect=lambda cfg: saved_configs.append(cfg)),
            patch.object(menu_svc, "generate_standard_renditions"),
            patch.object(menu_svc, "log_activity"),
            patch.object(menu_svc.subprocess, "run", side_effect=fake_ffmpeg),
        ):
            filename = menu_svc.create_menu_from_text(
                "Menu verrouillé",
                sections={"starter": "salade", "main": "poulet", "dessert": "tarte"},
                duration=6,
                screens=["__default__"],
                username="admin",
            )

        cfg = saved_configs[-1]
        self.assertEqual(cfg["durations"][filename], 15)
        self.assertEqual(cfg["generated_menus"][filename]["duration"], 15)
        self.assertTrue(cfg["generated_menus"][filename]["duration_locked"])

    def test_menu_animation_spreads_three_sections_over_full_duration(self):
        from services import menu_svc

        total_frames = 15 * 8

        self.assertEqual(menu_svc._active_animation_section_index(0, total_frames, 3), 0)
        self.assertEqual(menu_svc._active_animation_section_index(39, total_frames, 3), 0)
        self.assertEqual(menu_svc._active_animation_section_index(40, total_frames, 3), 1)
        self.assertEqual(menu_svc._active_animation_section_index(79, total_frames, 3), 1)
        self.assertEqual(menu_svc._active_animation_section_index(80, total_frames, 3), 2)
        self.assertEqual(menu_svc._active_animation_section_index(119, total_frames, 3), 2)

    def test_menu_animation_spreads_items_inside_active_section(self):
        from services import menu_svc

        total_frames = 15 * 8

        self.assertEqual(menu_svc._active_animation_item_index(0, total_frames, 3, 3), 0)
        self.assertEqual(menu_svc._active_animation_item_index(13, total_frames, 3, 3), 0)
        self.assertEqual(menu_svc._active_animation_item_index(14, total_frames, 3, 3), 1)
        self.assertEqual(menu_svc._active_animation_item_index(27, total_frames, 3, 3), 1)
        self.assertEqual(menu_svc._active_animation_item_index(28, total_frames, 3, 3), 2)
        self.assertEqual(menu_svc._active_animation_item_index(39, total_frames, 3, 3), 2)

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
