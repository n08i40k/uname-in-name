# fmt: off
from android.webkit import ValueCallback
from java import dynamic_proxy
from org.telegram.ui.ActionBar import AlertDialog
from client_utils import get_last_fragment
from ui.bulletin import BulletinHelper
from android_utils import run_on_ui_thread, copy_to_clipboard
import traceback
from android.util import Log
import threading
from ui.settings import Header, Text
from base_plugin import MenuItemType, MenuItemData, BasePlugin
from org.telegram.messenger import ApplicationLoader, LocaleController
from java.nio import ByteBuffer
from dalvik.system import InMemoryDexClassLoader
import os
import base64
import lzma
from java.lang import Class, String, Long
from typing import Optional, Any, cast

__id__ = "exteragram-plugin-template"
__name__ = "exteraGram plugin template"
__description__ = "Шаблон плагина exteraGram с DEX, встроенным прямо в исходник"
__author__ = "@n08i40k_extera"
__version__ = "0.0.0"
__min_version__ = "12.1.1"

LOGCAT_TAG = __id__

JVM_PLUGIN_CLASS = "ru.n08i40k.template.Plugin"

DEX_COMMENT_BEGIN = "# === EMDEDDED DEX BEGIN ==="
DEX_COMMENT_END = "# === EMDEDDED DEX END ==="


I18N_SETTINGS: dict[str, dict[str, str]] = {
    "settings.example.title": {
        "en": "Example button in plugin settings",
        "ru": "Пример кнопки в меню настроек плагина",
    },
}

