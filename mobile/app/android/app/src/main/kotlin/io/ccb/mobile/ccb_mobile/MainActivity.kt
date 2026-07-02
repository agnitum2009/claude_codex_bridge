package io.ccb.mobile.ccb_mobile

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Build
import com.google.android.gms.common.api.CommonStatusCodes
import com.google.mlkit.vision.barcode.common.Barcode as MlKitBarcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import com.google.zxing.BinaryBitmap
import com.google.zxing.DecodeHintType
import com.google.zxing.MultiFormatReader
import com.google.zxing.RGBLuminanceSource
import com.google.zxing.BarcodeFormat as ZxingBarcodeFormat
import com.google.zxing.common.HybridBinarizer
import com.google.zxing.integration.android.IntentIntegrator
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private var localNotificationsChannel: MethodChannel? = null
    private var pendingNotificationTapPayload: String? = null
    private var notificationTapHandlerReady = false
    private var pendingPermissionResult: MethodChannel.Result? = null
    private var pendingPairingScanResult: MethodChannel.Result? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "io.ccb.mobile/pairing_scanner"
        ).setMethodCallHandler { call, result ->
            when (call.method) {
                "scanPairingQr" -> scanPairingQr(result)
                "scanPairingQrImage" -> {
                    val path = call.argument<String>("path")
                    if (path.isNullOrBlank()) {
                        result.error(
                            "image_decode_failed",
                            "Image path is required.",
                            null
                        )
                        return@setMethodCallHandler
                    }
                    scanPairingQrImage(path, result)
                }
                else -> result.notImplemented()
            }
        }
        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "io.ccb.mobile/external_url"
        ).setMethodCallHandler { call, result ->
            if (call.method != "openUrl") {
                result.notImplemented()
                return@setMethodCallHandler
            }
            val url = call.argument<String>("url")
            if (url.isNullOrBlank()) {
                result.success(false)
                return@setMethodCallHandler
            }
            val uri = Uri.parse(url)
            if (uri.scheme != "http" && uri.scheme != "https") {
                result.success(false)
                return@setMethodCallHandler
            }
            try {
                val intent = Intent(Intent.ACTION_VIEW, uri)
                startActivity(intent)
                result.success(true)
            } catch (_: ActivityNotFoundException) {
                result.success(false)
            } catch (_: SecurityException) {
                result.success(false)
            }
        }
        localNotificationsChannel = MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "io.ccb.mobile/local_notifications"
        ).also { channel ->
            channel.setMethodCallHandler { call, result ->
                when (call.method) {
                    "registerNotificationTapHandler" -> {
                        notificationTapHandlerReady = true
                        dispatchPendingNotificationTap()
                        result.success(true)
                    }
                    "requestPostNotificationsPermission" -> {
                        requestPostNotificationsPermission(result)
                    }
                    "showTaskCompletion" -> {
                        val notificationId = call.argument<Int>("notification_id")
                        val channelId = call.argument<String>("channel_id")
                        val title = call.argument<String>("title")
                        val body = call.argument<String>("body")
                        val payload = call.argument<String>("payload")
                        if (notificationId == null ||
                            channelId.isNullOrBlank() ||
                            title.isNullOrBlank() ||
                            body.isNullOrBlank() ||
                            payload.isNullOrBlank()
                        ) {
                            result.success(false)
                            return@setMethodCallHandler
                        }
                        result.success(
                            showTaskCompletionNotification(
                                notificationId,
                                channelId,
                                title,
                                body,
                                payload
                            )
                        )
                    }
                    else -> result.notImplemented()
                }
            }
        }
        dispatchNotificationTap(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        dispatchNotificationTap(intent)
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != postNotificationsRequestCode) {
            if (requestCode == pairingCameraRequestCode) {
                val granted = grantResults.isNotEmpty() &&
                    grantResults[0] == PackageManager.PERMISSION_GRANTED
                if (granted) {
                    startZxingPairingScan()
                } else {
                    completePairingScanError(
                        "scanner_unavailable",
                        "Camera permission denied."
                    )
                }
            }
            return
        }
        val granted = grantResults.isNotEmpty() &&
            grantResults[0] == PackageManager.PERMISSION_GRANTED
        pendingPermissionResult?.success(granted)
        pendingPermissionResult = null
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        val scanResult = IntentIntegrator.parseActivityResult(requestCode, resultCode, data)
        if (scanResult != null && pendingPairingScanResult != null) {
            completePairingScan(scanResult.contents)
            return
        }
        super.onActivityResult(requestCode, resultCode, data)
    }

    private fun scanPairingQr(result: MethodChannel.Result) {
        if (pendingPairingScanResult != null) {
            result.error("scanner_busy", "Scanner is already open.", null)
            return
        }
        pendingPairingScanResult = result
        val options = GmsBarcodeScannerOptions.Builder()
            .setBarcodeFormats(MlKitBarcode.FORMAT_QR_CODE)
            .enableAutoZoom()
            .build()
        val scanner = GmsBarcodeScanning.getClient(this, options)
        scanner.startScan()
            .addOnSuccessListener { barcode ->
                completePairingScan(barcode.rawValue)
            }
            .addOnCanceledListener {
                completePairingScan(null)
            }
            .addOnFailureListener { error ->
                if (gmsFailureShouldFallback(error)) {
                    startZxingPairingScan()
                } else {
                    completePairingScanError(
                        "scanner_unavailable",
                        error.message ?: "Google scanner could not be opened."
                    )
                }
            }
    }

    private fun gmsFailureShouldFallback(error: Exception): Boolean {
        val statusCode = if (error is com.google.android.gms.common.api.ApiException) {
            error.statusCode
        } else {
            null
        }
        return statusCode == null ||
            statusCode == CommonStatusCodes.ERROR ||
            statusCode == CommonStatusCodes.API_NOT_CONNECTED ||
            statusCode == CommonStatusCodes.DEVELOPER_ERROR ||
            statusCode == CommonStatusCodes.INTERNAL_ERROR
    }

    private fun startZxingPairingScan() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M &&
            checkSelfPermission(Manifest.permission.CAMERA) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(
                arrayOf(Manifest.permission.CAMERA),
                pairingCameraRequestCode
            )
            return
        }
        try {
            IntentIntegrator(this).apply {
                setCaptureActivity(CcbZxingCaptureActivity::class.java)
                setDesiredBarcodeFormats(IntentIntegrator.QR_CODE)
                setPrompt("Scan the CCB mobile pairing QR code")
                setBeepEnabled(false)
                setOrientationLocked(true)
                setBarcodeImageEnabled(false)
            }.initiateScan()
        } catch (error: ActivityNotFoundException) {
            completePairingScanError(
                "scanner_unavailable",
                error.message ?: "Embedded scanner could not be opened."
            )
        } catch (error: SecurityException) {
            completePairingScanError(
                "scanner_unavailable",
                error.message ?: "Camera permission denied."
            )
        } catch (error: RuntimeException) {
            completePairingScanError(
                "scanner_unavailable",
                error.message ?: "Embedded scanner could not be opened."
            )
        }
    }

    private fun scanPairingQrImage(path: String, result: MethodChannel.Result) {
        try {
            val bitmap = BitmapFactory.decodeFile(path)
            if (bitmap == null) {
                result.error("image_decode_failed", "Image could not be decoded.", null)
                return
            }
            val width = bitmap.width
            val height = bitmap.height
            val pixels = IntArray(width * height)
            bitmap.getPixels(pixels, 0, width, 0, 0, width, height)
            val source = RGBLuminanceSource(width, height, pixels)
            val binaryBitmap = BinaryBitmap(HybridBinarizer(source))
            val reader = MultiFormatReader().apply {
                setHints(
                    mapOf(
                        DecodeHintType.POSSIBLE_FORMATS to listOf(
                            ZxingBarcodeFormat.QR_CODE
                        ),
                        DecodeHintType.TRY_HARDER to true
                    )
                )
            }
            result.success(reader.decodeWithState(binaryBitmap).text)
        } catch (_: com.google.zxing.NotFoundException) {
            result.success(null)
        } catch (error: RuntimeException) {
            result.error(
                "image_decode_failed",
                error.message ?: "Image could not be decoded.",
                null
            )
        }
    }

    private fun completePairingScan(rawValue: String?) {
        val result = pendingPairingScanResult ?: return
        pendingPairingScanResult = null
        result.success(rawValue)
    }

    private fun completePairingScanError(code: String, message: String) {
        val result = pendingPairingScanResult ?: return
        pendingPairingScanResult = null
        result.error(code, message, null)
    }

    private fun requestPostNotificationsPermission(result: MethodChannel.Result) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
            result.success(true)
            return
        }
        if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED
        ) {
            result.success(true)
            return
        }
        pendingPermissionResult?.success(false)
        pendingPermissionResult = result
        requestPermissions(
            arrayOf(Manifest.permission.POST_NOTIFICATIONS),
            postNotificationsRequestCode
        )
    }

    private fun showTaskCompletionNotification(
        notificationId: Int,
        channelId: String,
        title: String,
        body: String,
        payload: String
    ): Boolean {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(
                NotificationChannel(
                    channelId,
                    "CCB task completion",
                    NotificationManager.IMPORTANCE_DEFAULT
                )
            )
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            return false
        }
        val tapIntent = Intent(this, MainActivity::class.java).apply {
            action = notificationTapAction
            flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
            putExtra(notificationPayloadExtra, payload)
        }
        val pendingIntent = taskCompletionPendingIntent(notificationId, tapIntent)
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, channelId)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }
        val notification = builder
            .setSmallIcon(applicationInfo.icon)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(Notification.BigTextStyle().bigText(body))
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .setGroup(taskCompletionNotificationGroupKey)
            .build()
        return try {
            manager.notify(notificationId, notification)
            manager.notify(
                taskCompletionSummaryNotificationTag,
                taskCompletionSummaryNotificationId,
                taskCompletionSummaryNotification(channelId, title, body, payload)
            )
            true
        } catch (_: SecurityException) {
            false
        }
    }

    private fun taskCompletionSummaryNotification(
        channelId: String,
        title: String,
        body: String,
        payload: String
    ): Notification {
        val tapIntent = Intent(this, MainActivity::class.java).apply {
            action = notificationTapAction
            flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
            putExtra(notificationPayloadExtra, payload)
        }
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, channelId)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            builder.setGroupAlertBehavior(Notification.GROUP_ALERT_CHILDREN)
        }
        return builder
            .setSmallIcon(applicationInfo.icon)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(
                Notification.InboxStyle()
                    .addLine(body)
                    .setSummaryText("Tasks completed")
            )
            .setAutoCancel(true)
            .setContentIntent(
                taskCompletionPendingIntent(
                    taskCompletionSummaryNotificationId,
                    tapIntent
                )
            )
            .setGroup(taskCompletionNotificationGroupKey)
            .setGroupSummary(true)
            .build()
    }

    private fun taskCompletionPendingIntent(
        requestCode: Int,
        intent: Intent
    ): PendingIntent {
        intent.data = Uri.parse("ccb-mobile://task-completion/$requestCode")
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                PendingIntent.FLAG_IMMUTABLE
            } else {
                0
            }
        return PendingIntent.getActivity(this, requestCode, intent, flags)
    }

    private fun dispatchNotificationTap(intent: Intent?) {
        if (intent?.action != notificationTapAction) {
            return
        }
        val payload = intent.getStringExtra(notificationPayloadExtra) ?: return
        pendingNotificationTapPayload = payload
        dispatchPendingNotificationTap()
        intent.removeExtra(notificationPayloadExtra)
    }

    private fun dispatchPendingNotificationTap() {
        val payload = pendingNotificationTapPayload ?: return
        val channel = localNotificationsChannel ?: return
        if (!notificationTapHandlerReady) {
            return
        }
        channel.invokeMethod("notificationTap", payload)
        pendingNotificationTapPayload = null
    }

    override fun onResume() {
        super.onResume()
        dispatchPendingNotificationTap()
    }

    companion object {
        private const val pairingCameraRequestCode = 4206
        private const val postNotificationsRequestCode = 4207
        private const val taskCompletionSummaryNotificationId = 2147483646
        private const val taskCompletionSummaryNotificationTag =
            "ccb_task_completion_summary"
        private const val taskCompletionNotificationGroupKey =
            "io.ccb.mobile.ccb_mobile.TASK_COMPLETION_NOTIFICATIONS"
        private const val notificationTapAction =
            "io.ccb.mobile.ccb_mobile.TASK_COMPLETION_NOTIFICATION_TAP"
        private const val notificationPayloadExtra =
            "io.ccb.mobile.ccb_mobile.TASK_COMPLETION_NOTIFICATION_PAYLOAD"
    }
}
