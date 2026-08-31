# UserName-In-Name

Плагин для exteraGram / AyuGram, который подставляет юзернейм в отображаемое имя
пользователя по заданному шаблону. Логика написана на Kotlin, собирается в DEX и
встраивается прямо в `.py`-файл плагина.

## Шаблон

В настройках плагина задаётся шаблон имени:

- `{o}` — оригинальное имя пользователя;
- `{u}` — юзернейм.

По умолчанию — `{o} | @{u}`. Шаблон применяется только к пользователям с
юзернеймом, остальные отображаются как обычно.

## Как это устроено

- `uname-in-name.py` — сам плагин: метаданные, i18n, настройки, загрузка
  встроенного DEX через `InMemoryDexClassLoader` и вызов Kotlin-класса `Plugin`.
- `src/main/kotlin/...` — логика: хуки на `UserObject.getUserName` и
  `UserObject.getFirstName`, логгер и отправка crash-отчётов.
- `tools/embed_dex.py` — вшивает собранный `classes.dex` в копию `.py`.
- `tools/dev_watch.py` — live-reload на устройстве через `extera dev-sync` (adb).
- `tools/FixTelegramJar.java` — готовит `Telegram-compile.jar` из `Telegram.jar`
  (восстанавливает `InnerClasses` и отсекает лишние пакеты).
- `libs/Telegram*.jar` — классы хост-приложения (в git через LFS); генерируются
  из APK рецептом `just update-apk`.

## Требования

`java` (JDK 21), `uv`, `just`, `adb`. Для `update-apk` дополнительно `dex2jar` и `jbang`.

## Быстрый старт

```sh
# положить libs/Telegram.jar и Telegram-compile.jar (из APK хоста)
just update-apk /path/to/exteragram.apk

just dex     # debug-сборка DEX
just watch   # live-reload на подключённом устройстве
```

## Сборка релиза

```sh
just ci-release 1.2.3    # -> dist/uname-in-name.plugin: версия, release-DEX и упаковка
```

`just embed` вшивает уже собранный release-DEX в `dist/uname-in-name.py`, не трогая версию.

Либо workflow **Release** в GitHub Actions (запуск вручную, версия в формате `x.x.x`).

## Прочие команды

- `just gen-stubs <rt.jar> <android.jar>` — стабы для автодополнения в Python.

## Лицензия

[MIT](LICENSE)
