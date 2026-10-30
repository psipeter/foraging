// Browser helpers for the game (WebGL only).
mergeInto(LibraryManager.library, {
  // Whether the browser itself holds the mouse capture (pointer lock) on the page. Unity's Cursor.lockState does not notice when the
  // browser releases the capture (Escape, switching tabs or windows), so PointerLockGuard asks the page.
  IsPointerLocked: function () {
    return document.pointerLockElement ? 1 : 0;
  },
  // Leaves the page for another address (the Prolific completion page).
  RedirectTo: function (url) {
    window.location.href = UTF8ToString(url);
  }
});
