import { Capacitor } from "@capacitor/core";
import { Directory, Filesystem } from "@capacitor/filesystem";
import { Share } from "@capacitor/share";
import { blobToDataUrl } from "./images";

export interface ImageFile {
  name: string;
  blob: Blob;
}

const FOLDER = "FashionSketchpad";

async function base64(blob: Blob): Promise<string> {
  return (await blobToDataUrl(blob)).split(",")[1];
}

/** Saves to Documents/FashionSketchpad on Android; downloads in a browser. Returns a short message. */
export async function saveImages(files: ImageFile[]): Promise<string> {
  if (Capacitor.isNativePlatform()) {
    for (const file of files) {
      await Filesystem.writeFile({
        path: `${FOLDER}/${file.name}`,
        data: await base64(file.blob),
        directory: Directory.Documents,
        recursive: true,
      });
    }
    return `Saved to Documents/${FOLDER}`;
  }
  for (const file of files) {
    const url = URL.createObjectURL(file.blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = file.name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  }
  return "Downloaded";
}

/** Opens the system share sheet with the images (WhatsApp, Drive, Photos, ...). */
export async function shareImages(files: ImageFile[], title: string): Promise<string | null> {
  if (Capacitor.isNativePlatform()) {
    const uris: string[] = [];
    for (const file of files) {
      const written = await Filesystem.writeFile({
        path: `share/${file.name}`,
        data: await base64(file.blob),
        directory: Directory.Cache,
        recursive: true,
      });
      uris.push(written.uri);
    }
    await Share.share({ title, files: uris });
    return null;
  }
  const shareFiles = files.map((f) => new File([f.blob], f.name, { type: f.blob.type || "image/png" }));
  if (navigator.canShare?.({ files: shareFiles })) {
    await navigator.share({ title, files: shareFiles });
    return null;
  }
  return saveImages(files);
}
