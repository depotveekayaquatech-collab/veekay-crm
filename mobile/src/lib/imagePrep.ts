import { File } from "expo-file-system";
import { ImageManipulator, SaveFormat } from "expo-image-manipulator";
import { fitWithin, shouldShrink, type UploadPolicy } from "@/lib/compliance";
import type { Picked } from "@/lib/files";

/**
 * Shrinks a photo on the phone before it is sent: upright, the longest side limited to the server's maximum, saved as a
 * JPEG at the server's quality. A camera photo of 2-5 MB becomes about 0.2-0.4 MB, so it uploads quickly on mobile data.
 *
 *  - A photo that is already small is left alone (it is never compressed twice); a PDF is never touched.
 *  - If the shrunk copy is not smaller, or anything goes wrong, the ORIGINAL is returned unchanged: the server still shrinks
 *    and checks every photo itself, so this step can only ever make an upload faster, never worse.
 *  - The limits come from the server (GET /uploads/policy); nothing is hard-coded here.
 */
export async function shrinkForUpload(p: Picked, policy: UploadPolicy): Promise<Picked> {
  if (!shouldShrink(p, policy)) return p;
  try {
    const original = await ImageManipulator.manipulate(p.uri).renderAsync();          // decoded upright, at its real size
    const target = fitWithin(original.width, original.height, policy.max_dimension);
    const context = ImageManipulator.manipulate(p.uri);
    const rendered = await (target.width < original.width ? context.resize(target) : context).renderAsync();
    const saved = await rendered.saveAsync({ format: SaveFormat.JPEG, compress: policy.jpeg_quality / 100 });
    const newSize = new File(saved.uri).size;
    const oldSize = p.size ?? new File(p.uri).size;
    if (!newSize || (oldSize && newSize >= oldSize)) return p;                          // nothing gained: keep the original
    return { uri: saved.uri, name: `${p.name.replace(/\.\w+$/, "")}.jpg`, type: "image/jpeg", size: newSize };
  } catch {
    return p;
  }
}
