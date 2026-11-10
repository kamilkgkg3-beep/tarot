#!/usr/bin/env python3
"""Надёжная дозагрузка всех 78 изображений Rider–Waite–Smith."""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path
from PIL import Image
import io

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "images"
API = "https://api.github.com/repos/mixvlad/TarotCards/contents/tarot/rider-waite/720px?ref=main"

MAJOR = [
    ("Шут", "fool"), ("Маг", "magician"), ("Верховная Жрица", "high priestess"),
    ("Императрица", "empress"), ("Император", "emperor"), ("Иерофант", "hierophant"),
    ("Влюблённые", "lovers"), ("Колесница", "chariot"), ("Сила", "strength"),
    ("Отшельник", "hermit"), ("Колесо Фортуны", "wheel of fortune"),
    ("Справедливость", "justice"), ("Повешенный", "hanged man"), ("Смерть", "death"),
    ("Умеренность", "temperance"), ("Дьявол", "devil"), ("Башня", "tower"),
    ("Звезда", "star"), ("Луна", "moon"), ("Солнце", "sun"),
    ("Суд", "judgement"), ("Мир", "world"),
]
RANKS = [
    ("Туз", "ace"), ("Двойка", "two"), ("Тройка", "three"), ("Четвёрка", "four"),
    ("Пятёрка", "five"), ("Шестёрка", "six"), ("Семёрка", "seven"),
    ("Восьмёрка", "eight"), ("Девятка", "nine"), ("Десятка", "ten"),
    ("Паж", "page"), ("Рыцарь", "knight"), ("Королева", "queen"), ("Король", "king"),
]
SUITS = [("Жезлов", "wands"), ("Кубков", "cups"), ("Мечей", "swords"), ("Пентаклей", "pentacles")]


def request(url, attempts=4):
    last = None
    for n in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "TarotTelegramBot/2.0", "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=45) as response:
                return response.read()
        except Exception as exc:
            last = exc
            if n + 1 < attempts:
                time.sleep(1.5 * (n + 1))
    raise last


def norm(value):
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def valid_image(path):
    try:
        with Image.open(path) as im:
            im.verify()
        return path.stat().st_size > 1500
    except Exception:
        return False


def build_targets():
    targets = []
    for i, (ru, en) in enumerate(MAJOR):
        targets.append((ru, en, f"{i:02d}"))
    for suit_ru, suit_en in SUITS:
        for number, (rank_ru, rank_en) in enumerate(RANKS, 1):
            targets.append((f"{rank_ru} {suit_ru}", f"{rank_en} {suit_en}", f"{suit_en}{number:02d}"))
    return targets


def find_file(items, english, numbered):
    words = norm(english).split()
    compact = re.sub(r"[^a-z0-9]", "", english.lower())
    candidates = []
    for item in items:
        name = item.get("name", "")
        stem = Path(name).stem.lower()
        normalized = norm(stem)
        compact_name = re.sub(r"[^a-z0-9]", "", stem)
        score = 0
        if normalized == norm(english): score += 100
        if all(word in normalized.split() for word in words): score += 70
        if compact and compact in compact_name: score += 60
        # Repository naming convention also uses 00_Fool and Wands01 / Cups14.
        if numbered.lower() in compact_name: score += 80
        if compact_name.startswith(numbered.lower()): score += 30
        if score:
            candidates.append((score, item))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return candidates[0][1]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        files = json.loads(request(API).decode("utf-8"))
    except Exception as exc:
        print("Не удалось получить список файлов GitHub:", exc)
        print("Проверь интернет и повтори запуск.")
        return 1
    images = [x for x in files if x.get("type") == "file" and x.get("name", "").lower().endswith((".jpg", ".jpeg", ".png"))]
    if not images:
        print("GitHub не вернул список изображений. Возможно, изменился адрес источника.")
        return 1

    downloaded = skipped = 0
    missing = []
    for ru, english, numbered in build_targets():
        dest = OUT / f"{ru}.jpg"
        if dest.exists() and valid_image(dest):
            skipped += 1
            continue
        if dest.exists():
            dest.unlink()
        item = find_file(images, english, numbered)
        if not item or not item.get("download_url"):
            missing.append(ru)
            print("Не найдено в источнике:", ru)
            continue
        try:
            data = request(item["download_url"])
            with Image.open(io.BytesIO(data)) as im:
                im.verify()
            if len(data) < 1500:
                raise ValueError("файл слишком маленький")
            # Store as JPEG for the bot's stable filename convention.
            with Image.open(io.BytesIO(data)) as im:
                rgb = im.convert("RGB")
                rgb.save(dest, "JPEG", quality=94, optimize=True)
            if not valid_image(dest):
                raise ValueError("проверка изображения не пройдена")
            downloaded += 1
            print(f"[{downloaded + skipped}/78] Загружена: {ru}")
        except Exception as exc:
            missing.append(ru)
            print(f"Ошибка загрузки {ru}: {exc}")

    total = sum(1 for ru, _, _ in build_targets() if valid_image(OUT / f"{ru}.jpg"))
    print(f"\nПроверка колоды: {total}/78 исправных изображений.")
    print(f"Скачано сейчас: {downloaded}; уже было исправно: {skipped}.")
    if total != 78:
        print("Не хватает или не прошли проверку: " + ", ".join(missing))
        print("Повтори запуск: исправные файлы будут сохранены, недостающие докачаются.")
        return 2
    print("Все 78 карт готовы!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
