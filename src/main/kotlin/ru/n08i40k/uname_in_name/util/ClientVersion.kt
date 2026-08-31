package ru.n08i40k.uname_in_name.util

import android.content.pm.PackageInfo
import com.exteragram.messenger.utils.text.LocaleUtils
import org.telegram.messenger.ApplicationLoader

fun getClientName(): String = LocaleUtils.getAppName()

private fun packageInfo(): PackageInfo =
    with(ApplicationLoader.applicationContext) { packageManager.getPackageInfo(packageName, 0) }

fun getClientVersionName(): String =
    packageInfo().versionName ?: "unknown"
