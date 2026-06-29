/**
 * One-tap "Refresh" for the installed PWA.
 *
 * Installed (standalone) apps have no browser reload button, so this replaces it
 * — and it also force-pulls the latest app version. It asks the service worker to
 * check the server for a newer build right now (registerType "autoUpdate" then
 * activates it); if one is downloading it waits briefly for it to take over so the
 * reload lands on the newest code in a single shot. It always ends in a reload, so
 * data is re-fetched fresh either way. Bounded by a timeout so it can never hang.
 */
export async function refreshApp() {
  if ("serviceWorker" in navigator) {
    try {
      const reg = await navigator.serviceWorker.getRegistration();
      if (reg) {
        await reg.update(); // ask the server: is there a newer service worker?
        if (reg.installing || reg.waiting) {
          // A new version is downloading — wait (up to 3s) for it to take control
          // so the reload serves the latest code instead of double-reloading.
          await new Promise((resolve) => {
            const timer = setTimeout(resolve, 3000);
            navigator.serviceWorker.addEventListener(
              "controllerchange",
              () => { clearTimeout(timer); resolve(); },
              { once: true },
            );
          });
        }
      }
    } catch {
      /* ignore — just fall through to a plain reload */
    }
  }
  window.location.reload();
}
