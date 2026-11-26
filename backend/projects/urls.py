from django.urls import path
from rest_framework.routers import SimpleRouter

from .admin_api import AdminProjectViewSet, dashboard_view
from .views import ProjectViewSet

router = SimpleRouter()
router.register("projects", ProjectViewSet, basename="project")
# Our team's review of every client's projects (A3, A4). Admin role only.
router.register("admin/projects", AdminProjectViewSet, basename="admin-project")

urlpatterns = [
    path("admin/dashboard/", dashboard_view, name="admin-dashboard"),
    *router.urls,
]