I18N_MENU: dict[str, dict[str, str]] = {
    "menu.chat.example.title": {
        "en": "Example action",
        "ru": "Пример действия",
    },
    "menu.chat.example.description": {
        "en": "Example button in chat context menu",
        "ru": "Пример кнопки в контекстном меню чата",
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
    "status.error.chat.detect_current_failed": {
        "en": "Failed to detect the current chat",
        "ru": "Не удалось определить текущий чат",
    },
    "status.error.dex.missing": {
        "en": "Plugin engine is missing from the source file",
        "ru": "Движок плагина отсутствует в файле плагина",
    },
}

I18N_STRINGS: dict[str, dict[str, str]] = {
    **I18N_SETTINGS,
    **I18N_MENU,
    **I18N_DIALOG,
    **I18N_STATUS,
}

# fmt: on


def _as_dialog_id(value: Any) -> Optional[int]:
    try:
        return int(value) or None
    except Exception:
        return None


def _dialog_id_of(obj: Any) -> Optional[int]:
    try:
        return _as_dialog_id(obj.getDialogId())
    except Exception:
        return None


class JvmPluginBridge:
    """Loads classes.dex embedded (as a base64 comment) into this very .py file."""

    klass: Optional[Class]

    def __init__(self, plugin: "TemplatePlugin"):
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


class ChatContextMenu:
    """Chat context menu items. Keys must match ChatContextMenuButton on the DEX side."""

    EXAMPLE = "example"

    MENU_ITEMS: tuple[dict[str, Any], ...] = (
        {
            "key": EXAMPLE,
            "text_key": "menu.chat.example.title",
            "subtext_key": "menu.chat.example.description",
            "icon": "msg_settings",
            "priority": 1000,
        },
    )

    # the payload extera hands to on_click is either the chat fragment itself or
    # a mapping that carries the dialog id (or the fragment) under one of these keys
    PAYLOAD_DIALOG_KEYS = ("dialog_id", "dialogId")
    PAYLOAD_FRAGMENT_KEYS = ("chatActivity", "fragment")

    def __init__(self, plugin: "TemplatePlugin"):
        self.plugin = plugin
        self._item_ids: dict[str, str] = {}

    def register(self):
        self.unregister()

        for item in self.MENU_ITEMS:
            key: str = item["key"]

            try:
                item_id = self.plugin.add_menu_item(
                    MenuItemData(
                        menu_type=MenuItemType.CHAT_ACTION_MENU,
                        text=self.plugin._t(item["text_key"]),
                        subtext=self.plugin._t(item["subtext_key"]),
                        icon=item["icon"],
                        on_click=lambda payload, button=key: self._on_click(
                            button, payload
                        ),
                        priority=item["priority"],
                    )
                )

                self._item_ids[key] = str(item_id)
            except Exception as e:
                self.plugin.log_exception(
                    f"Failed to register chat context menu item {key}",
                    e,
                )

    def unregister(self):
        for key, item_id in tuple(self._item_ids.items()):
            try:
                self.plugin.remove_menu_item(item_id)
            except Exception as e:
                self.plugin.log_exception(
                    f"Failed to remove chat context menu item {key}",
                    e,
                )

        self._item_ids.clear()

    def _on_click(self, key: str, payload: Any):
        dialog_id = self._extract_dialog_id(payload)
        if dialog_id is None:
            self.plugin.log(
                f"Chat context menu click payload missing dialog id for {key}: {payload}"
            )
            self.plugin._show_error(
                self.plugin._t("status.error.chat.detect_current_failed")
            )
            return

        try:
            self.plugin.jvm_plugin.call(
                "invokeChatContextMenuCallback",
                String(key),
                Long(dialog_id),
                types=(String.getClass(), Long.TYPE),
            )
        except Exception as e:
            self.plugin.log_exception(
                f"Failed to execute chat context menu callback {key} for {dialog_id}",
                e,
            )

    def _extract_dialog_id(self, payload: Any) -> Optional[int]:
        getter = getattr(payload, "get", None)
        if getter is None:
            return _dialog_id_of(payload)

        for key in self.PAYLOAD_DIALOG_KEYS:
            if (dialog_id := _as_dialog_id(getter(key))) is not None:
                return dialog_id

        for key in self.PAYLOAD_FRAGMENT_KEYS:
            if (dialog_id := _dialog_id_of(getter(key))) is not None:
                return dialog_id

        return _dialog_id_of(payload)


class SettingsActions:
    """Plugin settings items. Keys must match SettingsActionButton on the DEX side."""

    EXAMPLE = "example"

    def __init__(self, plugin: "TemplatePlugin"):
        self.plugin = plugin

    def build_settings(self) -> list[Any]:
        return [
            Header(text=self.plugin._t("settings.example.title")),
            Text(
                text=self.plugin._t("settings.example.title"),
                icon="msg_settings",
                on_click=lambda _: self._on_click(self.EXAMPLE),
            ),
        ]

    def _on_click(self, key: str):
        try:
            self.plugin.jvm_plugin.call(
                "invokeSettingsActionCallback",
                String(key),
                types=(String.getClass(),),
            )
        except Exception as e:
            self.plugin.log_exception(
                f"Failed to execute settings callback {key}",
                e,
            )


class TemplatePlugin(BasePlugin):
    _full_load_lock = threading.Lock()
    _eject_lock = threading.Lock()

    _load_logging_active = False
    _load_log_buffer: list[str] = []
    _full_load_started = False
    _ejected = False

    jvm_plugin: JvmPluginBridge
    chat_context_menu: Optional[ChatContextMenu] = None

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

    def _register_ui(self):
        self.chat_context_menu = ChatContextMenu(self)
        self.chat_context_menu.register()

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
            ("register ui", self._register_ui),
            ("finalizeInject", self._finalize_jvm_plugin_inject),
        ):
            try:
                action()
            except BaseException as e:
                self._handle_load_failure(stage, e)
                self.on_plugin_eject()
                return

        self._stop_load_logging()

    def _unregister_chat_context_menu(self, reason: str):
        if self.chat_context_menu is None:
            return

        try:
            self.chat_context_menu.unregister()
        except Exception as e:
            self.log_exception(f"Failed to unregister chat context menu ({reason})", e)

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

        self._unregister_chat_context_menu("unload")

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

        self._unregister_chat_context_menu("eject")

        jvm_plugin = getattr(self, "jvm_plugin", None)
        if jvm_plugin is not None:
            jvm_plugin.klass = None


# === EMDEDDED DEX BEGIN ===
# === EMDEDDED DEX END ===
