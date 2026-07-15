// Shrink whatever image the owner picks to a small JPEG in the browser BEFORE we
// upload it — uploads stay fast on slow mobile networks and the payload sails
// under any proxy body limit. The server ALSO recompresses authoritatively (and
// decodes HEIC), so this is purely an optimization: on ANY failure or stall we
// fall back to the raw file and the (direct-to-backend) upload still succeeds.
// Every async step is raced against a timeout so a flaky phone browser can never
// hang the upload button forever.
function withTimeout(promise, ms) {
  return Promise.race([
    promise,
    new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), ms)),
  ]);
}

// Preferred decoder: createImageBitmap honors EXIF rotation via `from-image`.
async function decodeViaBitmap(file) {
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  return { source: bitmap, width: bitmap.width, height: bitmap.height, close: () => bitmap.close && bitmap.close() };
}

// Fallback decoder for browsers where createImageBitmap (or its options bag)
// isn't supported — older iOS Safari in particular. Modern iOS/Android already
// bake EXIF orientation into <img> decode (CSS image-orientation: from-image is
// the default), so portraits stay upright here too.
function decodeViaImgElement(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => resolve({
      source: img,
      width: img.naturalWidth,
      height: img.naturalHeight,
      close: () => URL.revokeObjectURL(url),
    });
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("img decode failed")); };
    img.src = url;
  });
}

export async function shrinkImage(file, { maxDim = 1280, quality = 0.85 } = {}) {
  try {
    if (!file || !file.type || !file.type.startsWith("image/")) return file;

    let decoded;
    try {
      decoded = await withTimeout(decodeViaBitmap(file), 8000);
    } catch {
      decoded = await withTimeout(decodeViaImgElement(file), 8000);
    }

    const scale = Math.min(1, maxDim / Math.max(decoded.width, decoded.height));
    const w = Math.max(1, Math.round(decoded.width * scale));
    const h = Math.max(1, Math.round(decoded.height * scale));

    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(decoded.source, 0, 0, w, h);
    decoded.close();

    const blob = await withTimeout(
      new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", quality)),
      8000
    );
    if (!blob) return file;
    return new File([blob], "photo.jpg", { type: "image/jpeg" });
  } catch {
    return file; // let the server deal with whatever we couldn't shrink here
  }
}
