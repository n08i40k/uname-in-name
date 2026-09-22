# fmt: off
import base64
import lzma
import os
import threading
import traceback
from typing import Any, Optional, cast

from android.util import Log
from android.webkit import ValueCallback
from android_utils import copy_to_clipboard, run_on_ui_thread
from base_plugin import BasePlugin
from client_utils import get_last_fragment
from dalvik.system import InMemoryDexClassLoader
from java import dynamic_proxy
from java.lang import Class, String, Boolean
from java.nio import ByteBuffer
from org.telegram.messenger import ApplicationLoader, LocaleController
from org.telegram.ui.ActionBar import AlertDialog
from ui.bulletin import BulletinHelper
from ui.settings import Divider, EditText, Header, Switch

__id__ = "uname-in-name"
__name__ = "UserName-In-Name"
__description__ = "Отображение юзернейма в имени пользователя по заданному шаблону"
__author__ = "@n08i40k_extera"
__icon__ = "LedScreenEmoji/47"
__version__ = "1.0.0"
__min_version__ = "12.1.1"

LOGCAT_TAG = __id__

JVM_PLUGIN_CLASS = "ru.n08i40k.uname_in_name.Plugin"

SETTINGS_TEMPLATE_KEY = "uname-in-name.template"
SETTINGS_COPY_ON_LONG_PRESS_KEY = "uname-in-name.copy-on-long-press"

SETTINGS_DEFAULT_TEMPLATE = "{o} | @{u}"
SETTINGS_DEFAULT_COPY_ON_LONG_PRESS = True

DEX_COMMENT_BEGIN = "# === EMDEDDED DEX BEGIN ==="
DEX_COMMENT_END = "# === EMDEDDED DEX END ==="


I18N_SETTINGS: dict[str, dict[str, str]] = {
    "settings.template.title": {
        "en": "Formatting template",
        "ru": "Шаблон форматирования",
    },
    "settings.template.hint": {
        "en": "{o} | @{u}",
    },
    "settings.template.desc": {
        "en": "You can write any template, and it will be used when a user name is displayed.\n\n{o} - The original user name.\n{u} - The username, if present.\n\nThe template is applied only to users that have a username.\nOtherwise the user name is displayed as usual.",
        "ru": "Вы можете написать любой шаблон, который будет использоваться при отображении имени пользователя.\n\n{o} - Оригинальное имя пользователя.\n{u} - Юзернейм, если присутствует.\n\nШаблон применяется только если у пользователя есть юзернейм.\nВ противном случае имя пользователя будет отображаться как обычно.",
    },
    "settings.actions.title": {
        "en": "Actions",
        "ru": "Действия",
    },
    "settings.copy_on_long_press.text": {
        "en": "Copy username on long press",
        "ru": "Копировать юзернейм при длительном нажатии",
    },
    "settings.copy_on_long_press.desc": {
        "en": "Copies the username to the clipboard when long-pressing the name in a message.",
        "ru": "Копирует имя пользователя в буфер обмена при длительном нажатии на его имя в сообщении.",
    },
}

I18N_DIALOG: dict[str, dict[str, str]] = {
    "dialog.load_crash.title": {
        "en": "Plugin failed to load",
        "ru": "Не удалось загрузить плагин",
    },
    "dialog.load_crash.message": {
        "en": "The plugin crashed at stage `{stage}`. The report is copied to the clipboard.",
        "ru": "Плагин упал на этапе `{stage}`. Отчёт скопирован в буфер обмена.",
    },
    "dialog.load_crash.ok": {
        "en": "OK",
        "ru": "ОК",
    },
}

I18N_STATUS: dict[str, dict[str, str]] = {
    "status.error.dex.missing": {
        "en": "Plugin engine is missing from the source file",
        "ru": "Движок плагина отсутствует в файле плагина",
    },
}

I18N_STRINGS: dict[str, dict[str, str]] = {
    **I18N_SETTINGS,
    **I18N_DIALOG,
    **I18N_STATUS,
}

