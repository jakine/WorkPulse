from rest_framework.exceptions import NotFound
from rest_framework.permissions import SAFE_METHODS, BasePermission

from companies.models import Membership
from companies.services import COMPANY_SESSION_KEY


class IsCompanyMember(BasePermission):
    message = "Choose a company first."

    def has_permission(self, request, view):
        company_id = request.session.get(COMPANY_SESSION_KEY)
        if not company_id:
            return False
        membership = (
            Membership.objects.filter(user=request.user, company_id=company_id)
            .select_related("company")
            .first()
        )
        if membership is None:
            return False
        request.company = membership.company
        request.membership = membership
        return True


class IsCompanyOwner(IsCompanyMember):
    message = "Only an owner can invite people."

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return request.membership.role == Membership.Role.OWNER


class HasCompanyRole(IsCompanyMember):
    """Owners and managers may do everything; team leads may read, plus the view's `lead_actions`."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if not is_team_lead(request):
            return True
        if request.method in SAFE_METHODS:
            return True
        if getattr(view, "action", None) in getattr(view, "lead_actions", ()):
            return True
        self.message = "Team leads cannot change this."
        return False


def is_team_lead(request):
    membership = getattr(request, "membership", None)
    return membership is not None and membership.role == Membership.Role.TEAM_LEAD


def lead_teams(request):
    from workforce.models import Team

    return Team.objects.filter(company=request.company, lead_user=request.user)


def lead_projects(request):
    from operations.models import Workplace

    return Workplace.objects.filter(
        company=request.company,
        workplace_teams__team__lead_user=request.user,
    ).distinct()


def visible_projects(request):
    from operations.models import Workplace

    projects = Workplace.objects.filter(company=request.company)
    if is_team_lead(request):
        projects = projects.filter(pk__in=lead_projects(request).values("pk"))
    return projects


def project_for(request, workplace_id):
    workplace = visible_projects(request).filter(pk=workplace_id).first()
    if workplace is None:
        raise NotFound("Project not found.")
    return workplace
