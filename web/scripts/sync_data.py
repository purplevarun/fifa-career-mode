import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "web" / "public"
sys.path.insert(0, str(ROOT))


def main():
    from career_data.database import connect
    from career_data.pipeline import export_data

    connection = connect(ROOT / "data" / "career.sqlite")
    try:
        export_data(connection, PUBLIC / "data" / "career.json")
    finally:
        connection.close()
    data = json.loads((PUBLIC / "data" / "career.json").read_text(encoding="utf-8"))
    image_directory = PUBLIC / "evidence"
    image_directory.mkdir(parents=True, exist_ok=True)

    def preview(source):
        original = (ROOT / source["path"]).resolve()
        if not original.is_relative_to(ROOT / "raw_data") or not original.is_file():
            return 0
        destination = image_directory / f"{source['id']}.webp"
        if destination.exists() and destination.stat().st_mtime >= original.stat().st_mtime:
            return 0
        with Image.open(original) as image:
            image.convert("RGB").save(destination, "WEBP", quality=86, method=4)
        return 1

    with ThreadPoolExecutor(max_workers=4) as executor:
        created = sum(executor.map(preview, data["source_images"]))
    print(f"Synced {len(data['matches'])} matches, {len(data['player_matches'])} player records; {created} new screenshot previews.")


if __name__ == "__main__":
    main()
