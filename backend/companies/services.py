from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from companies.exceptions import Conflict
from companies.models import Company, Membership
from operations.services import create_default_duration_units, create_default_measures, create_default_work_categories
from timesheets.leave import create_default_leave_types
from timesheets.periods import default_pay_group
from timesheets.services import create_default_schedule
from work.services import create_default_phases, create_default_statuses

COMPANY_SESSION_KEY = "company_id"

User = get_user_model()


def memberships_for_user(user):
    return Membership.objects.filter(user=user).select_related("company")


def create_company(user, name):
    with transaction.atomic():
        company = Company.objects.create(name=name)
        Membership.objects.create(
            user=user,
            company=company,
            role=Membership.Role.OWNER,
        )
        create_default_measures(company)
        create_default_duration_units(company)
        create_default_work_categories(company)
        create_default_statuses(company)
        create_default_phases(company)
        create_default_schedule(company)
        create_default_leave_types(company)
        default_pay_group(company)
    return company


def switch_company(request, company_id):
    membership = (
        Membership.objects.filter(user=request.user, company_id=company_id)
        .select_related("company")
        .first()
    )
    if membership is None:
        return None
    request.session[COMPANY_SESSION_KEY] = membership.company_id
    return membership


INVITABLE_ROLES = (Membership.Role.MANAGER, Membership.Role.TEAM_LEAD)


def invite_member(company, email, password, role=Membership.Role.MANAGER, team=None):
    if role not in INVITABLE_ROLES:
        raise ValidationError({"role": "Invite a manager or a team lead."})
    if team is not None:
        if role != Membership.Role.TEAM_LEAD:
            raise ValidationError({"team": "Only a team lead can be linked to a team."})
        if team.company_id != company.id:
            raise ValidationError({"team": "Team must belong to this company."})
    email = email.strip().lower()
    user = User.objects.filter(username__iexact=email).first()
    if user is None:
        if not password:
            raise ValidationError({"password": "Password is required for a new member."})
        try:
            validate_password(password)
        except DjangoValidationError as exc:
            raise ValidationError({"password": list(exc.messages)}) from exc
        user = User.objects.create_user(username=email, email=email, password=password)
    try:
        with transaction.atomic():
            membership = Membership.objects.create(user=user, company=company, role=role)
            if team is not None:
                team.lead_user = user
                team.save(update_fields=["lead_user"])
            return membership
    except IntegrityError as exc:
        raise Conflict("That person is already a member of this company.") from exc
