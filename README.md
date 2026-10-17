# Quran audio for xiaozhi-esp32

Файлы Ogg/Opus (16 кГц, моно) лежат в папке `quran/<чтец>/001.ogg ... 114.ogg`.
Плата берёт их по ссылке
`https://raw.githubusercontent.com/<пользователь>/<репозиторий>/main/quran/<чтец>/001.ogg`.

Источник звука - официальный бесплатный CDN проекта Al Quran Cloud
(<https://alquran.cloud/cdn>), без ключа и регистрации, с условиями,
прямо разрешающими скачивание и кеширование.

## Добавить чтеца
Вкладка **Actions -> Convert Quran audio -> Run workflow**, заполните:
- **edition** - идентификатор чтеца на CDN, например `ar.alafasy`. Частые варианты:

  | identifier | чтец |
  |---|---|
  | `ar.alafasy` | Мишари Рашид аль-Афаси |
  | `ar.husary` | Махмуд Халиль аль-Хусари |
  | `ar.minshawi` | Мухаммад Сиддик аль-Миншави |
  | `ar.sudais` | Абдуррахман ас-Судайс |
  | `ar.shuraim` | Сауд аш-Шурайм |
  | `ar.abdulbasit` | Абдул-Басит Абдус-Самад |
  | `ar.ajamy` | Ахмад аль-Аджами |

  Полный актуальный список: <https://api.alquran.cloud/v1/edition/format/audio>,
  либо `python scripts/prepare_quran.py --list-editions` на своём компьютере.
- **folder** - имя папки в репозитории (латиницей, например `afasy`).
- **surahs** (необязательно) - например `1,18,36-40`, если нужны не все суры.

Не включайте Git LFS: через raw.githubusercontent.com он отдаёт не файл, а заглушку.
