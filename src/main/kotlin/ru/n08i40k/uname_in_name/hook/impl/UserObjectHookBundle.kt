package ru.n08i40k.uname_in_name.hook.impl

import org.telegram.messenger.UserObject
import org.telegram.tgnet.TLRPC
import ru.n08i40k.uname_in_name.Plugin
import ru.n08i40k.uname_in_name.hook.HookBundle
import ru.n08i40k.uname_in_name.hook.InstallHook

class UserObjectHookBundle : HookBundle() {
    override fun inject(before: InstallHook, after: InstallHook) {
        fun fmt(user: TLRPC.User, source: String): String {
            val template = Plugin.getInstance().template

            if (user.username != null && user.username.isNotEmpty()) {
                return template
                    .replace("{o}", source)
                    .replace("{u}", user.username)
            }

            if (user.usernames.isNotEmpty()) {
                return template
                    .replace("{o}", source)
                    .replace("{u}", user.usernames[0].username)
            }

            return source
        }

        after(
            UserObject::class.java.getDeclaredMethod(
                "getUserName",
                TLRPC.User::class.java,
            )
        ) { param ->
            val user = param.args[0] as? TLRPC.User
                ?: return@after

            param.result = fmt(user, param.result as String)
        }

        after(
            UserObject::class.java.getDeclaredMethod(
                "getFirstName",
                TLRPC.User::class.java,
                Boolean::class.java
            )
        ) { param ->
            val user = param.args[0] as? TLRPC.User
                ?: return@after

            param.result = fmt(user, param.result as String)
        }
    }
}
