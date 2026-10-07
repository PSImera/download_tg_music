import os
import re
import yaml
from dotenv import load_dotenv
from pyrogram.client import Client
from pyrogram import filters
from pyrogram.types import Message
from tqdm import tqdm
import asyncio
import aiohttp
from dataclasses import dataclass

load_dotenv()

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]

with open("config.yaml", "r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

ROOT_DIR = CONFIG["download_dir"]
os.makedirs(ROOT_DIR, exist_ok=True)

DEFAULT_METADATA = CONFIG["default_metadata"]
BANDCAMP_PATTERN = re.compile(CONFIG["bandcamp_pattern"])
SOURCES = {}
for name, cfg in CONFIG["sources"].items():
    SOURCES[name] = {
        "release_pattern": re.compile(cfg["release_pattern"]),
        "label_pattern": re.compile(cfg["label_pattern"]),
        "label_underline": cfg["label_underline"],
    }

app = Client("my_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@dataclass(frozen=True)
class AlbumContext:
    release: str
    cover_msg: Message | None
    bandcamp_url: str | None

current_album: AlbumContext | None = None
_cover_locks: dict[str, asyncio.Lock] = {}
_pbars: dict[str, tqdm] = {}


def progress(current: int, total: int, file_name: str) -> None:
    if file_name not in _pbars:
        _pbars[file_name] = tqdm(
            total=total,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc=file_name[:50],
        )

    pbar = _pbars[file_name]
    pbar.n = current
    pbar.refresh()

    if current >= total:
        pbar.close()
        del _pbars[file_name]


def preprocess_label(raw: str, underline: bool = False) -> str:
    words_to_remove = {"records", "recordings", "productions"}
    if underline:
        parts = raw.split("_")
    else:
        parts = raw.split()
    parts = [p for p in parts if p.lower() not in words_to_remove]
    return " ".join(parts)


def extract_bandcamp_url(text: str) -> str | None:
    m = re.search(r"https?://[^\s]+\.bandcamp\.com/[^\s]+", text)
    return m.group(0) if m else None


async def ensure_cover(album: AlbumContext, folder_name: str, cover_path: str) -> None:
    """Saving cover: Telegram post first, Bandcamp as fallback"""
    lock = _cover_locks.setdefault(cover_path, asyncio.Lock())
    async with lock:
        if os.path.exists(cover_path):
            return

        # Telegram
        if album.cover_msg is not None and album.cover_msg.photo:
            try:
                await album.cover_msg.download(file_name=cover_path)
                print(f"✓ Telegram cover saved: {folder_name}")
                return
            except Exception as e:
                print(f"⚠ Could not download Telegram cover for {folder_name}: {e}")

        # Bandcamp
        if album.bandcamp_url:
            print(f"  No Telegram cover for {folder_name}, trying Bandcamp: {album.bandcamp_url}")
            if await download_bandcamp_cover(album.bandcamp_url, cover_path):
                print(f"✓ Bandcamp cover saved: {folder_name}")
            else:
                print(f"⚠ Bandcamp cover not saved: {folder_name}")


async def download_bandcamp_cover(url: str, dest_path: str) -> bool:
    """Download cover image from a Bandcamp album page."""
    print("  Fetching Bandcamp cover...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    return False
                html = await resp.text()
        m = re.search(r'<meta property="og:image"\s+content="([^"]+)"', html)
        if not m:
            m = re.search(r'<meta content="([^"]+)"\s+property="og:image"', html)
        img_url = m.group(1) if m else None
        if img_url is None:
            return False

        img_url = re.sub(r"_\d+\.jpg", "_0.jpg", img_url)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    img_url, timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        return False
                    data = await resp.read()
            with open(dest_path, "wb") as f:
                f.write(data)
            return True
        except Exception as e:
            print(f"⚠ Could not download Bandcamp cover: {e}")
            return False

    except Exception as e:
        print(f"⚠ Could not fetch Bandcamp cover: {e}")
        return False


def parse_metadata(text: str, release_pattern, label_pattern) -> dict:

    result = DEFAULT_METADATA.copy()
    lines = [l.strip() for l in text.splitlines()]

    release_found = False
    label_found = False

    for line in lines:

        #  search for release pattern
        if not release_found:
            m = release_pattern.search(line)
            if not m:
                continue

            result["artist"] = m.group("artist")
            result["album"] = m.group("album")
            result["year"] = m.group("year")
            result["is_ep"] = m.group("ep")

            release_found = True
            continue

        # search for label pattern
        if release_found and not label_found:
            m = label_pattern.match(line)
            if m:
                result["label"] = m.group(1)
                label_found = True
            continue

        # search for bandcamp link
        if label_found:
            m = BANDCAMP_PATTERN.search(line)
            if m:
                result["bandcamp_link"] = m.group(0)
                break

    return result


def format_release_name(metadata: dict, label_underline: bool = False) -> str:

    artist = (metadata.get("artist") or "").strip()
    if artist == "V.A":
        artist = "VA"

    album = re.sub(r"\(Compiled[^)]*\)", "", metadata.get("album") or "").strip()

    year = metadata.get("year")

    label = metadata.get("label") or ""
    words_to_remove = {"records", "recordings", "productions"}
    if label_underline:
        parts = label.split("_")
    else:
        parts = label.split()
    parts = [p for p in parts if p.lower() not in words_to_remove]
    label = " ".join(parts)

    is_ep = bool(metadata.get("is_ep"))
    if is_ep:
        label = f"{label} EP" if label else "EP"

    if label:
        release = f"{artist} - {album} ({label} {year})"
    else:
        release = f"{artist} - {album} ({year})"

    return re.sub(r'[\\/*?:"<>|]', "", release).strip()


@app.on_message(filters.private)
async def handler(client: Client, message: Message):
    global current_album
    album = current_album

    if message.forward_from_chat:
        source = message.forward_from_chat.username
    else:
        source = None

    text = (
        message.caption if message.caption else (message.text if message.text else "")
    )

    if text:
        if source in SOURCES:
            source_cfg = SOURCES[source]
            metadata = parse_metadata(
                text, source_cfg["release_pattern"], source_cfg["label_pattern"]
            )
            release = format_release_name(
                metadata, label_underline=source_cfg["label_underline"]
            )
        else:
            metadata = DEFAULT_METADATA.copy()
            metadata["album"] = f"_RELEASE[{message.id}]"
            release = format_release_name(metadata)

        bandcamp_url = extract_bandcamp_url(text)

        current_album = AlbumContext(
            release=release,
            cover_msg=message,
            bandcamp_url=bandcamp_url,
        )

        print(f"✓ Detected album: {release} [source: {source}]")
        return

    if message.audio:
        file_name = message.audio.file_name

        if album is None:
            path = os.path.join(ROOT_DIR, file_name)
            await message.download(
                file_name=path, progress=lambda c, t: progress(c, t, file_name)
            )
            print(f"✓ Saved: {path}\n")
            return

        # Determine format and create folder
        ext = file_name.split(".")[-1].upper()
        folder_name = f"{album.release} -{ext}-" if ext != "MP3" else album.release
        folder_path = os.path.join(ROOT_DIR, folder_name)
        os.makedirs(folder_path, exist_ok=True)

        # Save cover
        await ensure_cover(album, folder_name, os.path.join(folder_path, "Cover.png"))

        # Save audio
        path = os.path.join(folder_path, file_name)
        await message.download(
            file_name=path, progress=lambda c, t: progress(c, t, file_name)
        )
        print(f"✓ Saved: {path}\n")


if __name__ == "__main__":
    print("Starting Pyrogram client...")
    print(f"Download directory: {ROOT_DIR}\n")
    app.run()
