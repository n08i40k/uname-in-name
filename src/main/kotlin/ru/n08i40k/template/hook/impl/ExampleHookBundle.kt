package ru.n08i40k.template.hook.impl

import org.telegram.ui.LaunchActivity
import ru.n08i40k.template.hook.HookBundle
import ru.n08i40k.template.hook.InstallHook
import ru.n08i40k.template.util.Logger

/**
 * Example of a hook bundle: every bundle receives the [InstallHook] helpers and
 * registers as many hooks as it needs. Unhooking is handled by [ru.n08i40k.template.Plugin].
 */
class ExampleHookBundle : HookBundle() {
    override fun inject(before: InstallHook, after: InstallHook) {
        val onResume = LaunchActivity::class.java.declaredMethods
            .firstOrNull { it.name == "onResume" && it.parameterCount == 0 }

        if (onResume == null) {
            Logger.info("LaunchActivity.onResume not found, example hook skipped")
            return
        }

        after(onResume) {
            Logger.info("LaunchActivity resumed")
        }
    }
}
