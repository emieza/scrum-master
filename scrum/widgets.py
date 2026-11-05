from django_ckeditor_5.widgets import CKEditor5Widget


class Base64CKEditor5Widget(CKEditor5Widget):
    class Media(CKEditor5Widget.Media):
        js = CKEditor5Widget.Media.js + ["js/ckeditor_base64_upload.js"]
