// Puts text on the browser's clipboard (WebGL only). Unity's GUIUtility.systemCopyBuffer does not reach it from a page.
mergeInto(LibraryManager.library, {
  CopyToClipboard: function (text) {
    var value = UTF8ToString(text);
    var fallback = function () {
      var area = document.createElement("textarea");
      area.value = value;
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      try { document.execCommand("copy"); } catch (e) {}
      document.body.removeChild(area);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(value).catch(fallback);
    } else {
      fallback();
    }
  }
});
