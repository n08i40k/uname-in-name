package ru.n08i40k.template.hook


abstract class HookBundle {
    abstract fun inject(before: InstallHook, after: InstallHook)
}