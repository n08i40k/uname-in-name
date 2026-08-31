package ru.n08i40k.template

import ru.n08i40k.template.constants.SettingsActionButton
import ru.n08i40k.template.i18n.Strings
import ru.n08i40k.template.util.BulletinHelper
import ru.n08i40k.template.util.Logger

/**
 * Handlers of the plugin settings buttons declared on the Python side.
 * Every key must match the one used in the plugin .py.
 */
class SettingsMenuActions(private val plugin: Plugin) {
    fun register() = with(plugin) {
        fun add(key: String, callback: () -> Unit) {
            settingsActionCallbackRegistry.register(key) {
                Logger.tryOrFatal("handle settings action touch") { callback() }
            }
        }

        add(SettingsActionButton.EXAMPLE) {
            Logger.info("[Settings] Example clicked")

            BulletinHelper.show(Strings.status_info_example_settings_action())
        }

        settingsActionCallbackRegistry.freeze()
    }
}
