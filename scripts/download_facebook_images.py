import argparse
import csv
import fcntl
import hashlib
import html
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlparse


DEFAULT_CSV = Path("data/data-facebook/typhoons_annotated.csv")
DEFAULT_OUTPUT = Path("images/facebook-typhoons")
DEFAULT_LABELS = ("mild", "moderate", "severe")
GALLERY_RETRY_SLEEP = "exp=5"
MAX_CONSECUTIVE_POST_PARSE_ERRORS = 3
ATTACHMENT_TYPE_FIELD = re.compile(r"^attachments/(\d+)/type$")
RETRYABLE_STATUSES = (
    "auth_required",
    "extractor_error",
    "invalid_image",
    "rate_limited",
    "unavailable",
)
MANIFEST_FIELDS = (
    "record_index",
    "attachment_index",
    "post_id",
    "typhoon",
    "image_annotation",
    "attachment_id",
    "fbid",
    "source_url",
    "post_url",
    "canonical_url",
    "status",
    "local_path",
    "attempts",
    "error",
    "byte_size",
    "width",
    "height",
    "image_format",
    "sha256",
)


@dataclass(frozen=True)
class PhotoReference:
    record_index: int
    attachment_index: int
    post_id: str
    typhoon: str
    label: str
    attachment_id: str
    source_url: str
    fbid: str | None
    parse_error: str | None
    post_url: str = ""

    @property
    def canonical_url(self) -> str | None:
        if not self.fbid:
            return None
        return f"https://www.facebook.com/photo/?fbid={self.fbid}"


@dataclass(frozen=True)
class ImageDetails:
    path: Path
    size: int
    width: int
    height: int
    image_format: str
    sha256: str


class PhotoUnavailableError(Exception):
    pass


class PostPageParseError(Exception):
    pass


class DataSJSParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.blobs = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "script" and any(
            name.lower() == "data-sjs" for name, _ in attrs
        ):
            self.current = []

    def handle_data(self, data):
        if self.current is not None:
            self.current.append(data)

    def handle_entityref(self, name):
        if self.current is not None:
            self.current.append(f"&{name};")

    def handle_charref(self, name):
        if self.current is not None:
            self.current.append(f"&#{name};")

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self.current is not None:
            self.blobs.append("".join(self.current))
            self.current = None


def parse_fbid(url: str) -> str | None:
    if not url:
        return None

    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if hostname != "facebook.com" and not hostname.endswith(".facebook.com"):
        return None

    normalized_path = parsed.path.rstrip("/")
    fbid = (parse_qs(parsed.query).get("fbid") or [""])[0]
    if normalized_path in ("/photo", "/photo.php") and fbid.isdigit():
        return fbid

    parts = [part for part in parsed.path.split("/") if part]
    if "photos" in parts and parts[-1].isdigit():
        return parts[-1]
    return None


def attachment_indices(fieldnames: list[str] | None) -> list[int]:
    indices = []
    for fieldname in fieldnames or []:
        match = ATTACHMENT_TYPE_FIELD.match(fieldname)
        if match:
            indices.append(int(match.group(1)))
    return sorted(indices)


