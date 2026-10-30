from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from scrum.views import ProjecteAutocompleteJsonView

urlpatterns = [
    path(
        "admin/autocomplete/",
        admin.site.admin_view(
            ProjecteAutocompleteJsonView.as_view(admin_site=admin.site)
        ),
    ),
    path("admin/", admin.site.urls),
    path("ckeditor5/", include("django_ckeditor_5.urls")),
    path("accounts/", include("allauth.urls")),
    path("", include("scrum.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
