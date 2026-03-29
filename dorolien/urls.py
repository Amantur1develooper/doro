from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('analytics.urls')),
    path('accounts/', include('accounts.urls')),
    path('crm/', include('crm.urls')),
    path('warehouse/', include('warehouse.urls')),
    path('sales/', include('sales.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
