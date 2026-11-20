from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from accounts import views as accounts
from analytics import views as analytics
from dispatch import views as dispatch
from engine import views as engine
from copilot import views as copilot
from loadboard import api as loadboard_api
from loadboard import views as loadboard

urlpatterns = [
    path("", dispatch.home, name="home"),
    path("board/", dispatch.board, name="board"),

    path("loads/search/", loadboard.load_search, name="load_search"),
    path("loads/search/<int:pk>/book/", loadboard.book_load, name="book_load"),
    path("trucks/search/", loadboard.truck_search, name="truck_search"),
    path("my-loads/", loadboard.my_loads, name="my_loads"),
    path("my-loads/new/", loadboard.post_load, name="post_load"),
    path("my-loads/<int:pk>/edit/", loadboard.post_load, name="edit_load_posting"),
    path("my-loads/<int:pk>/cancel/", loadboard.cancel_load, name="cancel_load_posting"),
    path("my-trucks/", loadboard.my_trucks, name="my_trucks"),
    path("my-trucks/new/", loadboard.post_truck, name="post_truck"),
    path("my-trucks/<int:pk>/edit/", loadboard.post_truck, name="edit_truck_posting"),
    path("my-trucks/<int:pk>/remove/", loadboard.remove_truck, name="remove_truck_posting"),

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
    path("drivers/<int:pk>/telegram/", dispatch.driver_telegram, name="driver_telegram"),
    path("pods/<int:pk>/", dispatch.pod_file, name="pod_file"),

    path("trucks/", dispatch.TruckListView.as_view(), name="truck_list"),
    path("trucks/new/", dispatch.TruckCreateView.as_view(), name="truck_create"),
    path("trucks/<int:pk>/edit/", dispatch.TruckUpdateView.as_view(), name="truck_edit"),
    path("trucks/<int:pk>/delete/", dispatch.TruckDeleteView.as_view(), name="truck_delete"),

    path("brokers/", copilot.broker_directory, name="broker_list"),
    path("brokers/<int:pk>/", copilot.broker_detail, name="broker_detail"),
    path("brokers/new/", dispatch.BrokerCreateView.as_view(), name="broker_create"),
    path("brokers/<int:pk>/edit/", dispatch.BrokerUpdateView.as_view(), name="broker_edit"),
    path("brokers/<int:pk>/delete/", dispatch.BrokerDeleteView.as_view(), name="broker_delete"),

    path("copilot/email/<int:pk>/", copilot.compose_email, name="compose_email"),
    path("copilot/email/bulk/", copilot.bulk_email, name="bulk_email"),
    path("copilot/mailbox/", copilot.mailbox, name="mailbox"),
    path("copilot/call/<int:pk>/", copilot.call_assistant, name="call_assistant"),
    path("copilot/calls/", copilot.call_log, name="call_log"),
    path("profile/", copilot.profile, name="profile"),

    path("dashboard/", analytics.DashboardView.as_view(), name="dashboard"),
    path("reports/", analytics.ReportsView.as_view(), name="reports"),
    path("settings/", engine.SettingsView.as_view(), name="engine_settings"),

    path("api/evaluate/", engine.evaluate_api, name="api_evaluate"),
    path("api/loadboard/search/", loadboard_api.load_search_api, name="api_load_search"),
    path("api/loads/", loadboard_api.booked_loads_api, name="api_loads"),

    path("admin/", admin.site.urls),
]
