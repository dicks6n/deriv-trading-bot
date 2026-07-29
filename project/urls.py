from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from store import views  # Ensure views is imported from store

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('store.urls')),
    path('connect-broker/', views.connect_broker, name='connect_broker'), # <-- ADD THIS LINE
    path('deriv-callback/', views.deriv_callback, name='deriv_callback'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
