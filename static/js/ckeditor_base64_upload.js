(function () {
  if (window.__ckeditorBase64UploadInstalled) {
    return;
  }
  window.__ckeditorBase64UploadInstalled = true;

  function Base64UploadAdapter(loader) {
    this.loader = loader;
  }

  Base64UploadAdapter.prototype.upload = function () {
    return this.loader.file.then(function (file) {
      return new Promise(function (resolve, reject) {
        var reader = new FileReader();
        reader.onload = function () {
          resolve({ default: reader.result });
        };
        reader.onerror = function () {
          reject(reader.error);
        };
        reader.readAsDataURL(file);
      });
    });
  };

  Base64UploadAdapter.prototype.abort = function () {};

  function patchEditor(editor) {
    if (!editor || !editor.plugins || !editor.plugins.has('FileRepository')) {
      return;
    }
    var repository = editor.plugins.get('FileRepository');
    repository.createUploadAdapter = function (loader) {
      return new Base64UploadAdapter(loader);
    };
  }

  function install() {
    var editorClass = window.ClassicEditor;
    if (!editorClass || !editorClass.create || editorClass.create.__base64UploadPatched) {
      return false;
    }
    var originalCreate = editorClass.create;
    editorClass.create = function () {
      return originalCreate.apply(this, arguments).then(function (editor) {
        patchEditor(editor);
        return editor;
      });
    };
    editorClass.create.__base64UploadPatched = true;
    if (window.editors) {
      Object.keys(window.editors).forEach(function (id) {
        patchEditor(window.editors[id]);
      });
    }
    return true;
  }

  if (!install()) {
    var attempts = 0;
    var timer = setInterval(function () {
      attempts += 1;
      if (install() || attempts > 200) {
        clearInterval(timer);
      }
    }, 10);
  }
})();