def scan_csv(csv_path: Path, labels: set[str]) -> list[PhotoReference]:
    references = []
    with csv_path.open(newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        indices = attachment_indices(reader.fieldnames)
        if not indices:
            raise ValueError("CSV has no attachment type columns")

        for record_index, row in enumerate(reader, start=1):
            label = (
                row.get("image_annotated_flood_severity") or ""
            ).strip().lower()
            if label not in labels:
                continue

            for index in indices:
                prefix = f"attachments/{index}"
                attachment_type = (row.get(f"{prefix}/type") or "").strip()
                if attachment_type != "photo":
                    continue

                source_url = (row.get(f"{prefix}/url") or "").strip()
                attachment_id = (row.get(f"{prefix}/id") or "").strip()
                fbid = parse_fbid(source_url)
                parse_error = None

                if not fbid and attachment_id.isdigit():
                    fbid = attachment_id
                elif not fbid:
                    parse_error = "No exact numeric Facebook photo ID"

                references.append(
                    PhotoReference(
                        record_index=record_index,
                        attachment_index=index,
                        post_id=(row.get("postId") or "").strip(),
                        typhoon=(row.get("typhoon") or "").strip(),
                        label=label,
                        attachment_id=attachment_id,
                        source_url=source_url,
                        fbid=fbid,
                        parse_error=parse_error,
                        post_url=(row.get("url") or "").strip(),
                    )
                )
    return references


def unique_photo_count(references: list[PhotoReference]) -> int:
    return len({reference.fbid for reference in references if reference.fbid})


def connect_state(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS photos (
            fbid TEXT PRIMARY KEY,
            canonical_url TEXT NOT NULL,
            source_url TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            local_path TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            byte_size INTEGER,
            width INTEGER,
            height INTEGER,
            image_format TEXT,
            sha256 TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS photo_references (
            record_index INTEGER NOT NULL,
            attachment_index INTEGER NOT NULL,
            fbid TEXT REFERENCES photos(fbid),
            post_id TEXT NOT NULL,
            typhoon TEXT NOT NULL,
            label TEXT NOT NULL,
            attachment_id TEXT NOT NULL,
            source_url TEXT NOT NULL,
            post_url TEXT NOT NULL DEFAULT '',
            parse_error TEXT,
            PRIMARY KEY (record_index, attachment_index)
        );
        """
    )
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(photo_references)")
    }
    if "post_url" not in columns:
        connection.execute(
            "ALTER TABLE photo_references "
            "ADD COLUMN post_url TEXT NOT NULL DEFAULT ''"
        )
        connection.commit()
    return connection


def acquire_run_lock(output_dir: Path):
    lock_file = (output_dir / "run.lock").open("a+", encoding="utf-8")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        lock_file.close()
        raise RuntimeError(
            f"Another downloader is already using output directory: {output_dir}"
        ) from error

    lock_file.seek(0)
    lock_file.truncate()
    lock_file.write(f"pid={os.getpid()}\n")
    lock_file.flush()
    return lock_file


def sync_references(
    connection: sqlite3.Connection, references: list[PhotoReference]
) -> None:
    with connection:
        connection.execute("DELETE FROM photo_references")
        for reference in references:
            if reference.fbid and reference.canonical_url:
                connection.execute(
                    """
                    INSERT INTO photos (fbid, canonical_url, source_url)
                    VALUES (?, ?, ?)
                    ON CONFLICT(fbid) DO UPDATE SET
                        canonical_url = excluded.canonical_url,
                        source_url = CASE
                            WHEN photos.source_url = '' THEN excluded.source_url
                            ELSE photos.source_url
                        END
                    """,
                    (
                        reference.fbid,
                        reference.canonical_url,
                        reference.source_url,
                    ),
                )

            connection.execute(
                """
                INSERT INTO photo_references (
                    record_index, attachment_index, fbid, post_id, typhoon,
                    label, attachment_id, source_url, post_url, parse_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reference.record_index,
                    reference.attachment_index,
                    reference.fbid,
                    reference.post_id,
                    reference.typhoon,
                    reference.label,
                    reference.attachment_id,
                    reference.source_url,
                    reference.post_url,
                    reference.parse_error,
                ),
            )


def require_pillow() -> None:
    try:
        import PIL  # noqa: F401
    except ImportError as error:
        raise RuntimeError(
            "Pillow is required for image validation. "
            "Install dependencies with: pip install -r requirements.txt"
        ) from error


def validate_image(path: Path) -> ImageDetails:
    from PIL import Image

    if path.stat().st_size == 0:
        raise ValueError("Downloaded file is empty")

    with path.open("rb") as image_file:
        prefix = image_file.read(256).lstrip().lower()
        if prefix.startswith((b"<!doctype html", b"<html")):
            raise ValueError("Downloaded file contains HTML")

    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        image.load()
        width, height = image.size
        image_format = image.format or "unknown"

    digest = hashlib.sha256()
    with path.open("rb") as image_file:
        for chunk in iter(lambda: image_file.read(1024 * 1024), b""):
            digest.update(chunk)

    return ImageDetails(
        path=path,
        size=path.stat().st_size,
        width=width,
        height=height,
        image_format=image_format,
        sha256=digest.hexdigest(),
    )


def photo_files(files_dir: Path, fbid: str) -> list[Path]:
    return sorted(
        path
        for path in files_dir.glob(f"{fbid}.*")
        if path.is_file() and not path.name.endswith(".part")
    )


def quarantine_file(path: Path, invalid_dir: Path) -> Path:
    invalid_dir.mkdir(parents=True, exist_ok=True)
    destination = invalid_dir / path.name
    counter = 1
    while destination.exists():
        destination = invalid_dir / f"{path.stem}.{counter}{path.suffix}"
        counter += 1
    return Path(shutil.move(str(path), destination))


def reconcile_photos(
    connection: sqlite3.Connection,
    fbids: list[str],
    files_dir: Path,
    invalid_dir: Path,
) -> set[str]:
    downloaded = set()
    for fbid in fbids:
        paths = photo_files(files_dir, fbid)
        if not paths:
            row = connection.execute(
                "SELECT status FROM photos WHERE fbid = ?", (fbid,)
            ).fetchone()
            if row and row["status"] == "downloaded":
                with connection:
                    connection.execute(
                        """
                        UPDATE photos SET status = 'pending', local_path = NULL,
                            last_error = 'Downloaded file is missing',
                            byte_size = NULL, width = NULL, height = NULL,
                            image_format = NULL, sha256 = NULL,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE fbid = ?
                        """,
                        (fbid,),
                    )
            continue

        validation_errors = []
        for path in paths:
            try:
                details = validate_image(path)
            except Exception as error:
                quarantined = quarantine_file(path, invalid_dir)
                validation_errors.append(f"{quarantined.name}: {error}")
                continue

            with connection:
                connection.execute(
                    """
                    UPDATE photos SET
                        status = 'downloaded', local_path = ?, last_error = NULL,
                        byte_size = ?, width = ?, height = ?, image_format = ?,
                        sha256 = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE fbid = ?
                    """,
                    (
                        str(details.path),
                        details.size,
                        details.width,
                        details.height,
                        details.image_format,
                        details.sha256,
                        fbid,
                    ),
                )
            downloaded.add(fbid)
            break

        if fbid not in downloaded and validation_errors:
            with connection:
                connection.execute(
                    """
                    UPDATE photos SET status = 'invalid_image', local_path = NULL,
                        last_error = ?, byte_size = NULL, width = NULL,
                        height = NULL, image_format = NULL, sha256 = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE fbid = ?
                    """,
                    ("; ".join(validation_errors), fbid),
                )
    return downloaded


def parse_browser_specification(specification: str) -> tuple[str, ...]:
    browser, _, profile = specification.partition(":")
    browser, _, keyring = browser.partition("+")
    browser, _, domain = browser.partition("/")
    if profile.startswith(":"):
        container = profile[1:]
        profile = ""
    else:
        profile, _, container = profile.partition("::")
    return browser, profile, keyring, container, domain


def require_facebook_login(cookies) -> None:
    cookie_names = {cookie.name for cookie in cookies}
    missing = {"c_user", "xs"} - cookie_names
    if missing:
        raise RuntimeError(
            "The selected browser profile does not contain an authenticated "
            "Facebook session"
        )


def create_facebook_extractor(
    cookies_from_browser: str, sleep_request: str
):
    try:
        from gallery_dl import config
        from gallery_dl.extractor.facebook import FacebookPhotoExtractor
    except ImportError as error:
        raise RuntimeError(
            "gallery-dl is required. Install dependencies with: "
            "pip install -r requirements.txt"
        ) from error

    config.set((), "cookies", parse_browser_specification(cookies_from_browser))
    config.set((), "retries", 3)
    config.set((), "sleep-request", sleep_request)
    config.set((), "sleep-retries", GALLERY_RETRY_SLEEP)
    config.set((), "sleep-429", 300)

    extractor = FacebookPhotoExtractor.from_url(
        "https://www.facebook.com/photo/?fbid=1"
    )
    extractor.initialize()
    require_facebook_login(extractor.cookies)
    return extractor


def resolve_photo(extractor, fbid: str) -> tuple[str, str | None]:
    photo_url = f"https://www.facebook.com/photo/?fbid={fbid}&set="
    page = extractor.photo_page_request_wrapper(photo_url).text
    photo = extractor.parse_photo_page(page)
    media_url = photo.get("url")
    if not media_url:
        raise PhotoUnavailableError(
            "Facebook page no longer exposes a downloadable image"
        )

    resolved_id = photo.get("id")
    if resolved_id != fbid:
        raise ValueError(f"Facebook resolved unexpected photo ID {resolved_id}")
    return media_url, photo.get("extension")


def is_facebook_url(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return hostname == "facebook.com" or hostname.endswith(".facebook.com")


def is_facebook_photo_page_url(url: str) -> bool:
    return urlparse(url).path.rstrip("/").lower() in ("/photo", "/photo.php")


def count_consecutive_post_parse_errors(
    error: Exception,
    post_url: str,
    current_count: int,
    known_failure: bool = False,
) -> int:
    if not isinstance(error, PostPageParseError):
        return 0
    if known_failure or is_facebook_photo_page_url(post_url):
        return 0
    return current_count + 1


def is_facebook_media_url(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in ("fbcdn.net", "fbsbx.com")
    )


def image_candidates(value, priority: int):
    if isinstance(value, list):
        for nested in value:
            yield from image_candidates(nested, priority)
        return
    if not isinstance(value, dict):
        return

    uri = value.get("uri") or value.get("url")
    if isinstance(uri, str) and is_facebook_media_url(uri):
        width = value.get("width") or 0
        height = value.get("height") or 0
        area = width * height if isinstance(width, int) and isinstance(height, int) else 0
        yield area, priority, uri

    for nested in value.values():
        if isinstance(nested, (dict, list)):
            yield from image_candidates(nested, priority)


def extract_post_photo_urls(page: str, target_fbids: set[str]) -> dict[str, str]:
    matches: dict[str, tuple[int, int, str]] = {}
    parsed_blobs = 0

    def walk(value) -> None:
        if isinstance(value, dict):
            fbid = str(value.get("id") or "")
            is_photo = (
                value.get("__typename") == "Photo"
                or value.get("__isMedia") == "Photo"
            )
            if fbid in target_fbids and is_photo:
                candidates = []
                for priority, key in enumerate(
                    ("image", "photo_image", "preferred_thumbnail", "viewer_image")
                ):
                    candidates.extend(image_candidates(value.get(key), priority))
                if candidates:
                    candidate = max(candidates)
                    if candidate > matches.get(fbid, (-1, -1, "")):
                        matches[fbid] = candidate

            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    parser = DataSJSParser()
    parser.feed(page)
    raw_blobs = parser.blobs
    for raw_json in raw_blobs:
        try:
            value = json.loads(raw_json)
        except ValueError:
            try:
                value = json.loads(html.unescape(raw_json))
            except ValueError:
                continue
        parsed_blobs += 1
        walk(value)

    if not raw_blobs or not parsed_blobs:
        raise PostPageParseError(
            "Facebook post page did not contain readable structured data"
        )

    return {fbid: candidate[2] for fbid, candidate in matches.items()}


def fetch_post_photo_urls(
    extractor, post_url: str, target_fbids: set[str]
) -> dict[str, str]:
    if not is_facebook_url(post_url):
        raise ValueError(f"Unsupported Facebook post URL: {post_url}")

    response = extractor.request(post_url)
    response_text = response.text
    response_path = urlparse(response.url).path.lower()
    if response_path.startswith("/login") or any(
        marker in response_text
        for marker in (">You must log in to continue", 'id="login_form"')
    ):
        raise RuntimeError("You must be logged in to view this Facebook post")

    title_match = re.search(
        r"<title[^>]*>(.*?)</title>", response_text, re.IGNORECASE | re.DOTALL
    )
    title = (
        html.unescape(re.sub(r"<[^>]+>", "", title_match.group(1))).lower()
        if title_match
        else ""
    )
    if response_path.startswith("/checkpoint") or any(
        marker in title for marker in ("temporarily blocked", "too many requests")
    ):
        raise RuntimeError("Facebook temporarily blocked the post request")

    media_urls = extract_post_photo_urls(response_text, target_fbids)
    unresolved_mentions = {
        fbid for fbid in target_fbids - media_urls.keys() if fbid in response_text
    }
    if unresolved_mentions:
        raise PostPageParseError(
            "Facebook post contains target photo IDs but their media data "
            "could not be parsed"
        )
    if not media_urls:
        raise PostPageParseError(
            "Facebook post page did not expose any exact target photo media"
        )
    return media_urls


def image_extension(extension: str | None, content_type: str) -> str:
    extension = (extension or "").lower().lstrip(".")
    if re.fullmatch(r"[a-z0-9]{2,5}", extension):
        return "jpg" if extension == "jpeg" else extension

    content_type = content_type.partition(";")[0].strip().lower()
    return {
        "image/avif": "avif",
        "image/gif": "gif",
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }.get(content_type, "jpg")


def download_media(
    extractor,
    fbid: str,
    media_url: str,
    extension: str | None,
    files_dir: Path,
) -> Path:
    if not is_facebook_media_url(media_url):
        raise ValueError("Facebook returned an unsupported media URL")

    response = extractor.request(media_url, stream=True)
    content_type = response.headers.get("Content-Type", "")
    if content_type.lower().startswith("text/html"):
        response.close()
        raise ValueError("Facebook returned HTML instead of an image")

    extension = image_extension(extension, content_type)
    destination = files_dir / f"{fbid}.{extension}"
    temporary_path = files_dir / f"{fbid}.{extension}.part"
    try:
        with response, temporary_path.open("wb") as image_file:
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    image_file.write(chunk)
        os.replace(temporary_path, destination)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    return destination


def download_photo(extractor, fbid: str, files_dir: Path) -> Path:
    media_url, extension = resolve_photo(extractor, fbid)
    return download_media(extractor, fbid, media_url, extension, files_dir)


def classify_download_error(error: Exception) -> tuple[str, bool]:
    if isinstance(error, PhotoUnavailableError):
        return "unavailable", False

    name = error.__class__.__name__.lower()
    message = str(error).lower()
    if "auth" in name or "must be logged in" in message:
        return "auth_required", True
    if any(
        marker in message
        for marker in ("temporarily blocked", "too many requests", "429")
    ):
        return "rate_limited", True
    if "404 not found" in message:
        return "unavailable", False
    return "extractor_error", False


def log_event(log_path: Path, message: str) -> None:
    print(message)
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(f"{message}\n")


def pending_photos(
    connection: sqlite3.Connection, limit: int | None
) -> list[sqlite3.Row]:
    sql = """
        SELECT p.fbid, p.canonical_url
        FROM photos AS p
        JOIN (
            SELECT fbid, MIN(record_index) AS first_record
            FROM photo_references
            WHERE fbid IS NOT NULL
            GROUP BY fbid
        ) AS refs ON refs.fbid = p.fbid
        WHERE p.status IN ('pending', 'downloading')
        ORDER BY refs.first_record, p.fbid
    """
    parameters: tuple[int, ...] = ()
    if limit is not None:
        sql += " LIMIT ?"
        parameters = (limit,)
    return connection.execute(sql, parameters).fetchall()


def current_fbids(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        """
        SELECT DISTINCT fbid FROM photo_references
        WHERE fbid IS NOT NULL ORDER BY fbid
        """
    ).fetchall()
    return [row["fbid"] for row in rows]


def recovery_posts(
    connection: sqlite3.Connection,
    photo_limit: int | None,
    post_limit: int | None,
) -> list[tuple[str, list[str]]]:
    rows = connection.execute(
        """
        SELECT refs.post_url, refs.fbid
        FROM photo_references AS refs
        JOIN photos ON photos.fbid = refs.fbid
        WHERE photos.status NOT IN ('downloaded', 'pending')
          AND refs.post_url != ''
        ORDER BY refs.record_index, refs.attachment_index
        """
    ).fetchall()

    grouped: dict[str, list[str]] = {}
    queued_photos = 0
    for row in rows:
        fbid = row["fbid"]
        if photo_limit is not None and queued_photos >= photo_limit:
            break

        post_url = row["post_url"]
        if post_url not in grouped:
            if post_limit is not None and len(grouped) >= post_limit:
                break
            grouped[post_url] = []
        if fbid in grouped[post_url]:
            continue
        grouped[post_url].append(fbid)
        queued_photos += 1

    return list(grouped.items())


def retry_failures(connection: sqlite3.Connection) -> int:
    placeholders = ",".join("?" for _ in RETRYABLE_STATUSES)
    with connection:
        cursor = connection.execute(
            f"""
            UPDATE photos SET status = 'pending', last_error = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE status IN ({placeholders})
              AND fbid IN (
                  SELECT fbid FROM photo_references WHERE fbid IS NOT NULL
              )
            """,
            RETRYABLE_STATUSES,
        )
    return cursor.rowcount


def mark_photo_started(connection: sqlite3.Connection, fbid: str) -> None:
    with connection:
        connection.execute(
            """
            UPDATE photos SET status = 'downloading', attempts = attempts + 1,
                last_error = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE fbid = ?
            """,
            (fbid,),
        )


def mark_photo_failure(
    connection: sqlite3.Connection,
    fbid: str,
    status: str,
    error: Exception,
) -> None:
    with connection:
        connection.execute(
            """
            UPDATE photos SET status = ?, last_error = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE fbid = ?
            """,
            (status, str(error), fbid),
        )


def export_manifest(connection: sqlite3.Connection, manifest_path: Path) -> None:
    rows = connection.execute(
        """
        SELECT
            refs.record_index,
            refs.attachment_index,
            refs.post_id,
            refs.typhoon,
            refs.label AS image_annotation,
            refs.attachment_id,
            refs.fbid,
            refs.source_url,
            refs.post_url,
            photos.canonical_url,
            CASE
                WHEN refs.fbid IS NULL THEN 'unrecoverable_id'
                ELSE photos.status
            END AS status,
            photos.local_path,
            photos.attempts,
            COALESCE(refs.parse_error, photos.last_error) AS error,
            photos.byte_size,
            photos.width,
            photos.height,
            photos.image_format,
            photos.sha256
        FROM photo_references AS refs
        LEFT JOIN photos ON photos.fbid = refs.fbid
        ORDER BY refs.record_index, refs.attachment_index
        """
    ).fetchall()

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        newline="",
        encoding="utf-8",
        dir=manifest_path.parent,
        delete=False,
    ) as temporary_file:
        writer = csv.DictWriter(temporary_file, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(dict(row) for row in rows)
        temporary_path = Path(temporary_file.name)
    os.replace(temporary_path, manifest_path)


def print_summary(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        """
        SELECT status, COUNT(*) AS count
        FROM (
            SELECT DISTINCT photos.fbid, photos.status
            FROM photos
            JOIN photo_references ON photo_references.fbid = photos.fbid
        )
        GROUP BY status ORDER BY status
        """
    ).fetchall()
    unrecoverable = connection.execute(
        "SELECT COUNT(*) FROM photo_references WHERE fbid IS NULL"
    ).fetchone()[0]

    print("\nUnique photo status:")
    for row in rows:
        print(f"  {row['status']:<18} {row['count']}")
    if unrecoverable:
        print(f"  {'unrecoverable_id':<18} {unrecoverable}")


def failed_photo_count(connection: sqlite3.Connection) -> int:
    return connection.execute(
        """
        SELECT COUNT(*) FROM photos
        WHERE status NOT IN ('pending', 'downloading', 'downloaded')
          AND fbid IN (
              SELECT fbid FROM photo_references WHERE fbid IS NOT NULL
          )
        """
    ).fetchone()[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download flood-labeled Facebook photos from the annotated CSV."
    )
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--labels",
        nargs="+",
        default=list(DEFAULT_LABELS),
        help="Image annotations to include (default: mild moderate severe)",
    )
    parser.add_argument(
        "--cookies-from-browser",
        help="gallery-dl browser cookie specification, for example 'firefox'",
    )
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument(
        "--limit", type=int, help="Maximum unique photos to process this run"
    )
    parser.add_argument("--sleep-extractor", default="2.0-5.0")
    parser.add_argument("--sleep-request", default="1.0-2.0")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument(
        "--recover-from-posts",
        action="store_true",
        help="Retry failed photos using each row's Facebook post URL",
    )
    parser.add_argument(
        "--post-limit",
        type=int,
        help="Maximum post URLs to process during post recovery",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.batch_size < 1:
        raise ValueError("--batch-size must be at least 1")
    if args.limit is not None and args.limit < 1:
        raise ValueError("--limit must be at least 1")
    if args.post_limit is not None and args.post_limit < 1:
        raise ValueError("--post-limit must be at least 1")
    if args.retry_failed and args.recover_from_posts:
        raise ValueError("--retry-failed cannot be combined with --recover-from-posts")
    if not args.csv.is_file():
        raise ValueError(f"CSV file does not exist: {args.csv}")


def main() -> int:
    args = parse_args()
    try:
        validate_args(args)
        labels = {label.strip().lower() for label in args.labels}
        references = scan_csv(args.csv, labels)
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    unique_count = unique_photo_count(references)
    unrecoverable_count = sum(reference.fbid is None for reference in references)
    print(f"Selected attachment references: {len(references)}")
    print(f"Unique recoverable photos:      {unique_count}")
    print(f"Unrecoverable references:       {unrecoverable_count}")

    if args.dry_run:
        return 0
    if not args.cookies_from_browser:
        print("Error: --cookies-from-browser is required", file=sys.stderr)
        return 2

    try:
        require_pillow()
    except RuntimeError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    output_dir = args.output
    files_dir = output_dir / "files"
    invalid_dir = output_dir / "invalid"
    state_path = output_dir / "state.sqlite3"
    manifest_path = output_dir / "manifest.csv"
    log_path = output_dir / "gallery-dl.log"

    files_dir.mkdir(parents=True, exist_ok=True)
    try:
        run_lock = acquire_run_lock(output_dir)
    except RuntimeError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    try:
        connection = connect_state(state_path)
        sync_references(connection, references)
    except Exception:
        run_lock.close()
        raise

    try:
        extractor = create_facebook_extractor(
            args.cookies_from_browser, args.sleep_request
        )
        from gallery_dl import util as gallery_util

        photo_sleep = gallery_util.build_duration_func(args.sleep_extractor)
    except Exception as error:
        connection.close()
        run_lock.close()
        print(f"Error: {error}", file=sys.stderr)
        return 2

    print(f"Facebook cookies loaded:        {len(extractor.cookies)}")

    terminal_stop_reason = None
    consecutive_post_parse_errors = 0
    try:
        if args.retry_failed:
            print(f"Reset retryable failures:        {retry_failures(connection)}")

        all_fbids = current_fbids(connection)
        reconcile_photos(connection, all_fbids, files_dir, invalid_dir)
        if args.recover_from_posts:
            posts = recovery_posts(connection, args.limit, args.post_limit)
            recovery_count = sum(len(fbids) for _, fbids in posts)
            print(f"Post URLs queued for recovery:  {len(posts)}")
            print(f"Failed photos in those posts:   {recovery_count}")

            for start in range(0, len(posts), args.batch_size):
                batch = posts[start : start + args.batch_size]
                print(
                    f"\nRecovery batch {start // args.batch_size + 1}: "
                    f"posts {start + 1}-{start + len(batch)} of {len(posts)}"
                )

                for offset, (post_url, fbids) in enumerate(batch):
                    prior_statuses = {
                        fbid: connection.execute(
                            "SELECT status FROM photos WHERE fbid = ?", (fbid,)
                        ).fetchone()["status"]
                        for fbid in fbids
                    }
                    fbids = [
                        fbid
                        for fbid in fbids
                        if prior_statuses[fbid] != "downloaded"
                    ]
                    if not fbids:
                        continue
                    known_parse_failure = all(
                        prior_statuses[fbid] == "extractor_error"
                        for fbid in fbids
                    )

                    position = start + offset + 1
                    if photo_sleep:
                        extractor.sleep(photo_sleep(), "post")
                    log_event(
                        log_path,
                        f"[{position}/{len(posts)}] Recovering {len(fbids)} "
                        f"photo(s) from post {post_url}",
                    )

                    try:
                        media_urls = fetch_post_photo_urls(
                            extractor, post_url, set(fbids)
                        )
                    except Exception as error:
                        status, should_stop = classify_download_error(error)
                        if isinstance(error, PostPageParseError):
                            consecutive_post_parse_errors = (
                                count_consecutive_post_parse_errors(
                                    error,
                                    post_url,
                                    consecutive_post_parse_errors,
                                    known_parse_failure,
                                )
                            )
                            should_stop = (
                                consecutive_post_parse_errors
                                >= MAX_CONSECUTIVE_POST_PARSE_ERRORS
                            )
                        else:
                            consecutive_post_parse_errors = 0
                        for fbid in fbids:
                            mark_photo_started(connection, fbid)
                            mark_photo_failure(connection, fbid, status, error)
                        log_event(log_path, f"  {status}: {error}")
                        if should_stop:
                            terminal_stop_reason = status
                            break
                        continue

                    consecutive_post_parse_errors = 0

                    for fbid in fbids:
                        mark_photo_started(connection, fbid)
                        media_url = media_urls.get(fbid)
                        if not media_url:
                            error = PhotoUnavailableError(
                                "Facebook post does not expose this exact photo ID"
                            )
                            mark_photo_failure(
                                connection, fbid, "unavailable", error
                            )
                            log_event(log_path, f"  {fbid} unavailable")
                            continue

                        try:
                            path = download_media(
                                extractor, fbid, media_url, None, files_dir
                            )
                            downloaded = reconcile_photos(
                                connection, [fbid], files_dir, invalid_dir
                            )
                            if fbid in downloaded:
                                log_event(log_path, f"  Downloaded: {path}")
                            else:
                                log_event(
                                    log_path, f"  {fbid} failed image validation"
                                )
                        except Exception as error:
                            status, should_stop = classify_download_error(error)
                            mark_photo_failure(connection, fbid, status, error)
                            log_event(log_path, f"  {fbid} {status}: {error}")
                            if should_stop:
                                terminal_stop_reason = status
                                break

                    if terminal_stop_reason:
                        break

                export_manifest(connection, manifest_path)
                if terminal_stop_reason:
                    break
        else:
            queue = pending_photos(connection, args.limit)
            print(f"Photos queued for this run:      {len(queue)}")

            for start in range(0, len(queue), args.batch_size):
                batch = queue[start : start + args.batch_size]
                print(
                    f"\nBatch {start // args.batch_size + 1}: "
                    f"photos {start + 1}-{start + len(batch)} of {len(queue)}"
                )

                for offset, row in enumerate(batch):
                    fbid = row["fbid"]
                    position = start + offset + 1
                    if photo_sleep:
                        extractor.sleep(photo_sleep(), "photo")
                    log_event(
                        log_path, f"[{position}/{len(queue)}] Facebook photo {fbid}"
                    )
                    mark_photo_started(connection, fbid)

                    try:
                        path = download_photo(extractor, fbid, files_dir)
                        downloaded = reconcile_photos(
                            connection, [fbid], files_dir, invalid_dir
                        )
                        if fbid in downloaded:
                            log_event(log_path, f"  Downloaded: {path}")
                        else:
                            log_event(log_path, "  Failed image validation")
                    except Exception as error:
                        status, should_stop = classify_download_error(error)
                        mark_photo_failure(connection, fbid, status, error)
                        log_event(log_path, f"  {status}: {error}")
                        if should_stop:
                            terminal_stop_reason = status
                            break

                export_manifest(connection, manifest_path)
                if terminal_stop_reason:
                    break

        if terminal_stop_reason:
            retry_command = (
                "--recover-from-posts"
                if args.recover_from_posts
                else "--retry-failed"
            )
            print(
                f"Stopping after Facebook reported {terminal_stop_reason}. "
                f"Resolve it, then rerun with {retry_command}.",
                file=sys.stderr,
            )
    except KeyboardInterrupt:
        print("\nInterrupted. Progress has been preserved.", file=sys.stderr)
        return_code = 130
    else:
        failures = failed_photo_count(connection)
        if failures:
            print(f"Unresolved photo failures:       {failures}", file=sys.stderr)
        return_code = 1 if terminal_stop_reason or failures else 0
    finally:
        try:
            export_manifest(connection, manifest_path)
            print_summary(connection)
        finally:
            connection.close()
            run_lock.close()

    print(f"Manifest: {manifest_path}")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
