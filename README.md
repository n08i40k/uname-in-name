# exteraGram Plugin Template

Шаблон плагина для exteraGram / AyuGram, в котором вся логика написана на Kotlin,
собирается в DEX и встраивается прямо в `.py`-файл плагина.

## Как это устроено

- `<plugin-id>.py` — сам плагин: метаданные, i18n, загрузка встроенного DEX
  через `InMemoryDexClassLoader` и вызов Kotlin-класса `Plugin`.
- `src/main/kotlin/...` — основная логика (хуки, пункты меню, настройки, i18n).
- `tools/embed_dex.py` — вшивает собранный `classes.dex` в копию `.py`.
- `tools/dev_watch.py` — live-reload на устройстве через `extera dev-sync` (adb).
- `libs/Telegram*.jar` — классы хост-приложения (в git через LFS); генерируются
  из APK рецептом `just update-apk`.

## Требования

`java` (JDK 21), `uv`, `just`, `adb`. Для `update-apk` дополнительно `dex2jar` и `jbang`.

## Быстрый старт

```sh
# переименовать шаблон под себя: пакет, id и отображаемое имя
just init com.example.myplugin my-plugin "My Plugin"

# положить libs/Telegram.jar и Telegram-compile.jar (из APK хоста)
just update-apk /path/to/exteragram.apk

just dex     # debug-сборка DEX
just watch   # live-reload на подключённом устройстве
```

## Сборка релиза

```sh
just ci-release 1.2.3    # -> dist/<plugin-id>.plugin: версия, release-DEX и упаковка
```

`just embed` вшивает уже собранный release-DEX в `dist/<plugin-id>.py`, не трогая версию.

Либо workflow **Release** в GitHub Actions (запуск вручную, версия в формате `x.x.x`).

## Прочие команды

- `just loc` — перегенерировать i18n-файлы без полной пересборки DEX.
- `just gen-stubs <rt.jar> <android.jar>` — стабы для автодополнения в Python.

## Лицензия

[MIT](LICENSE)
