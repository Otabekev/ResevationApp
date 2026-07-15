// Shrink whatever image the owner picks to a small JPEG in the browser BEFORE we
// upload it. Two reasons: (1) the wire payload then clears Vercel's ~4.5MB body
// limit no matter how big the original phone photo is, and (2) uploads stay fast
// on slow mobile networks. The server ALSO recompresses authoritatively (and now
// decodes HEIC), so this is purely an optimization — on ANY failure or stall we
// fall back to the raw file and let the server handle it. Every async step is
// raced against a timeout so a flaky phone browser can never hang the upload
// button forever.
function withTimeout(promise, ms) {
  return Promise.race([
    promise,
    new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), ms)),
  ]);
}

export async function shrinkImage(file, { maxDim = 1280, quality = 0.85 } = {}) {
  try {
    if (!file || !file.type || !file.type.startsWith("image/")) return file;
    // `from-image` bakes the EXIF orientation into the pixels so a portrait phone
    // photo isn't uploaded sideways (canvas would otherwise drop the EXIF tag).
    const bitmap = await withTimeout(
      createImageBitmap(file, { imageOrientation: "from-image" }),
      8000
    );
    const scale = Math.min(1, maxDim / Math.max(bitmap.width, bitmap.height));
    const w = Math.max(1, Math.round(bitmap.width * scale));
    const h = Math.max(1, Math.round(bitmap.height * scale));

    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(bitmap, 0, 0, w, h);
    if (bitmap.close) bitmap.close();

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
