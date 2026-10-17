#!/usr/bin/env python3
"""
Готовит аудио Корана для xiaozhi-esp32 из официального бесплатного CDN
islamic.network (проект Al Quran Cloud, https://alquran.cloud/cdn).

Источник не требует ключа и явно разрешает скачивание и кеширование
("cache aggressively at your own edge" - из условий использования CDN).

Делает из MP3 файлы Ogg/Opus (16 кГц, моно, кадры 60 мс) с именами 001.ogg ... 114.ogg -
такие же по формату, как азан. Нужны Python 3.8+ и ffmpeg (с libopus).

Примеры:
  # список доступных чтецов (аудио-изданий) прямо с сервера
  python prepare_quran.py --list-editions

  # скачать и преобразовать всего Корана одного чтеца
  python prepare_quran.py --edition ar.alafasy --out quran/afasy

  # только несколько сур, битрейт поменьше, зеркало в России
  python prepare_quran.py --edition ar.sudais --out quran/sudais --surahs 1,18,36,55,67,112-114 --mirror ru

  # у вас уже есть готовые MP3 (в имени файла должен быть номер суры)
  python prepare_quran.py --input-dir C:\\mp3\\afasy --out quran/afasy

Готовые файлы пропускаются, поэтому скрипт можно запускать повторно.
Один чтец (114 сур, 16 кбит/с на выходе) занимает около 50-60 МБ.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

EDITIONS_API = "https://api.alquran.cloud/v1/edition/format/audio"
MIRRORS = {
    "global": "https://cdn.islamic.network",
    "ru": "https://cdn.alislam.ru",
}
CDN_BITRATES = (192, 128, 64, 48, 40, 32)  # доступные битрейты источника, см. alquran.cloud/cdn
UA = "xiaozhi-quran-prepare/2.0"
GITHUB_WEB_LIMIT = 25 * 1024 * 1024    # загрузка через браузер
GITHUB_HARD_LIMIT = 100 * 1024 * 1024  # жёсткий лимит GitHub на файл


def surah_number(filename):
    """Номер суры из имени файла: берём последнее число в имени."""
    numbers = re.findall(r"\d+", os.path.splitext(os.path.basename(filename))[0])
    if not numbers:
        return None
    n = int(numbers[-1])
    return n if 1 <= n <= 114 else None


def parse_surah_list(spec):
    """'1,18,36,55,67,112-114' -> [1, 18, 36, 55, 67, 112, 113, 114]"""
    if not spec:
        return list(range(1, 115))
    out = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    bad = [n for n in out if not 1 <= n <= 114]
    if bad:
        sys.exit("Номер суры вне диапазона 1..114: %s" % bad)
    return sorted(out)


def convert(src, dst, bitrate_kbps):
    tmp = dst + ".part"
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src,
           "-vn", "-map_metadata", "-1", "-ac", "1", "-ar", "16000",
           "-c:a", "libopus", "-b:a", "%dk" % bitrate_kbps, "-frame_duration", "60",
           "-application", "audio", "-f", "ogg", tmp]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise RuntimeError(result.stderr.strip() or "ffmpeg failed")
    os.replace(tmp, dst)


def convert_fit(src, dst, bitrate_kbps, max_bytes):
    """Преобразует файл; если он больше max_bytes, повторяет с меньшим битрейтом."""
    candidates = [bitrate_kbps] + [b for b in (12, 10, 8) if b < bitrate_kbps]
    for br in candidates:
        convert(src, dst, br)
        if not max_bytes or os.path.getsize(dst) <= max_bytes:
            if br != bitrate_kbps:
                print("   файл не влезал в лимит, использован битрейт %d кбит/с" % br)
            return
    print("   ВНИМАНИЕ: даже при %d кбит/с файл больше лимита" % candidates[-1])


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def download(url, dst, retries=3):
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as resp, open(dst, "wb") as out:
                shutil.copyfileobj(resp, out)
            return
        except OSError as exc:
            if attempt == retries:
                raise
            print("   повтор (%s)" % exc)
            time.sleep(2 * attempt)


def list_editions(query):
    data = fetch_json(EDITIONS_API)
    items = data.get("data", [])
    tokens = re.findall(r"[a-z0-9]+", (query or "").lower())
    print("%-24s %-10s %s" % ("identifier", "язык", "имя"))
    for e in items:
        name = str(e.get("englishName", ""))
        ident = str(e.get("identifier", ""))
        hay = (name + " " + ident).lower()
        if not tokens or all(t in hay for t in tokens):
            print("%-24s %-10s %s" % (ident, e.get("language", ""), name))


def resolve_bitrate(requested, available=None):
    """Ближайший доступный битрейт CDN не ниже запрошенного, иначе максимальный доступный."""
    pool = sorted(available, reverse=True) if available else sorted(CDN_BITRATES, reverse=True)
    for b in sorted(pool):
        if b >= requested:
            return b
    return max(pool)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--input-dir", help="папка с готовыми MP3 (вместо скачивания)")
    p.add_argument("--edition", help="идентификатор чтеца на CDN, например ar.alafasy (см. --list-editions)")
    p.add_argument("--list-editions", metavar="QUERY", nargs="?", const="",
                   help="показать список чтецов (можно с фильтром по имени) и выйти")
    p.add_argument("--mirror", choices=["global", "ru"], default="global",
                   help="global = cdn.islamic.network, ru = российское зеркало cdn.alislam.ru")
    p.add_argument("--surahs", help="какие суры брать, например '1,18,36,55,67,112-114' (по умолчанию все 114)")
    p.add_argument("--source-bitrate", type=int, default=128,
                   help="битрейт, который запрашивать у CDN: 32/40/48/64/128/192 (по умолчанию 128)")
    p.add_argument("--out", default="quran_out", help="папка результата")
    p.add_argument("--bitrate", type=int, default=16, help="битрейт результата (Opus), кбит/с, по умолчанию 16")
    p.add_argument("--max-size-mb", type=float, default=0,
                   help="максимальный размер файла в МБ; битрейт результата снижается автоматически")
    args = p.parse_args()

    if args.list_editions is not None:
        list_editions(args.list_editions)
        return
    if not shutil.which("ffmpeg"):
        sys.exit("Не найден ffmpeg. Установите его и перезапустите терминал.")
    if bool(args.input_dir) == bool(args.edition):
        sys.exit("Укажите либо --input-dir, либо --edition (см. --help, или --list-editions для списка чтецов)")

    os.makedirs(args.out, exist_ok=True)
    jobs = []  # (номер, источник: путь или url)
    if args.input_dir:
        for name in sorted(os.listdir(args.input_dir)):
            n = surah_number(name)
            if n and name.lower().endswith((".mp3", ".m4a", ".wav", ".ogg", ".flac")):
                jobs.append((n, os.path.join(args.input_dir, name)))
    else:
        base = MIRRORS[args.mirror]
        bitrate = resolve_bitrate(args.source_bitrate)
        if bitrate != args.source_bitrate:
            print("Битрейт %d недоступен на CDN, использую ближайший: %d" % (args.source_bitrate, bitrate))
        surahs = parse_surah_list(args.surahs)
        print("Чтец: %s | зеркало: %s | битрейт источника: %d кбит/с" % (args.edition, base, bitrate))
        for n in surahs:
            jobs.append((n, "%s/quran/audio-surah/%d/%s/%d.mp3" % (base, bitrate, args.edition, n)))

    if not jobs:
        sys.exit("Не найдено ни одного файла с номером суры 1..114")
    jobs.sort()
    seen = set()
    total = 0
    for n, source in jobs:
        if n in seen:
            print("Сура %d: пропущен дубликат %s" % (n, source))
            continue
        seen.add(n)
        dst = os.path.join(args.out, "%03d.ogg" % n)
        if os.path.exists(dst):
            print("Сура %3d: уже есть" % n)
        else:
            tmp_src = None
            try:
                if source.startswith("http"):
                    fd, tmp_src = tempfile.mkstemp(suffix=".mp3")
                    os.close(fd)
                    print("Сура %3d: скачиваю..." % n)
                    download(source, tmp_src)
                    src = tmp_src
                else:
                    src = source
                print("Сура %3d: преобразую..." % n)
                convert_fit(src, dst, args.bitrate, int(args.max_size_mb * 1048576))
            except (OSError, RuntimeError) as exc:
                print("   ОШИБКА: %s (%s)" % (exc, source))
                continue
            finally:
                if tmp_src and os.path.exists(tmp_src):
                    os.remove(tmp_src)
        size = os.path.getsize(dst)
        total += size
        if size > GITHUB_HARD_LIMIT:
            print("   ВНИМАНИЕ: %.0f МБ - больше лимита GitHub (100 МБ), снизьте --bitrate" % (size / 1048576))
        elif size > GITHUB_WEB_LIMIT:
            print("   %.0f МБ - через браузер GitHub не загрузится (лимит 25 МБ)" % (size / 1048576))

    missing = [n for n in parse_surah_list(args.surahs) if n not in seen]
    print("\nГотово: %d файлов, %.0f МБ в папке %s" % (len(seen), total / 1048576, args.out))
    if missing:
        print("Нет сур: %s" % ", ".join(map(str, missing)))


if __name__ == "__main__":
    main()
