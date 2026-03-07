import os
import re
import yaml
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message
from tqdm import tqdm
import asyncio
import aiohttp

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

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

release = None
cover_msg = None
bandcamp_url = None
current_source = None
cover_lock = asyncio.Lock()


def progress(current, total, file_name):
    if not hasattr(progress, "pbars"):
        progress.pbars = {}

    if file_name not in progress.pbars:
        progress.pbars[file_name] = tqdm(
            total=total,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc=file_name[:50],
        )

    pbar = progress.pbars[file_name]
    pbar.n = current
    pbar.refresh()

    if current >= total:
        pbar.close()
        del progress.pbars[file_name]


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


async def download_bandcamp_cover(url: str, dest_path: str) -> bool:
    """Download cover image from a Bandcamp album page."""
    print("  Fetching Bandcamp cover...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text()
        m = re.search(r'<meta property="og:image"\s+content="([^"]+)"', html)
        if not m:
            m = re.search(r'<meta content="([^"]+)"\s+property="og:image"', html)
        img_url = m.group(1) if m else None

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


def parse_metadata(text: str, release_rattern, label_pattern) -> dict:

    result = DEFAULT_METADATA.copy()
    lines = [l.strip() for l in text.splitlines()]

    release_found = False
    label_found = False

    for line in lines:

        #  search for release pattern
        if not release_found:
            m = release_rattern.search(line)
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

    artist = metadata.get("artist").strip()
    if artist == "V.A":
        artist = "VA"

    album = metadata.get("album")
    album = re.sub(r"\(Compiled[^)]*\)", "", album).strip()

    year = metadata.get("year")

    label = metadata.get("label")
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
    global release, cover_msg, bandcamp_url

    if message.forward_from_chat:
        source = message.forward_from_chat.username
    else:
        source = None

    source_cfg = SOURCES.get(source)

    text = (
        message.caption if message.caption else (message.text if message.text else "")
    )

    if text:
        if source in SOURCES:
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

        cover_msg = message
        bandcamp_url = extract_bandcamp_url(text)

        print(f"✓ Detected album: {release} [source: {source}]")
        if bandcamp_url:
            print(f"  Bandcamp URL: {bandcamp_url}")
        return

    if message.audio:
        file_name = message.audio.file_name

        if not release:
            path = os.path.join(ROOT_DIR, file_name)
            await message.download(
                file_name=path, progress=lambda c, t: progress(c, t, file_name)
            )
            print(f"✓ Saved: {path}\n")
            return

        # Determine format and create folder
        ext = file_name.split(".")[-1].upper()
        folder_name = f"{release} -{ext}-" if ext != "MP3" else release
        folder_path = os.path.join(ROOT_DIR, folder_name)
        os.makedirs(folder_path, exist_ok=True)

        # Save cover (Bandcamp preferred, fallback to Telegram photo)
        cover_path = os.path.join(folder_path, "Cover.png")
        async with cover_lock:
            if not os.path.exists(cover_path):
                if cover_msg.photo:
                    await cover_msg.download(file_name=cover_path)
                    print(f"✓ Telegram cover saved")
                elif bandcamp_url:
                    await download_bandcamp_cover(bandcamp_url, cover_path)
                    print(f"✓ Bandcamp cover saved")

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
