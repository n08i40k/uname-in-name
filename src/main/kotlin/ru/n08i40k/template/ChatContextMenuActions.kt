package ru.n08i40k.template

import ru.n08i40k.template.constants.ChatContextMenuButton
import ru.n08i40k.template.i18n.Strings
import ru.n08i40k.template.util.BulletinHelper
import ru.n08i40k.template.util.Logger

/**
 * Handlers of the chat context menu items declared on the Python side.
 * Every key must match the one used in the plugin .py.
 */
class ChatContextMenuActions(private val plugin: Plugin) {
    fun register() = with(plugin) {
        fun add(key: String, callback: (Long) -> Unit) {
            chatContextMenuCallbackRegistry.register(key) {
                Logger.tryOrFatal("handle context menu entry touch") {
                    callback(it)
                }
            }
        }

        add(ChatContextMenuButton.EXAMPLE) { peerId ->
            Logger.info("[Context Menu] Example clicked for $peerId")

            BulletinHelper.show(Strings.status_info_example_chat_action(peerId))
        }

        chatContextMenuCallbackRegistry.freeze()
    }
}
