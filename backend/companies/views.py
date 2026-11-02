from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from companies.models import Membership
from companies.permissions import HasCompanyRole, IsCompanyMember, IsCompanyOwner
from companies.serializers import (
    CompanyCreateSerializer,
    CompanySettingsSerializer,
    InviteSerializer,
    MembershipSerializer,
    SwitchSerializer,
)
from companies.services import (
    COMPANY_SESSION_KEY,
    create_company,
    invite_member,
    memberships_for_user,
    switch_company,
)
from workforce.models import Team


def _company_data(membership):
    return {
        "id": membership.company_id,
        "name": membership.company.name,
        "timezone": membership.company.timezone,
        "role": membership.role,
    }


class CompanyListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        memberships = memberships_for_user(request.user)
        return Response([_company_data(membership) for membership in memberships])

    def post(self, request):
        serializer = CompanyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company = create_company(request.user, serializer.validated_data["name"].strip())
        request.session[COMPANY_SESSION_KEY] = company.id
        return Response(
            {"id": company.id, "name": company.name, "timezone": company.timezone, "role": Membership.Role.OWNER},
            status=status.HTTP_201_CREATED,
        )


class CurrentCompanyView(APIView):
    permission_classes = [IsAuthenticated, HasCompanyRole]

    def get(self, request):
        return Response(CompanySettingsSerializer(request.company).data)

    def patch(self, request):
        serializer = CompanySettingsSerializer(request.company, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class SwitchCompanyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SwitchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = switch_company(request, serializer.validated_data["company_id"])
        if membership is None:
            return Response(
                {"detail": "You are not a member of that company."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(_company_data(membership))


class MemberListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsCompanyOwner()]
        return [IsAuthenticated(), IsCompanyMember()]

    def get(self, request):
        memberships = (
            Membership.objects.filter(company=request.company)
            .select_related("user")
            .order_by("user__email")
        )
        return Response(MembershipSerializer(memberships, many=True).data)

    def post(self, request):
        serializer = InviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        team = None
        if data.get("team"):
            team = Team.objects.filter(company=request.company, pk=data["team"]).first()
            if team is None:
                return Response({"team": ["Team must belong to this company."]}, status=status.HTTP_400_BAD_REQUEST)
        membership = invite_member(
            request.company,
            data["email"],
            data.get("password") or "",
            role=data["role"],
            team=team,
        )
        return Response(MembershipSerializer(membership).data, status=status.HTTP_201_CREATED)
