RELEASE_DEX_PATH := `realpath -m dist/dex/release/classes.dex`
DEBUG_DEX_PATH := `realpath -m dist/dex/debug/classes.dex`

PLUGIN_PY := `grep -ls '^__id__ = ' -- *.py | head -n1`
DIST_PY := "dist/" + file_name(PLUGIN_PY)
DIST_PLUGIN := "dist/" + file_stem(PLUGIN_PY) + ".plugin"

# fail early if the tools a recipe needs are not installed
[private]
_require +COMMANDS:
    #!/usr/bin/env bash
    set -euo pipefail

    missing=()
    for cmd in {{ COMMANDS }}; do
        command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
    done

    if [ ${#missing[@]} -ne 0 ]; then
        echo "missing required commands: ${missing[*]}" >&2
        exit 1
    fi

# build dex in debug mode
dex: (_require "java")
    ./gradlew buildDexDebug

# embed a DEX (default: release) into a distributable copy of the plugin .py
embed DEX_PATH=RELEASE_DEX_PATH OUTPUT=DIST_PY SOURCE=PLUGIN_PY: (_require "uv")
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p "$(dirname '{{ OUTPUT }}')"
    uv run python tools/embed_dex.py '{{ DEX_PATH }}' '{{ SOURCE }}' '{{ OUTPUT }}'

# stamp the version, build the release DEX and embed it into a distributable plugin
ci-release VERSION OUTPUT=DIST_PLUGIN: (_require "java" "uv")
    #!/usr/bin/env bash
    set -euo pipefail

    tmp=$(mktemp -d)
    trap 'rm -rf "$tmp"' EXIT

    cp '{{ PLUGIN_PY }}' "$tmp/{{ file_name(PLUGIN_PY) }}"
    cp pyproject.toml "$tmp/pyproject.toml"

    uv run python scripts/prepare_release.py \
        --version '{{ VERSION }}' \
        --plugin-file "$tmp/{{ file_name(PLUGIN_PY) }}" \
        --pyproject-file "$tmp/pyproject.toml"

    ./gradlew buildDexRelease
    just embed '{{ RELEASE_DEX_PATH }}' '{{ OUTPUT }}' "$tmp/{{ file_name(PLUGIN_PY) }}"

# watch the plugin source + debug DEX and live-reload on device via extera dev-sync
watch *ARGS: (_require "uv" "adb")
    uv run python tools/dev_watch.py '{{ PLUGIN_PY }}' '{{ DEBUG_DEX_PATH }}' {{ ARGS }}

# generate new Telegram[-compile].jar from updated extera/Ayu-Gram apk
update-apk PATH_TO_APK: (_require "dex2jar" "jbang" "git")
    #!/usr/bin/env bash
    set -veuo pipefail

    # create task temp dir
    tmp=$(mktemp -d)
    trap 'rm -rf "$tmp"' EXIT

    # copy provided apk into temp dir
    cp {{ PATH_TO_APK }} "$tmp/Telegram.apk"

    # convert apk to jar
    dex2jar -f -o "$tmp/Telegram.jar" "$tmp/Telegram.apk"

    # fix class inheritance and exclude unneded packages
    jbang ./tools/FixTelegramJar.java "$tmp/Telegram.jar" "$tmp/Telegram-compile.jar"

    # copy generated jars
    mkdir -p ./libs/
    cp "$tmp/Telegram.jar" ./libs/Telegram.jar
    cp "$tmp/Telegram-compile.jar" ./libs/Telegram-compile.jar

    # and commit them
    git add -N -- ./libs/Telegram.jar ./libs/Telegram-compile.jar
    git commit -m "chore: bump telegram version" -- ./libs/Telegram.jar ./libs/Telegram-compile.jar

# generate stubs for python
gen-stubs PATH_TO_RT_JAR PATH_TO_ANDROID_JAR: (_require "java2pyi")
    java2pyi {{ PATH_TO_RT_JAR }} {{ PATH_TO_ANDROID_JAR }} ./libs/Telegram.jar -o stubs/
