import * as DocumentPicker from "expo-document-picker";
import { File, Paths } from "expo-file-system";
import * as ImagePicker from "expo-image-picker";
import * as Sharing from "expo-sharing";
import { Alert } from "react-native";
import { requestBytes } from "@/api/client";

export interface Picked {
  uri: string;
  name: string;
  type: string;
}

/** Appends a picked file to a multipart form the way React Native expects. */
export function appendFile(form: FormData, field: string, f: Picked) {
  form.append(field, { uri: f.uri, name: f.name, type: f.type } as unknown as Blob);
}

function fromAsset(a: ImagePicker.ImagePickerAsset, i: number): Picked {
  return { uri: a.uri, name: a.fileName ?? `photo-${Date.now()}-${i}.jpg`, type: a.mimeType ?? "image/jpeg" };
}

/** Photos from the system photo picker: needs no storage permission. */
export async function pickPhotos(limit: number): Promise<Picked[]> {
  if (limit <= 0) return [];
  const res = await ImagePicker.launchImageLibraryAsync({
    mediaTypes: ["images"],
    allowsMultipleSelection: limit > 1,
    selectionLimit: limit,
    quality: 0.8,
  });
  return res.canceled ? [] : res.assets.slice(0, limit).map(fromAsset);
}

export async function takePhoto(): Promise<Picked[]> {
  const perm = await ImagePicker.requestCameraPermissionsAsync();
  if (!perm.granted) {
    Alert.alert("Camera is off", "Allow the camera for this app in your phone's settings to take photos, or choose a photo from your gallery instead.");
    return [];
  }
  const res = await ImagePicker.launchCameraAsync({ mediaTypes: ["images"], quality: 0.8 });
  return res.canceled ? [] : res.assets.map(fromAsset);
}

export async function pickPdf(): Promise<Picked[]> {
  const res = await DocumentPicker.getDocumentAsync({ type: "application/pdf", copyToCacheDirectory: true, multiple: false });
  return res.canceled ? [] : res.assets.map((a) => ({ uri: a.uri, name: a.name, type: a.mimeType ?? "application/pdf" }));
}

const EXT: Record<string, string> = { "application/pdf": "pdf", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx", "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp" };

/** Downloads an authenticated file to the app's cache and hands it to the phone's own viewer ("Open with…"). */
export async function openRemoteFile(path: string, baseName: string): Promise<void> {
  const { bytes, contentType } = await requestBytes(path);
  const ext = EXT[contentType.split(";")[0]] ?? "bin";
  const file = new File(Paths.cache, `${baseName.replace(/[^\w.-]+/g, "_")}.${ext}`);
  if (file.exists) file.delete();
  file.create();
  file.write(bytes);
  if (!(await Sharing.isAvailableAsync())) {
    Alert.alert("Can't open file", "This phone has no app that can open this file.");
    return;
  }
  await Sharing.shareAsync(file.uri, { mimeType: contentType, dialogTitle: "Open with" });
}
