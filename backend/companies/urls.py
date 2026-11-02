from django.urls import path

from companies.views import CompanyListCreateView, CurrentCompanyView, MemberListCreateView, SwitchCompanyView

urlpatterns = [
    path("", CompanyListCreateView.as_view(), name="company-list"),
    path("current/", CurrentCompanyView.as_view(), name="company-current"),
    path("switch/", SwitchCompanyView.as_view(), name="company-switch"),
    path("members/", MemberListCreateView.as_view(), name="company-members"),
]
