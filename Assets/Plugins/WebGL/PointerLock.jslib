// Browser helpers for the game (WebGL only).
mergeInto(LibraryManager.library, {
  // Whether the browser itself holds the mouse capture (pointer lock) on the page. Unity's Cursor.lockState does not notice when the
  // browser releases the capture (Escape, switching tabs or windows), so PointerLockGuard asks the page.
  IsPointerLocked: function () {
    return document.pointerLockElement ? 1 : 0;
  },
  // Asks the browser to capture the mouse on the game's canvas. It needs a user gesture a few seconds old at most (Chrome), so the menu click's handler calls it at once,
  // where Unity's own Cursor.lockState request would wait for the next click.
  RequestPointerLock: function () {
    var canvas = document.querySelector("canvas");
    if (canvas && !document.pointerLockElement && canvas.requestPointerLock) {
      var request = canvas.requestPointerLock();
      if (request && request.catch) {
        request.catch(function () {});
      }
    }
  },
  // Leaves the page for another address (the Prolific completion page).
  RedirectTo: function (url) {
    window.location.href = UTF8ToString(url);
  }
});
