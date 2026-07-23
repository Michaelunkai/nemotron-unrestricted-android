package com.michaelovsky.nemotronunrestricted.tools;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.media.FaceDetector;
import java.io.File;

/** Local-only legacy Android face presence detector; it performs no identity inference. */
public final class NemotronFaceDetector {
    private static String escape(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"")
                .replace("\n", "\\n").replace("\r", "\\r");
    }

    private static void emit(String path, int faces, String error) {
        String suffix = error == null ? "" : ",\"error\":\"" + escape(error) + "\"";
        System.out.println("{\"path\":\"" + escape(path) + "\",\"faceCount\":" + faces + suffix + "}");
    }

    public static void main(String[] args) {
        for (String path : args) {
            Bitmap decoded = null;
            Bitmap scaled = null;
            Bitmap compatible = null;
            try {
                File file = new File(path);
                if (!file.isFile() || file.length() <= 0) {
                    emit(path, 0, "unreadable_image");
                    continue;
                }
                BitmapFactory.Options bounds = new BitmapFactory.Options();
                bounds.inJustDecodeBounds = true;
                BitmapFactory.decodeFile(path, bounds);
                if (bounds.outWidth < 2 || bounds.outHeight < 2) {
                    emit(path, 0, "unsupported_image");
                    continue;
                }
                int sample = 1;
                while (bounds.outWidth / sample > 1600 || bounds.outHeight / sample > 1600) sample *= 2;
                BitmapFactory.Options options = new BitmapFactory.Options();
                options.inSampleSize = sample;
                options.inPreferredConfig = Bitmap.Config.RGB_565;
                decoded = BitmapFactory.decodeFile(path, options);
                if (decoded == null) {
                    emit(path, 0, "decode_failed");
                    continue;
                }
                int width = decoded.getWidth() & ~1;
                int height = decoded.getHeight();
                if (width < 2 || height < 2) {
                    emit(path, 0, "image_too_small");
                    continue;
                }
                scaled = width == decoded.getWidth() ? decoded : Bitmap.createBitmap(decoded, 0, 0, width, height);
                compatible = scaled.getConfig() == Bitmap.Config.RGB_565
                        ? scaled : scaled.copy(Bitmap.Config.RGB_565, false);
                FaceDetector.Face[] found = new FaceDetector.Face[64];
                int count = new FaceDetector(compatible.getWidth(), compatible.getHeight(), found.length).findFaces(compatible, found);
                emit(path, Math.max(0, count), null);
            } catch (Throwable error) {
                emit(path, 0, error.getClass().getSimpleName());
            } finally {
                if (compatible != null && compatible != scaled) compatible.recycle();
                if (scaled != null && scaled != decoded) scaled.recycle();
                if (decoded != null) decoded.recycle();
            }
        }
    }
}