# fmt: on


def _detached(text: str) -> str:
    """Copy of `text` that shares no object with the rest of the module.

    exteraGram reads every field of a settings item as a PyObject and closes it
    right after reading, while equal string constants of one module are a single
    Python object. Two fields holding the same text would make the second read
    hit an already closed object, and the whole settings list of the plugin is
    then dropped with `ValueError: PyObject is closed`.
    """
    return "".join(iter(text))


class JvmPluginBridge:
    """Loads classes.dex embedded (as a base64 comment) into this very .py file."""

    klass: Optional[Class]

    def __init__(self, plugin: "Plugin"):
        self.plugin = plugin
        self.klass = None

    def load(self):
        dex_data = self._read_embedded_dex()
        if dex_data is None:
            self.plugin.log("Embedded DEX is unavailable; plugin will not load")
            self.plugin._show_error(self.plugin._t("status.error.dex.missing"))
            return

        try:
            loader = InMemoryDexClassLoader(
                ByteBuffer.wrap(dex_data),  # ty:ignore[invalid-argument-type]
                ApplicationLoader.applicationContext.getClassLoader(),
            )
            self.klass = loader.loadClass(String(JVM_PLUGIN_CLASS))
        except Exception as e:
            self.plugin.log_exception("Failed to load DEX", e)

    def call(self, name: str, *args: Any, types: tuple = ()) -> Any:
        """Invoke a static method of the loaded JVM plugin class.

        Raises if the class is not loaded or the call itself fails; callers
        decide whether that is fatal for them.
        """
        if self.klass is None:
            raise RuntimeError(f"cannot call {name}: JVM plugin is not loaded")

        return self.klass.getDeclaredMethod(String(name), *types).invoke(None, *args)

    def _read_own_source(self) -> Optional[str]:
        candidates: list[str] = []

        own_file = globals().get("__file__")
        if isinstance(own_file, str) and own_file:
            candidates.append(own_file)

        plugins_dir_getter = globals().get("get_plugins_dir")
        if callable(plugins_dir_getter):
            try:
                candidates.append(os.path.join(plugins_dir_getter(), f"{__id__}.py"))
            except Exception as e:
                self.plugin.log_exception("Failed to resolve plugins directory", e)

        for path in candidates:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                self.plugin.log_exception(f"Failed to read plugin source at {path}", e)

        return None

    def _read_embedded_dex(self) -> Optional[bytes]:
        source = self._read_own_source()
        if source is None:
            self.plugin.log("Failed to read plugin source for embedded DEX")
            return None

        payload = bytearray()
        decompressor = lzma.LZMADecompressor()
        collecting = False
        completed = False

        try:
            for line in source.splitlines():
                stripped = line.strip()

                if not collecting:
                    collecting = stripped == DEX_COMMENT_BEGIN
                    continue

                if stripped == DEX_COMMENT_END:
                    completed = True
                    break

                if stripped.startswith("#"):
                    chunk = base64.b64decode(stripped[1:].strip())
                    payload += decompressor.decompress(chunk)
        except (ValueError, lzma.LZMAError) as e:
            self.plugin.log_exception("Failed to decode embedded DEX", e)
            return None

        if completed and not decompressor.eof:
            self.plugin.log("Embedded DEX payload is truncated")
            return None

        if not completed or not payload:
            self.plugin.log("Embedded DEX payload is empty")
            return None

        return bytes(payload)


