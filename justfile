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

# generate i18n files (use added lines without full dex rebuild)
loc: (_require "java")
    ./gradlew generateI18n4kFiles

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
    mkdir ./libs/
    cp "$tmp/Telegram.jar" ./libs/Telegram.jar
    cp "$tmp/Telegram-compile.jar" ./libs/Telegram-compile.jar

    # and commit them
    git add -N -- ./libs/Telegram.jar ./libs/Telegram-compile.jar
    git commit -m "chore: bump telegram version" -- ./libs/Telegram.jar ./libs/Telegram-compile.jar

# generate stubs for python
gen-stubs PATH_TO_RT_JAR PATH_TO_ANDROID_JAR: (_require "java2pyi")
    java2pyi {{ PATH_TO_RT_JAR }} {{ PATH_TO_ANDROID_JAR }} ./libs/Telegram.jar -o stubs/

# rename plugin package/id/name and move sources (e.g. just rename com.example.myplugin my-plugin "My Plugin")
init NEW_PACKAGE NEW_ID NEW_NAME: (_require "uv")
    #!/usr/bin/env bash
    set -euo pipefail

    new_package='{{ NEW_PACKAGE }}'
    new_id='{{ NEW_ID }}'
    new_name='{{ NEW_NAME }}'

    if ! [[ "$new_package" =~ ^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$ ]]; then
        echo "invalid package: $new_package (expected e.g. com.example.myplugin)" >&2
        exit 1
    fi

    if ! [[ "$new_id" =~ ^[a-z0-9][a-z0-9._-]*$ ]]; then
        echo "invalid plugin id: $new_id (expected e.g. my-plugin)" >&2
        exit 1
    fi

    # current values are read from the sources, so the recipe can be run repeatedly
    old_package=$(sed -n 's/^ *namespace = "\(.*\)"$/\1/p' build.gradle.kts)
    old_py=$(grep -ls '^__id__ = ' -- *.py | head -n1)
    old_id=$(sed -n 's/^__id__ = "\(.*\)"$/\1/p' "$old_py")
    old_name=$(sed -n 's/^rootProject.name = "\(.*\)"$/\1/p' settings.gradle.kts)

    if [ -z "$old_package" ] || [ -z "$old_py" ] || [ -z "$old_id" ]; then
        echo "failed to detect current plugin package/id" >&2
        exit 1
    fi

    old_path="src/main/kotlin/${old_package//.//}"
    new_path="src/main/kotlin/${new_package//.//}"

    echo "package: $old_package -> $new_package"
    echo "id:      $old_id -> $new_id"
    echo "name:    $old_name -> $new_name"

    # move the sources into the new package folder
    if [ "$old_path" != "$new_path" ]; then
        mkdir -p "$(dirname "$new_path")"
        mv "$old_path" "$new_path"

        # drop the package folders left empty by the move
        old_parent=$(dirname "$old_path")
        while [ "$old_parent" != "src/main/kotlin" ] && rmdir "$old_parent" 2>/dev/null; do
            old_parent=$(dirname "$old_parent")
        done
    fi

    # package references, both dotted (kotlin) and slashed (relocation/proguard config)
    files=(build.gradle.kts proguard-rules.pro "$old_py")
    while IFS= read -r -d '' file; do
        files+=("$file")
    done < <(find src -name '*.kt' -print0)

    sed -i \
        -e "s|${old_package//./\\.}|${new_package}|g" \
        -e "s|${old_package//.//}|${new_package//.//}|g" \
        -e "s|${old_id}|${new_id}|g" \
        "${files[@]}"

    # plugin metadata
    sed -i "s|^__name__ = \".*\"$|__name__ = \"${new_name}\"|" "$old_py"
    sed -i "s|^rootProject.name = \".*\"$|rootProject.name = \"${new_name}\"|" settings.gradle.kts
    sed -i "s|^name = \".*\"$|name = \"${new_id}\"|" pyproject.toml

    if [ "$old_py" != "${new_id}.py" ]; then
        mv "$old_py" "${new_id}.py"
    fi

    uv sync

    echo "done, run 'just dex' to rebuild"
