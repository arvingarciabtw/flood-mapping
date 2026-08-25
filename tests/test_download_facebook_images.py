import csv
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from gallery_dl.util import build_duration_func_ex

from download_facebook_images import (
    GALLERY_RETRY_SLEEP,
    PostPageParseError,
    RETRYABLE_STATUSES,
    PhotoUnavailableError,
    PhotoReference,
    acquire_run_lock,
    classify_download_error,
    connect_state,
    count_consecutive_post_parse_errors,
    extract_post_photo_urls,
    export_manifest,
    fetch_post_photo_urls,
    image_extension,
    is_facebook_photo_page_url,
    parse_browser_specification,
    parse_fbid,
    reconcile_photos,
    recovery_posts,
    require_facebook_login,
    resolve_photo,
    scan_csv,
    sync_references,
    unique_photo_count,
    validate_image,
)


class FacebookImageDownloaderTests(unittest.TestCase):
    def test_parse_fbid_from_supported_url_forms(self):
        self.assertEqual(
            parse_fbid("https://www.facebook.com/photo.php?fbid=123&set=a.9"),
            "123",
        )
        self.assertEqual(
            parse_fbid("https://www.facebook.com/photo/?set=a.9&fbid=456"),
            "456",
        )
        self.assertEqual(
            parse_fbid("https://www.facebook.com/1/photos/gm.2/789/"), "789"
        )
        self.assertIsNone(parse_fbid("https://www.facebook.com/posts/example"))
        self.assertIsNone(parse_fbid("https://www.facebook.com/posts/123"))
        self.assertIsNone(parse_fbid("https://example.com/photo/?fbid=123"))

    def test_scan_filters_recovers_and_deduplicates_photos(self):
        fieldnames = [
            "attachments/0/id",
            "attachments/0/type",
            "attachments/0/url",
            "attachments/1/id",
            "attachments/1/type",
            "attachments/1/url",
            "postId",
            "postText",
            "typhoon",
            "image_annotated_flood_severity",
        ]
        rows = [
            {
                "attachments/0/id": "123",
                "attachments/0/type": "photo",
                "attachments/0/url": "https://www.facebook.com/photo.php?fbid=123",
                "attachments/1/id": "456",
                "attachments/1/type": "photo",
                "attachments/1/url": "",
                "postId": "post-1",
                "postText": "first line\nsecond line",
                "typhoon": "carina",
                "image_annotated_flood_severity": "mild",
            },
            {
                "attachments/0/id": "123",
                "attachments/0/type": "photo",
                "attachments/0/url": "https://www.facebook.com/photo/?fbid=123",
                "attachments/1/id": "5.85E+15",
                "attachments/1/type": "photo",
                "attachments/1/url": "",
                "postId": "post-2",
                "postText": "ignored",
                "typhoon": "egay",
                "image_annotated_flood_severity": "moderate",
            },
            {
                "attachments/0/id": "999",
                "attachments/0/type": "photo",
                "attachments/0/url": "https://www.facebook.com/photo/?fbid=999",
                "postId": "post-3",
                "typhoon": "egay",
                "image_annotated_flood_severity": "irrelevant",
            },
        ]

        with tempfile.TemporaryDirectory() as temporary_dir:
            csv_path = Path(temporary_dir) / "input.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

            references = scan_csv(csv_path, {"mild", "moderate", "severe"})

        self.assertEqual(len(references), 4)
        self.assertEqual(unique_photo_count(references), 2)
        self.assertEqual(references[1].fbid, "456")
        self.assertIsNone(references[3].fbid)
        self.assertIn("exact numeric", references[3].parse_error)

    def test_sync_preserves_download_state(self):
        reference = PhotoReference(
            record_index=1,
            attachment_index=0,
            post_id="post",
            typhoon="carina",
            label="mild",
            attachment_id="123",
            source_url="https://www.facebook.com/photo/?fbid=123",
            fbid="123",
            parse_error=None,
        )
        with tempfile.TemporaryDirectory() as temporary_dir:
            state_path = Path(temporary_dir) / "state.sqlite3"
            connection = connect_state(state_path)
            sync_references(connection, [reference])
            connection.execute(
                "UPDATE photos SET status = 'downloaded' WHERE fbid = '123'"
            )
            connection.commit()

            sync_references(connection, [reference])
            status = connection.execute(
                "SELECT status FROM photos WHERE fbid = '123'"
            ).fetchone()["status"]
            connection.close()

        self.assertEqual(status, "downloaded")

    def test_recovery_posts_groups_failed_photos_by_post(self):
        references = [
            PhotoReference(
                record_index=index,
                attachment_index=0,
                post_id=f"post-{post}",
                typhoon="carina",
                label="mild",
                attachment_id=fbid,
                source_url=f"https://www.facebook.com/photo/?fbid={fbid}",
                fbid=fbid,
                parse_error=None,
                post_url=f"https://www.facebook.com/page/posts/{post}",
            )
            for index, (fbid, post) in enumerate(
                (("1", "a"), ("2", "a"), ("3", "b"), ("1", "c")), start=1
            )
        ]
        with tempfile.TemporaryDirectory() as temporary_dir:
            connection = connect_state(Path(temporary_dir) / "state.sqlite3")
            sync_references(connection, references)
            connection.execute(
                "UPDATE photos SET status = 'unavailable' WHERE fbid != '3'"
            )
            connection.execute(
                "UPDATE photos SET status = 'downloaded' WHERE fbid = '3'"
            )
            connection.commit()

            posts = recovery_posts(connection, None, None)
            connection.close()

        self.assertEqual(
            posts,
            [
                ("https://www.facebook.com/page/posts/a", ["1", "2"]),
                ("https://www.facebook.com/page/posts/c", ["1"]),
            ],
        )

    def test_existing_state_gets_post_url_column(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            state_path = Path(temporary_dir) / "state.sqlite3"
            connection = sqlite3.connect(state_path)
            connection.execute(
                """
                CREATE TABLE photo_references (
                    record_index INTEGER NOT NULL,
                    attachment_index INTEGER NOT NULL,
                    fbid TEXT,
                    post_id TEXT NOT NULL,
                    typhoon TEXT NOT NULL,
                    label TEXT NOT NULL,
                    attachment_id TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    parse_error TEXT,
                    PRIMARY KEY (record_index, attachment_index)
                )
                """
            )
            connection.commit()
            connection.close()

            connection = connect_state(state_path)
            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(photo_references)"
                )
            }
            connection.close()

        self.assertIn("post_url", columns)

    def test_validate_and_reconcile_image(self):
        reference = PhotoReference(
            record_index=1,
            attachment_index=0,
            post_id="post",
            typhoon="carina",
            label="severe",
            attachment_id="123",
            source_url="https://www.facebook.com/photo/?fbid=123",
            fbid="123",
            parse_error=None,
        )
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            files_dir = root / "files"
            files_dir.mkdir()
            image_path = files_dir / "123.png"
            Image.new("RGB", (12, 8), "blue").save(image_path)

            details = validate_image(image_path)
            self.assertEqual((details.width, details.height), (12, 8))
            self.assertEqual(details.image_format, "PNG")

            connection = connect_state(root / "state.sqlite3")
            sync_references(connection, [reference])
            downloaded = reconcile_photos(
                connection, ["123"], files_dir, root / "invalid"
            )
            row = connection.execute(
                "SELECT * FROM photos WHERE fbid = '123'"
            ).fetchone()
            connection.close()

        self.assertEqual(downloaded, {"123"})
        self.assertEqual(row["status"], "downloaded")
        self.assertEqual(row["width"], 12)
        self.assertEqual(len(row["sha256"]), 64)

    def test_validation_rejects_truncated_image(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            image_path = Path(temporary_dir) / "truncated.jpg"
            Image.new("RGB", (100, 100), "blue").save(image_path)
            data = image_path.read_bytes()
            image_path.write_bytes(data[: len(data) // 2])

            with self.assertRaises(Exception):
                validate_image(image_path)

    def test_gallery_retry_delay_uses_valid_syntax(self):
        delay = build_duration_func_ex(GALLERY_RETRY_SLEEP)

        self.assertEqual(delay(1), 5)
        self.assertEqual(delay(2), 10)

    def test_parse_zen_browser_specification(self):
        self.assertEqual(
            parse_browser_specification("zen"), ("zen", "", "", "", "")
        )
        self.assertEqual(
            parse_browser_specification("zen:research::all"),
            ("zen", "research", "", "all", ""),
        )

    def test_resolve_photo_does_not_request_album_metadata(self):
        class FakePage:
            text = "photo page"

        class FakeExtractor:
            def photo_page_request_wrapper(self, url):
                self.requested_url = url
                return FakePage()

            def parse_photo_page(self, page):
                return {
                    "id": "123",
                    "url": "https://scontent.example/image.jpg",
                    "extension": "jpg",
                }

        extractor = FakeExtractor()
        media_url, extension = resolve_photo(extractor, "123")

        self.assertEqual(media_url, "https://scontent.example/image.jpg")
        self.assertEqual(extension, "jpg")
        self.assertEqual(
            extractor.requested_url,
            "https://www.facebook.com/photo/?fbid=123&set=",
        )

    def test_missing_media_url_is_unavailable(self):
        class FakePage:
            text = "photo page"

        class FakeExtractor:
            def photo_page_request_wrapper(self, url):
                return FakePage()

            def parse_photo_page(self, page):
                return {"id": "", "url": "", "extension": ""}

        with self.assertRaises(PhotoUnavailableError):
            resolve_photo(FakeExtractor(), "123")

        status, should_stop = classify_download_error(
            PhotoUnavailableError("missing")
        )
        self.assertEqual(status, "unavailable")
        self.assertFalse(should_stop)
        self.assertIn("unavailable", RETRYABLE_STATUSES)

    def test_media_url_requires_exact_resolved_id(self):
        class FakePage:
            text = "photo page"

        class FakeExtractor:
            def photo_page_request_wrapper(self, url):
                return FakePage()

            def parse_photo_page(self, page):
                return {
                    "id": "",
                    "url": "https://scontent.example/image.jpg",
                    "extension": "jpg",
                }

        with self.assertRaisesRegex(ValueError, "unexpected photo ID"):
            resolve_photo(FakeExtractor(), "123")

    def test_authenticated_facebook_cookies_are_required(self):
        require_facebook_login(
            [SimpleNamespace(name="c_user"), SimpleNamespace(name="xs")]
        )
        with self.assertRaisesRegex(RuntimeError, "authenticated Facebook"):
            require_facebook_login([SimpleNamespace(name="locale")])

    def test_image_extension_prefers_facebook_metadata(self):
        self.assertEqual(image_extension("jpeg", "image/jpeg"), "jpg")
        self.assertEqual(image_extension(None, "image/webp"), "webp")

    def test_extract_post_photos_matches_exact_ids_and_largest_image(self):
        payload = {
            "attachments": [
                {
                    "media": {
                        "__typename": "Photo",
                        "__isMedia": "Photo",
                        "id": "123",
                        "image": {
                            "width": 400,
                            "height": 300,
                            "uri": "https://scontent.example.fbcdn.net/small.jpg",
                        },
                        "viewer_image": {
                            "width": 1600,
                            "height": 1200,
                            "uri": "https://scontent.example.fbcdn.net/large.jpg",
                        },
                    }
                },
                {
                    "media": {
                        "__typename": "Photo",
                        "id": "999",
                        "viewer_image": {
                            "uri": "https://scontent.example.fbcdn.net/other.jpg"
                        },
                    }
                },
            ]
        }
        page = (
            f'<script data-sjs="1" type="application/json">'
            f"{json.dumps(payload)}</script>"
        )

        photos = extract_post_photo_urls(page, {"123"})

        self.assertEqual(
            photos, {"123": "https://scontent.example.fbcdn.net/large.jpg"}
        )

    def test_post_parser_rejects_missing_structured_data(self):
        with self.assertRaises(PostPageParseError):
            extract_post_photo_urls("<html>checkpoint</html>", {"123"})

        invalid_attribute = (
            '<script data-sjs-extra="1" type="application/json">'
            '{"id":"123"}</script>'
        )
        with self.assertRaises(PostPageParseError):
            extract_post_photo_urls(invalid_attribute, {"123"})

    def test_post_fetch_requires_an_exact_target_match(self):
        class FakeResponse:
            url = "https://www.facebook.com/page/posts/1"
            text = (
                '<script data-sjs type="application/json">'
                '{"unrelated":true}</script>'
            )

        class FakeExtractor:
            def request(self, url):
                return FakeResponse()

        with self.assertRaisesRegex(PostPageParseError, "exact target"):
            fetch_post_photo_urls(
                FakeExtractor(),
                "https://www.facebook.com/page/posts/1",
                {"123"},
            )

    def test_post_fetch_ignores_generic_challenge_strings(self):
        payload = {
            "media": {
                "__typename": "Photo",
                "id": "123",
                "viewer_image": {
                    "width": 800,
                    "height": 600,
                    "uri": "https://scontent.example.fbcdn.net/image.jpg",
                },
            },
            "modules": ["checkpoint", "CometErrorRoot.react"],
        }

        class FakeResponse:
            url = "https://www.facebook.com/page/posts/1"
            text = (
                '<script data-sjs type="application/json">'
                f"{json.dumps(payload)}</script>"
            )

        class FakeExtractor:
            def request(self, url):
                return FakeResponse()

        photos = fetch_post_photo_urls(
            FakeExtractor(),
            "https://www.facebook.com/page/posts/1",
            {"123"},
        )

        self.assertEqual(
            photos, {"123": "https://scontent.example.fbcdn.net/image.jpg"}
        )

    def test_post_fetch_detects_checkpoint_redirect(self):
        class FakeResponse:
            url = "https://www.facebook.com/checkpoint/blocked"
            text = "<html><title>Facebook</title></html>"

        class FakeExtractor:
            def request(self, url):
                return FakeResponse()

        with self.assertRaisesRegex(RuntimeError, "temporarily blocked"):
            fetch_post_photo_urls(
                FakeExtractor(),
                "https://www.facebook.com/page/posts/1",
                {"123"},
            )

    def test_direct_photo_parse_errors_do_not_trip_post_breaker(self):
        error = PostPageParseError("missing media")
        post_url = "https://www.facebook.com/page/posts/1"
        photo_url = "https://www.facebook.com/photo.php?fbid=123&set=a.1"

        count = count_consecutive_post_parse_errors(error, post_url, 0)
        self.assertEqual(count, 1)
        self.assertTrue(is_facebook_photo_page_url(photo_url))
        count = count_consecutive_post_parse_errors(error, photo_url, count)
        self.assertEqual(count, 0)
        count = count_consecutive_post_parse_errors(error, post_url, count)
        self.assertEqual(count, 1)

    def test_known_parse_failure_resets_post_breaker(self):
        count = count_consecutive_post_parse_errors(
            PostPageParseError("known failure"),
            "https://www.facebook.com/page/posts/1",
            2,
            known_failure=True,
        )
        self.assertEqual(count, 0)

    def test_non_parse_error_resets_post_parse_error_count(self):
        count = count_consecutive_post_parse_errors(
            ValueError("ordinary error"),
            "https://www.facebook.com/page/posts/1",
            2,
        )
        self.assertEqual(count, 0)

    def test_output_lock_prevents_concurrent_runs(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            output_dir = Path(temporary_dir)
            first_lock = acquire_run_lock(output_dir)
            try:
                with self.assertRaisesRegex(RuntimeError, "already using"):
                    acquire_run_lock(output_dir)
            finally:
                first_lock.close()

    def test_empty_manifest_has_stable_columns(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            connection = connect_state(root / "state.sqlite3")
            export_manifest(connection, root / "manifest.csv")
            connection.close()

            with (root / "manifest.csv").open(newline="", encoding="utf-8") as file:
                header = next(csv.reader(file))

        self.assertIn("fbid", header)
        self.assertIn("post_url", header)
        self.assertIn("image_annotation", header)
        self.assertIn("sha256", header)


if __name__ == "__main__":
    unittest.main()
