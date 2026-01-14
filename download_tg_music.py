import os
import re
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message
from tqdm import tqdm
import asyncio

load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHAT_ID = int(os.getenv("CHAT_ID"))
ROOT_DIR = os.getenv("DOWNLOAD_DIR")

os.makedirs(ROOT_DIR, exist_ok=True)

app = Client("my_session", api_id=API_ID, api_hash=API_HASH)

release = None
cover = None
cover_lock = asyncio.Lock()  # Блокировка для обложки


def get_caption(msg: Message):
    return msg.caption if msg.caption else (msg.text if msg.text else "")


def clean_label(raw: str) -> str:
    words_to_remove = {"records", "recordings"}
    parts = raw.split("_")
    parts = [p for p in parts if p.lower() not in words_to_remove]
    return " ".join(parts)


def parse_release(text: str) -> str:
    lines = text.splitlines()
    m = re.search(
        r"^(?P<artist>.+?)\s*-\s*(?P<album>.+?)(?P<ep>\s+EP)?\s*\[(?P<year>\d{4})\]",
        lines[0],
    )
    if not m:
        return None

    artist = m.group("artist").strip()
    album = m.group("album").strip()
    year = m.group("year")
    is_ep = bool(m.group("ep"))

    label = "Unknown"
    for line in lines:
        lm = re.search(r"^Label:\s*#([A-Za-z0-9_]+)", line)
        if lm:
            label = clean_label(lm.group(1))
            break

    ep_part = " EP" if is_ep else ""
    release = f"{artist} - {album} ({label}{ep_part} {year})"
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


@app.on_message(filters.chat(CHAT_ID))
async def handler(client: Client, message: Message):
    global release, cover

    text = get_caption(message)

    if message.photo and text:
        release = parse_release(text)
        cover = message
        print(f"✓ Detected album: {release}")
        return

    if message.audio:
        file_name = message.audio.file_name

        if not release or not cover:
            path = os.path.join(ROOT_DIR, file_name)
            await message.download(
                file_name=path, progress=lambda c, t: progress(c, t, file_name)
            )
            print(f"✓ Saved: {path}\n")
            return

        ext = file_name.split(".")[-1].upper()
        folder_name = f"{release} -{ext}-" if ext != "MP3" else release
        folder_path = os.path.join(ROOT_DIR, folder_name)
        os.makedirs(folder_path, exist_ok=True)

        # Блокировка для скачивания обложки
        cover_path = os.path.join(folder_path, "Cover.png")
        async with cover_lock:
            if not os.path.exists(cover_path):
                await cover.download(file_name=cover_path)
                print(f"✓ Cover saved")

        path = os.path.join(folder_path, file_name)
        await message.download(
            file_name=path, progress=lambda c, t: progress(c, t, file_name)
        )
        print(f"✓ Saved: {path}\n")


if __name__ == "__main__":
    print("Starting Pyrogram client...")
    print(f"Download directory: {ROOT_DIR}\n")
    app.run()
