package ru.n08i40k.uname_in_name

import android.webkit.ValueCallback
import de.robv.android.xposed.XC_MethodHook
import de.robv.android.xposed.XposedBridge
import ru.n08i40k.uname_in_name.hook.impl.ChatMessageCellHookBundle
import ru.n08i40k.uname_in_name.hook.impl.UserObjectHookBundle
import ru.n08i40k.uname_in_name.util.Logger
import java.lang.reflect.Member
import java.util.function.Supplier
import kotlin.concurrent.thread
import kotlin.time.Instant

typealias LogReceiver = ValueCallback<String>

class Plugin private constructor() {
    @Suppress("unused")
    companion object {
        private const val HANDLE_KEY = "ru.n08i40k.uname_in_name.handle"

        @Volatile
        private var WAS_INJECTED = false

        @Volatile
        private var INSTANCE: Plugin? = null

        private var VERSION: String? = null

        internal fun getInstance(): Plugin = INSTANCE!!

        @JvmStatic
        fun getBuildDate(): String = Instant
            .fromEpochMilliseconds(BuildConfig.BUILD_TIME)
            .toString()

        @JvmStatic
        fun getVersion(): String? = VERSION

        @Synchronized
        @JvmStatic
        fun inject(
            version: String,
            logReceiver: LogReceiver,
        ) {
            if (INSTANCE != null)
                return

            if (WAS_INJECTED)
                throw IllegalStateException("Cannot inject plugin from same class-loader twice")

            VERSION = version
            WAS_INJECTED = true

            Logger.setReceiver(logReceiver)

            val props = System.getProperties()

            // prevent two plugin injects concurrently (from different class-loaders)
            synchronized(props) {
                @Suppress("UNCHECKED_CAST")
                (props.put(HANDLE_KEY, Supplier { ejectPromise() }) as? Supplier<Thread>)
                    ?.apply {
                        Logger.info("Plugin is probably injected in different class loader!")

                        Logger.info("Ejecting old plugin...")
                        get().join()
                    }

                Logger.tryOrFatal("create and inject plugin") {
                    val plugin = Plugin()
                        .also { INSTANCE = it }

                    plugin.onInject()
                }
            }
        }

        @JvmStatic
        fun setFormattingTemplate(template: String) {
            INSTANCE?.template = template
        }

        @JvmStatic
        fun setCopyOnLongPress(value: Boolean) {
            INSTANCE?.doCopyOnLongPress = value
        }

        @Synchronized
        @JvmStatic
        fun finalizeInject() {
            // safely return as eject was called before finalizeInject
            if (WAS_INJECTED && INSTANCE == null)
                return

            // NPE is a bug, then it should not be silenced
            INSTANCE!!.onFinalizeInject()
        }

        @Synchronized
        private fun ejectSynchronized() {
            Logger.tryOrFatal("Failed to eject plugin") {
                INSTANCE?.onEject()
            }

            INSTANCE = null
        }

        private fun ejectPromise(): Thread =
            thread(
                contextClassLoader = Plugin::class.java.classLoader,
                block = ::ejectSynchronized
            )

        @JvmStatic
        fun eject() {
            ejectPromise()
        }
    }


    // installed hooks, unhooked on eject
    private val hooks: ArrayList<XC_MethodHook.Unhook> = arrayListOf()

    var template: String = "{o} | @{u}"
    var doCopyOnLongPress: Boolean = true

    private fun onInject() {
        Logger.info("Injected!")
    }

    private fun onFinalizeInject() {
        Logger.tryOrFatal(
            "hook methods",
            ::hookMethods
        )

        Logger.info("Inject finalized!")
    }

    private fun onEject() {
        Logger.info("onEject called!")

        hooks.forEach {
            Logger.tryOrFatal(
                "unhook method ${it.hookedMethod}",
                it::unhook
            )
        }
        hooks.clear()

        Logger.onEject()
    }

    private fun hookMethods() {
        fun add(method: Member, hook: XC_MethodHook) {
            hooks.add(XposedBridge.hookMethod(method, hook))
        }

        fun before(method: Member, callback: (XC_MethodHook.MethodHookParam) -> Unit) {
            add(
                method,
                object : XC_MethodHook() {
                    override fun beforeHookedMethod(param: MethodHookParam) {
                        Logger.tryOrFatal("run $method before-call hook") { callback(param) }
                    }
                }
            )
        }

        fun after(method: Member, callback: (XC_MethodHook.MethodHookParam) -> Unit) {
            add(
                method,
                object : XC_MethodHook() {
                    override fun afterHookedMethod(param: MethodHookParam) {
                        Logger.tryOrFatal("run $method after-call hook") { callback(param) }
                    }
                }
            )
        }

        val bundles = listOf(
            ChatMessageCellHookBundle(),
            UserObjectHookBundle(),
        )

        bundles.forEach { it.inject(::before, ::after) }
    }
}
