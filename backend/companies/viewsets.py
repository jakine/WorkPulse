from django.db.models import ProtectedError, RestrictedError
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from companies.permissions import HasCompanyRole, is_team_lead


class CompanyScopedViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasCompanyRole]
    company_lookup = "company"
    lead_actions = ()

    def get_queryset(self):
        queryset = super().get_queryset().filter(**{self.company_lookup: self.request.company})
        if is_team_lead(self.request):
            queryset = self.scope_for_lead(queryset)
        return queryset

    def scope_for_lead(self, queryset):
        return queryset

    def perform_create(self, serializer):
        if self.company_lookup == "company":
            serializer.save(company=self.request.company)
        else:
            serializer.save()

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except (ProtectedError, RestrictedError):
            return Response(
                {"detail": "This record is used by other data and cannot be deleted."},
                status=400,
            )