class SettingsActions:
    """Builds the settings items shown in the plugin settings screen."""

    def __init__(self, plugin: "Plugin"):
        self.plugin = plugin

    def build_settings(self) -> list[Any]:
        try:
            return [
                Header(text=self.plugin._t("settings.template.title")),
                EditText(
                    key=SETTINGS_TEMPLATE_KEY,
                    hint=self.plugin._t("settings.template.hint"),
                    default=_detached(SETTINGS_DEFAULT_TEMPLATE),
                    on_change=self._on_template_change,
                ),
                Divider(text=self.plugin._t("settings.template.desc")),
                Header(text=self.plugin._t("settings.actions.title")),
                Switch(
                    key=SETTINGS_COPY_ON_LONG_PRESS_KEY,
                    text=self.plugin._t("settings.copy_on_long_press.text"),
                    default=SETTINGS_DEFAULT_COPY_ON_LONG_PRESS,
                    on_change=self._on_copy_on_long_press_change,
                ),
                Divider(text=self.plugin._t("settings.copy_on_long_press.desc")),
            ]
        except Exception as e:
            self.plugin.log_exception("Failed to build settings items", e)

            raise e

    def _on_template_change(self, template: str):
        try:
            self.plugin.push_formatting_template(template or SETTINGS_DEFAULT_TEMPLATE)
        except Exception as e:
            self.plugin.log_exception("Failed to apply formatting template", e)

    def _on_copy_on_long_press_change(self, value: bool):
        try:
            self.plugin.push_copy_on_long_press(value)
        except Exception as e:
            self.plugin.log_exception("Failed to apply copy on long press", e)


