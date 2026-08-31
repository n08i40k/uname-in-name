package ru.n08i40k.template

import android.content.Context
import android.content.SharedPreferences
import android.webkit.ValueCallback
import androidx.annotation.AnyThread
import de.comahe.i18n4k.config.I18n4kConfigDefault
import de.comahe.i18n4k.createLocale
import de.comahe.i18n4k.i18n4k
import de.comahe.i18n4k.messages.formatter.MessageFormatterDefault
import de.robv.android.xposed.XC_MethodHook
import de.robv.android.xposed.XposedBridge
import kotlinx.coroutines.CoroutineExceptionHandler
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.job
import kotlinx.coroutines.runBlocking
import org.jetbrains.annotations.Blocking
import org.telegram.messenger.ApplicationLoader
import org.telegram.messenger.LocaleController
import ru.n08i40k.template.event.eject.EjectNotifier
import ru.n08i40k.template.extension.resolveLanguageCode
import ru.n08i40k.template.hook.impl.ExampleHookBundle
import ru.n08i40k.template.i18n.MessagePluralFormatter
import ru.n08i40k.template.registry.LockableActionRegistry
import ru.n08i40k.template.registry.LockableCallbackRegistry
import ru.n08i40k.template.util.Logger
import ru.n08i40k.template.util.RefCounter
import java.lang.reflect.Member
import java.util.function.Supplier
import kotlin.concurrent.thread
import kotlin.time.Instant

typealias LogReceiver = ValueCallback<String>

/**
 * Entry point of the DEX part of the plugin.
 *
 * Every `@JvmStatic` method of the companion object is called reflectively from the
 * Python side, so their names and signatures must stay in sync with the plugin .py.
 */
class Plugin private constructor() {
    @Suppress("unused")
    companion object {
        const val ID = "exteragram-plugin-template"

        private const val HANDLE_KEY = "ru.n08i40k.template.handle"

        @Volatile
        private var WAS_INJECTED = false

        @Volatile
        private var INSTANCE: Plugin? = null

        private var VERSION: String? = null

        fun isInjected(): Boolean = INSTANCE != null

        internal fun getInstance(): Plugin = INSTANCE!!

        @JvmStatic
        fun getBuildDate(): String = Instant
            .fromEpochMilliseconds(BuildConfig.BUILD_TIME.toLong())
            .toString()

        @JvmStatic
        fun getVersion(): String? = VERSION

        @Synchronized
        @Blocking
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

                i18n4k = I18n4kConfigDefault().apply {
                    locale = createLocale(
                        LocaleController
                            .getInstance()
                            .resolveLanguageCode()
                    )
                }
                MessageFormatterDefault.registerMessageValueFormatters(MessagePluralFormatter)

                Logger.tryOrFatal("create and inject plugin") {
                    val plugin = Plugin()
                        .also { INSTANCE = it }

                    plugin.onInject()
                }
            }
        }

        /**
         * Called after [inject] once the Python side has registered its UI. Put here
         * everything that may touch the host UI or needs the plugin to be fully built.
         */
        @Blocking
        @Synchronized
        @JvmStatic
        fun finalizeInject() {
            // safely return as eject was called before finalizeInject
            if (WAS_INJECTED && INSTANCE == null)
                return

            // NPE is a bug, then it should not be silenced
            INSTANCE!!.onFinalizeInject()
        }

        @JvmStatic
        fun invokeChatContextMenuCallback(key: String, id: Long) = with(INSTANCE!!) {
            chatContextMenuCallbackRegistry.get(key).accept(id)
        }

        @JvmStatic
        fun invokeSettingsActionCallback(key: String) = with(INSTANCE!!) {
            settingsActionCallbackRegistry.get(key).run()
        }

        @Synchronized
        private fun ejectSynchronized() {
            Logger.tryOrFatal("Failed to eject plugin") {
                INSTANCE?.onEject()
            }

            INSTANCE = null
        }

        @AnyThread
        private fun ejectPromise(): Thread =
            thread(
                contextClassLoader = Plugin::class.java.classLoader,
                block = ::ejectSynchronized
            )

        @AnyThread
        @JvmStatic
        fun eject() {
            ejectPromise()
        }

        @AnyThread
        @JvmStatic
        fun getSharedPrefs(): SharedPreferences =
            ApplicationLoader.applicationContext.getSharedPreferences(
                ID,
                Context.MODE_PRIVATE
            )

        fun coroutineScope(): CoroutineScope =
            INSTANCE!!.backgroundScope

        fun childCoroutineScope(): CoroutineScope =
            INSTANCE!!.backgroundScope.coroutineContext.let { CoroutineScope(it + SupervisorJob(it.job)) }
    }

    val backgroundScope =
        CoroutineScope(SupervisorJob() + Dispatchers.IO + CoroutineExceptionHandler { _, exception ->
            Logger.fatal("An unknown error occurred in background coroutine scope", exception)
        })

    // installed hooks, unhooked on eject
    val hooks: ArrayList<XC_MethodHook.Unhook> = arrayListOf()

    // callbacks invoked from the Python side
    internal val chatContextMenuCallbackRegistry = LockableCallbackRegistry()
    internal val settingsActionCallbackRegistry = LockableActionRegistry()

    private fun onInject() {
        ChatContextMenuActions(this).register()
        SettingsMenuActions(this).register()

        Logger.info("Injected!")
    }

    private fun onFinalizeInject() {
        Logger.tryOrFatal(
            "hook methods",
            ::hookMethods
        )

        Logger.info("Inject finalized!")
    }

    @Blocking
    private fun onEject() {
        Logger.info("onEject called!")

        hooks.forEach {
            Logger.tryOrFatal(
                "unhook method ${it.hookedMethod}",
                it::unhook
            )
        }
        hooks.clear()

        backgroundScope.cancel()

        Logger.info("Waiting for background coroutines to finish..")
        runBlocking { backgroundScope.coroutineContext.job.join() }
        Logger.info("Background coroutines finished!")

        // released after every other eject subscriber is notified
        EjectNotifier.subscribe(999) {
            Logger.info("Waiting for ref counter to be zero..")
            runBlocking { RefCounter.wait() }
            Logger.info("No more refs from other threads!")
        }

        EjectNotifier.fire()
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
            ExampleHookBundle(),
        )

        bundles.forEach { it.inject(::before, ::after) }
    }
}
