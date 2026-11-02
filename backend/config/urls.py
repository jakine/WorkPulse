from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/companies/", include("companies.urls")),
    path("api/", include("workforce.urls")),
    path("api/", include("operations.urls")),
    path("api/", include("inventory.urls")),
    path("api/", include("core.urls")),
    path("api/", include("work.urls")),
    path("api/", include("sitelog.urls")),
]
