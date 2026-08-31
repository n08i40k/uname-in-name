package ru.n08i40k.uname_in_name.hook

abstract class HookBundle {
    abstract fun inject(before: InstallHook, after: InstallHook)
}
