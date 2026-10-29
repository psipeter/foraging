// Whether the browser itself holds the mouse capture (pointer lock) on the page. Unity's Cursor.lockState does not notice when the
// browser releases the capture (Escape, switching tabs or windows), so PointerLockGuard asks the page.
mergeInto(LibraryManager.library, {
  IsPointerLocked: function () {
    return document.pointerLockElement ? 1 : 0;
  }
});
