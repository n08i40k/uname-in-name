package ru.n08i40k.uname_in_name.util

import android.content.Intent
import android.net.Uri
import com.exteragram.messenger.plugins.PluginsController
import org.telegram.messenger.AndroidUtilities
import org.telegram.ui.LaunchActivity
import ru.n08i40k.uname_in_name.LogReceiver
import ru.n08i40k.uname_in_name.Plugin
import ru.n08i40k.uname_in_name.constants.TrustedSources
import ru.n08i40k.uname_in_name.extension.format
import java.util.concurrent.ThreadLocalRandom

object Logger {
    private val ID = ThreadLocalRandom.current()
        .nextInt()
        .toHexString(HexFormat {
            upperCase = true

            number {
                minLength = 4
            }
        })
        .take(4)

    @Volatile
    private var receiver: LogReceiver? = null

    @Volatile
    private var suppressFatal = false

    fun setReceiver(receiver: LogReceiver) {
        this.receiver = receiver
    }

    fun info(message: String) {
        try {
            receiver?.onReceiveValue("DEX:$ID $message")
        } catch (_: Throwable) {
            Plugin.eject()
        }
    }

    fun fatal(message: String, exception: Throwable) {
        try {
            receiver?.onReceiveValue("DEX:$ID $message")
            receiver?.onReceiveValue("DEX:$ID ${exception.format()}")
        } catch (_: Throwable) {
            Plugin.eject()
        }

        if (!suppressFatal) {
            AndroidUtilities.addToClipboard(buildReportText(message, exception))
            openChat()

            Plugin.eject()
        }
    }

    fun tryOrFatal(action: String, block: () -> Unit): Unit? =
        try {
            block()
        } catch (e: Throwable) {
            fatal("Failed to $action", e)
            null
        }

    fun onEject() {
        suppressFatal = true

        // logger is notified about eject last
        info("Ejected!")

        receiver = null
    }

    private fun openChat() {
        val context = LaunchActivity.instance.applicationContext

        val intent = Intent().apply {
            action = Intent.ACTION_VIEW
            data = Uri.parse("tg://resolve?domain=${TrustedSources.REPORT_CHAT}&post=999999999") // auto-scroll to the last message
            `package` = context.packageName
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
        }

        context.startActivity(intent)
    }

    private fun buildReportText(message: String, exception: Throwable): String {
        val header = """
            #crash_report

            Reason: `$message`

            ${getClientName()} version: `${getClientVersionName()}`
            Plugin version: `${Plugin.getVersion() ?: "unknown"}`
            Plugin build date: `${Plugin.getBuildDate()}`
        """.trimIndent()

        @Suppress("UNCHECKED_CAST")
        val pluginsList = run {
            val klass = PluginsController::class.java

            val controller = klass
                .getDeclaredMethod("getInstance")
                .invoke(null) as PluginsController

            val plugins = klass.declaredMethods
                .find { it.name == "getPlugins" }
                ?.invoke(controller)
                ?: klass.getField("plugins").get(controller)

            val pluginValues = plugins.javaClass.getDeclaredMethod("values")
                .invoke(plugins) as Collection<com.exteragram.messenger.plugins.Plugin>

            pluginValues
                .filter { it.isEnabled() }
                .map { "— ${it.getName()} by ${it.getAuthor()} (${it.getId()} | ${it.getVersion()})" }
        }

        val plugins =
            "Plugins:\n```\n${pluginsList.joinToString("\n")}\n```"

        val trace = "```\n${exception.format()}\n```"

        return "$header\n\n${plugins}\n\nStack-trace:\n$trace"
    }
}
