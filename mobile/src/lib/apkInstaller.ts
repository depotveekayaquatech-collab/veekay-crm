/**
 * Downloads the new APK inside the app and opens Android's installer for it.
 *
 * Safety: only an https link from the version file is used; the file is refused if its size does not match the size the
 * release script recorded; and Android itself refuses to install an APK that is not signed with the same key as the
 * installed app, so a tampered file can never replace it. Android always asks the person to confirm the install.
 * Any failure here is reported to the caller, which falls back to opening the link in the browser.
 */
import { File, Paths } from "expo-file-system";
import { getContentUriAsync } from "expo-file-system/legacy";
import * as IntentLauncher from "expo-intent-launcher";
import type { ApkManifest } from "@/lib/versionPolicy";

const APK_MIME = "application/vnd.android.package-archive";
const FLAG_GRANT_READ_URI_PERMISSION = 1;
const FALLBACK_NEEDED_BYTES = 150 * 1024 * 1024;

export class InstallError extends Error {}

/** Free space needed: the APK plus room for Android to unpack it. */
export function neededBytes(manifest: Pick<ApkManifest, "apkSizeBytes">): number {
  return manifest.apkSizeBytes > 0 ? Math.round(manifest.apkSizeBytes * 2.2) : FALLBACK_NEEDED_BYTES;
}

export async function downloadAndInstall(
  manifest: ApkManifest,
  onProgress: (percent: number | null) => void,
  signal?: AbortSignal,
): Promise<void> {
  if (!manifest.downloadUrl.startsWith("https://")) throw new InstallError("The update link is not secure.");
  if (Paths.availableDiskSpace < neededBytes(manifest)) {
    throw new InstallError("There is not enough free space on this phone to download the update. Free some space and try again.");
  }

  const dest = new File(Paths.cache, "veekay-update.apk");
  if (dest.exists) dest.delete();

  const task = File.createDownloadTask(manifest.downloadUrl, dest, {
    signal,
    onProgress: ({ bytesWritten, totalBytes }) => onProgress(totalBytes > 0 ? Math.min(100, Math.round((bytesWritten / totalBytes) * 100)) : null),
  });
  const file = await task.downloadAsync();
  if (!file) throw new InstallError("The download was interrupted.");

  // A link that returns a web page (for example a "sign in" or "virus scan" page) is far smaller than an APK.
  const size = file.size ?? 0;
  if (size < 5 * 1024 * 1024) {
    file.delete();
    throw new InstallError("The download link did not give the app file.");
  }
  if (manifest.apkSizeBytes > 0 && size !== manifest.apkSizeBytes) {
    file.delete();
    throw new InstallError("The downloaded file is incomplete. Please try again.");
  }

  onProgress(100);
  const contentUri = await getContentUriAsync(file.uri);
  await IntentLauncher.startActivityAsync("android.intent.action.VIEW", {
    data: contentUri,
    flags: FLAG_GRANT_READ_URI_PERMISSION,
    type: APK_MIME,
  });
}
