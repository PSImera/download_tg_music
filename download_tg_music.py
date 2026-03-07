import os
import re
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message
from tqdm import tqdm
import asyncio

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
ROOT_DIR = os.getenv("DOWNLOAD_DIR")
KNOWN_SOURCES = {"radio_boga", "psymusicru"}

os.makedirs(ROOT_DIR, exist_ok=True)

app = Client("my_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

release = None
cover_msg = None
cover_bandcamp_url = None
current_source = None
cover_lock = asyncio.Lock()


def clean_label(raw: str, spaced: bool = False) -> str:
    words_to_remove = {"records", "recordings"}
    if spaced:
        parts = raw.split()
    else:
        parts = raw.split("_")
    parts = [p for p in parts if p.lower() not in words_to_remove]
    return " ".join(parts)


def parse_release(text: str, source: str | None) -> str:
    if source == "psymusicru":
        return parse_release_psymusicru(text)
    elif source == "radio_boga":
        return parse_release_radio_boga(text)


def parse_release_radio_boga(text: str) -> str:
    lines = text.splitlines()
    m = re.search(
        r"^(?P<artist>.+?)\s*-\s*(?P<album>.+?)(?P<ep>\s+EP)?\s*\[(?P<year>\d{4})\]",
        lines[0],
    )
    if not m:
        return None

    artist = m.group("artist").strip()
    if artist == "V.A":
        artist = "VA"

    album = m.group("album").strip()
    album = re.sub(
        r"\(Compiled[^)]*\)", "", album
    ).strip()  # удалить (Compiled ...) из названия альбома

    year = m.group("year")
    is_ep = bool(m.group("ep"))

    label = None
    for line in lines:
        lm = re.search(r"^Label:\s*#([A-Za-z0-9_]+)", line)
        if lm:
            label = clean_label(lm.group(1))
            break

    if is_ep:
        label = f"{label} EP" if label else "EP"

    if label:
        release = f"{artist} - {album} ({label} {year})"
    else:
        release = f"{artist} - {album} ({year})"

    return re.sub(r'[\\/*?:"<>|]', "", release).strip()


def parse_release_psymusicru(text: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    title_line = None
    for line in lines:
        if re.search(r".+\s*-\s*.+\d{4}", line) and not line.startswith("#"):
            title_line = line
            break

    if not title_line:
        return None

    m = re.search(
        r"^(?P<artist>.+?)\s*-\s*(?P<album>.+?)(?:\s+EP)?\s+(?P<year>\d{4})\s*$",
        title_line,
    )
    if not m:
        return None

    artist = m.group("artist").strip()
    if artist in ("V.A", "V.A."):
        artist = "VA"

    album = m.group("album").strip()
    year = m.group("year")
    is_ep = bool(re.search(r"\bEP\b", title_line))

    label = None
    for line in lines:
        lm = re.search(r"\(([^)]+)\)", line)
        if lm:
            raw_label = lm.group(1).strip()
            if re.search(r"[A-Za-z]", raw_label):
                label = clean_label(raw_label, spaced=True)
                break

    if is_ep:
        label = f"{label} EP" if label else "EP"

    if label:
        release = f"{artist} - {album} ({label} {year})"
    else:
        release = f"{artist} - {album} ({year})"

    return re.sub(r'[\\/*?:"<>|]', "", release).strip()


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


@app.on_message(filters.private)
async def handler(client: Client, message: Message):
    global release, cover_msg

    if message.forward_from_chat:
        source = message.forward_from_chat.username
    else:
        source = None

    text = (
        message.caption if message.caption else (message.text if message.text else "")
    )

    if text:
        if source == "psymusicru":
            release = parse_release_psymusicru(text)
        elif source == "radio_boga":
            release = parse_release_radio_boga(text)
        else:
            release = f"_RELEASE[{message.id}]"

        cover_msg = message
        print(f"✓ Detected album: {release} [source: {source}]")
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

        # определяем формат и создаём папку
        ext = file_name.split(".")[-1].upper()
        folder_name = f"{release} -{ext}-" if ext != "MP3" else release
        folder_path = os.path.join(ROOT_DIR, folder_name)
        os.makedirs(folder_path, exist_ok=True)

        # сохранение обложки
        if cover_msg.photo:
            cover_path = os.path.join(folder_path, "Cover.png")
            async with cover_lock:
                if not os.path.exists(cover_path):
                    await cover_msg.download(file_name=cover_path)
                    print(f"✓ Cover saved")

        # сохраняем аудио
        path = os.path.join(folder_path, file_name)
        await message.download(
            file_name=path, progress=lambda c, t: progress(c, t, file_name)
        )
        print(f"✓ Saved: {path}\n")


if __name__ == "__main__":
    print("Starting Pyrogram client...")
    print(f"Download directory: {ROOT_DIR}\n")
    app.run()
