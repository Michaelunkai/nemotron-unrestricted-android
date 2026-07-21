package com.michaelovsky.nemotronunrestricted.isolated;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.util.Log;

public final class BootReceiver extends BroadcastReceiver {
    private static final String TAG = "NemotronBootReceiver";

    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent != null ? intent.getAction() : null;
        if (!Intent.ACTION_BOOT_COMPLETED.equals(action)
                && !Intent.ACTION_MY_PACKAGE_REPLACED.equals(action))
            return;
        Log.i(TAG, "Received boot event: " + action);
        Intent service = new Intent(context, NemotronRuntimeService.class);
        service.putExtra("reason", "boot-" + action);
        if (Build.VERSION.SDK_INT >= 26)
            context.startForegroundService(service);
        else
            context.startService(service);
    }
}