class Plugin(BasePlugin):
    _full_load_lock = threading.Lock()
    _eject_lock = threading.Lock()

    _load_logging_active = False
    _load_log_buffer: list[str] = []
    _full_load_started = False
    _ejected = False

    jvm_plugin: JvmPluginBridge

    def log(self, message: Any):
        text = str(message)
        super().log(text)

        if self._load_logging_active:
            self._load_log_buffer.append(text)

        try:
            Log.i(cast("String", LOGCAT_TAG), cast("String", text))
        except Exception:
            pass

    def log_exception(self, message: str, exception: BaseException):
        self.log(f"{message}: {exception}")

        for chunk in traceback.format_exception(
            type(exception),
            exception,
            exception.__traceback__,
        ):
            for line in chunk.rstrip().splitlines():
                if line:
                    self.log(line)

    def create_settings(self) -> list[Any]:
        return SettingsActions(self).build_settings()

    def _show_error(self, message: str):
        run_on_ui_thread(lambda: BulletinHelper.show_error(message))

    def _t(self, key: str, **kwargs: Any) -> str:
        values = I18N_STRINGS.get(key)
        if values is None:
            text = key
        else:
            text = values.get(self._get_app_language_code()) or values.get("en") or key

        try:
            return text.format(**kwargs)
        except Exception:
            return text

    def _get_app_language_code(self) -> str:
        raw = None

        try:
            info = LocaleController.getInstance().getCurrentLocaleInfo()
            if info.hasBaseLang():
                raw = info.baseLangCode
            else:
                raw = info.getLangCode() or info.shortName
        except Exception:
            pass

        if not raw:
            try:
                raw = LocaleController.getInstance().getCurrentLocale().getLanguage()
            except Exception:
                return "en"

        return str(raw).strip().lower().replace("-", "_").split("_", 1)[0] or "en"

    def _start_load_logging(self):
        self._load_log_buffer = []
        self._load_logging_active = True

    def _stop_load_logging(self):
        self._load_logging_active = False
        self._load_log_buffer = []

    def _handle_load_failure(self, stage: str, exception: BaseException):
        self.log_exception(f"Plugin load failed ({stage})", exception)

        logs = "\n".join(self._load_log_buffer)
        report = (
            f"Stage: `{stage}`\n"
            f"Plugin version: `{__version__}`\n\n"
            f"Error:\n```\n{exception}\n```\n\n"
            f"Log:\n```\n{logs}\n```"
        )

        try:
            copy_to_clipboard(report)
        except Exception as e:
            self.log_exception("Failed to copy load-crash report to clipboard", e)

        self._show_load_crash_dialog(stage)

    def _show_load_crash_dialog(self, stage: str):
        def show():
            try:
                fragment = get_last_fragment()
            except Exception:
                fragment = None

            message = self._t("dialog.load_crash.message", stage=stage)

            if fragment is None:
                self._show_error(message)
                return

            try:
                fragment.showDialog(
                    AlertDialog.Builder(fragment.getContext())
                    .setTitle(String(self._t("dialog.load_crash.title")))
                    .setMessage(String(message))
                    .setPositiveButton(
                        String(self._t("dialog.load_crash.ok")),
                        None,  # ty:ignore[invalid-argument-type]
                    )
                    .create()
                )
            except Exception as e:
                self.log_exception("Failed to show load crash dialog", e)
                self._show_error(message)

        run_on_ui_thread(show)

    def _prepare_jvm_plugin(self) -> bool:
        self.jvm_plugin = JvmPluginBridge(self)
        self.jvm_plugin.load()

        return self.jvm_plugin.klass is not None

    def _inject_jvm_plugin(self):
        try:
            self.log(f"Loading JVM plugin {self.jvm_plugin.call('getBuildDate')}")
        except Exception as e:
            self.log_exception("Failed to infer JVM plugin version", e)

        ref = self

        class Logger(dynamic_proxy(ValueCallback)):
            def onReceiveValue(self, arg0):
                ref.log(str(arg0))

        self.jvm_plugin.call(
            "inject",
            String(__version__),
            Logger(),
            types=(String.getClass(), ValueCallback.getClass()),
        )
        self.log("JVM plugin injected successfully")

    def push_formatting_template(self, template: str):
        self.jvm_plugin.call(
            "setFormattingTemplate",
            String(template),
            types=(String.getClass(),),
        )

    def push_copy_on_long_press(self, value: bool):
        self.jvm_plugin.call(
            "setCopyOnLongPress",
            value,
            types=(Boolean.TYPE,),
        )

    def _apply_saved_settings(self):
        self.push_formatting_template(
            self.get_setting(SETTINGS_TEMPLATE_KEY, SETTINGS_DEFAULT_TEMPLATE)
        )

        self.push_copy_on_long_press(
            self.get_setting(
                SETTINGS_COPY_ON_LONG_PRESS_KEY, SETTINGS_DEFAULT_COPY_ON_LONG_PRESS
            )
        )

        self.log("Saved settings applied")

    def _finalize_jvm_plugin_inject(self):
        self.jvm_plugin.call("finalizeInject")
        self.log("JVM plugin finalizeInject completed")

    def _run_plugin_load(self):
        with self._full_load_lock:
            if self._full_load_started:
                return
            self._full_load_started = True

        if not self._prepare_jvm_plugin():
            with self._full_load_lock:
                self._full_load_started = False
            return

        for stage, action in (
            ("inject", self._inject_jvm_plugin),
            ("applySavedSettings", self._apply_saved_settings),
            ("finalizeInject", self._finalize_jvm_plugin_inject),
        ):
            try:
                action()
            except BaseException as e:
                self._handle_load_failure(stage, e)
                self.on_plugin_eject()
                return

        self._stop_load_logging()

    def on_plugin_load(self):
        self._start_load_logging()
        self._ejected = False
        self._full_load_started = False

        thread = threading.Thread(
            target=self._run_plugin_load,
            name=f"{__id__}-continue-plugin-load",
            daemon=True,
        )
        thread.start()

        return thread

    def on_plugin_unload(self):
        jvm_plugin = getattr(self, "jvm_plugin", None)

        if jvm_plugin is None or jvm_plugin.klass is None:
            return

        try:
            jvm_plugin.call("eject")
            self.log("JVM plugin ejected successfully")
        except Exception as e:
            self.log_exception("Failed to eject JVM plugin", e)

        jvm_plugin.klass = None

    def on_plugin_eject(self):
        with self._eject_lock:
            if self._ejected:
                return
            self._ejected = True

        self.log("JVM plugin instance lost: ejected by a concurrent reload")

        jvm_plugin = getattr(self, "jvm_plugin", None)
        if jvm_plugin is not None:
            jvm_plugin.klass = None


# === EMDEDDED DEX BEGIN ===
# === EMDEDDED DEX END ===
