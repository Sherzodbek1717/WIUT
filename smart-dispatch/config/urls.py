from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from accounts import views as accounts
from analytics import views as analytics
from dispatch import views as dispatch
from engine import views as engine

urlpatterns = [
    path("", dispatch.home, name="home"),
    path("board/", dispatch.board, name="board"),

    path("login/", auth_views.LoginView.as_view(redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("register/", accounts.RegisterView.as_view(), name="register"),
    path("users/", accounts.UserListView.as_view(), name="user_list"),
    path("users/<int:pk>/edit/", accounts.UserUpdateView.as_view(), name="user_edit"),

    path("loads/", dispatch.LoadListView.as_view(), name="load_list"),
    path("loads/new/", dispatch.LoadCreateView.as_view(), name="load_create"),
    path("loads/<int:pk>/", dispatch.LoadDetailView.as_view(), name="load_detail"),
    path("loads/<int:pk>/edit/", dispatch.LoadUpdateView.as_view(), name="load_edit"),
    path("loads/<int:pk>/delete/", dispatch.LoadDeleteView.as_view(), name="load_delete"),
    path("loads/<int:pk>/assign/", dispatch.load_assign, name="load_assign"),
    path("loads/<int:pk>/status/", dispatch.load_status, name="load_status"),

    path("drivers/", dispatch.DriverListView.as_view(), name="driver_list"),
    path("drivers/new/", dispatch.DriverCreateView.as_view(), name="driver_create"),
    path("drivers/<int:pk>/edit/", dispatch.DriverUpdateView.as_view(), name="driver_edit"),
    path("drivers/<int:pk>/delete/", dispatch.DriverDeleteView.as_view(), name="driver_delete"),

    path("trucks/", dispatch.TruckListView.as_view(), name="truck_list"),
    path("trucks/new/", dispatch.TruckCreateView.as_view(), name="truck_create"),
    path("trucks/<int:pk>/edit/", dispatch.TruckUpdateView.as_view(), name="truck_edit"),
    path("trucks/<int:pk>/delete/", dispatch.TruckDeleteView.as_view(), name="truck_delete"),

    path("brokers/", dispatch.BrokerListView.as_view(), name="broker_list"),
    path("brokers/new/", dispatch.BrokerCreateView.as_view(), name="broker_create"),
    path("brokers/<int:pk>/edit/", dispatch.BrokerUpdateView.as_view(), name="broker_edit"),
    path("brokers/<int:pk>/delete/", dispatch.BrokerDeleteView.as_view(), name="broker_delete"),

    path("dashboard/", analytics.DashboardView.as_view(), name="dashboard"),
    path("reports/", analytics.ReportsView.as_view(), name="reports"),
    path("settings/", engine.SettingsView.as_view(), name="engine_settings"),

    path("api/evaluate/", engine.evaluate_api, name="api_evaluate"),

    path("admin/", admin.site.urls),
]
