package ru.n08i40k.template.util

import ru.n08i40k.template.LogReceiver
import ru.n08i40k.template.Plugin
import ru.n08i40k.template.event.eject.EjectNotifier
import ru.n08i40k.template.extension.format
import java.util.concurrent.ThreadLocalRandom

object Logger : EjectNotifier.Delegate {
    init {
        EjectNotifier.subscribe(this, priority = 1000)
    }

    // distinguishes log lines of plugin instances loaded from different class loaders
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

    fun fatal(message: String, exception: Throwable, preventEject: Boolean = false) {
        try {
            receiver?.onReceiveValue("DEX:$ID $message")
            receiver?.onReceiveValue("DEX:$ID ${exception.format()}")
        } catch (_: Throwable) {
            Plugin.eject()
        }

        if (!suppressFatal && !preventEject)
            Plugin.eject()
    }

    fun tryOrFatal(action: String, block: () -> Unit): Unit? =
        try {
            block()
        } catch (e: Throwable) {
            fatal("Failed to $action", e)
            null
        }

    override fun onEject() {
        suppressFatal = true

        // logger is notified about eject last
        info("Ejected!")

        receiver = null
    }
}
