package ru.n08i40k.uname_in_name.hook.impl

import android.graphics.drawable.Drawable
import org.telegram.messenger.AndroidUtilities
import org.telegram.ui.Cells.ChatMessageCell
import ru.n08i40k.uname_in_name.Plugin
import ru.n08i40k.uname_in_name.hook.HookBundle
import ru.n08i40k.uname_in_name.hook.InstallHook
import java.lang.reflect.Field

class ChatMessageCellHookBundle : HookBundle() {
    private companion object {
        val NAME_LAYOUT_SELECTOR_FIELD: Field by lazy {
            ChatMessageCell::class.java.getDeclaredField("nameLayoutSelector")
                .apply { isAccessible = true }
        }
    }

    override fun inject(
        before: InstallHook,
        after: InstallHook
    ) {
        before(
            ChatMessageCell::class.java
                .getDeclaredMethod("onLongPress")
        ) { param ->
            if (!Plugin.getInstance().doCopyOnLongPress)
                return@before

            val cell = param.thisObject as ChatMessageCell

            val currentUser = cell.currentUser
                ?: return@before

            val username = currentUser.username.takeUnless(String::isNullOrBlank)
                ?: currentUser.usernames
                    .takeUnless(Collection<*>::isEmpty)
                    ?.get(0)
                    ?.username
                    ?.takeUnless(String::isNullOrBlank)
                ?: return@before

            val nameLayoutSelector =
                NAME_LAYOUT_SELECTOR_FIELD
                    .get(cell) as? Drawable?
                    ?: return@before

            val pressed = nameLayoutSelector.bounds
                .contains(cell.lastTouchX.toInt(), cell.lastTouchY.toInt())

            if (!pressed)
                return@before

            param.result = true

            AndroidUtilities.addToClipboard("@$username")
        }
    }
}