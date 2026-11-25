from rest_framework.routers import SimpleRouter

from .admin_api import AdminProjectViewSet
from .views import ProjectViewSet

router = SimpleRouter()
router.register("projects", ProjectViewSet, basename="project")
# Our team's review of every client's projects (A3, A4). Admin role only.
router.register("admin/projects", AdminProjectViewSet, basename="admin-project")

urlpatterns = router.urls