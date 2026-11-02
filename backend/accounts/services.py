from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError

from companies.services import COMPANY_SESSION_KEY, memberships_for_user

User = get_user_model()


def login_user(request, email, password):
    user = authenticate(request, username=email, password=password)
    if user is None:
        return None
    login(request, user)
    memberships = list(memberships_for_user(user))
    if len(memberships) == 1:
        request.session[COMPANY_SESSION_KEY] = memberships[0].company_id
    else:
        request.session.pop(COMPANY_SESSION_KEY, None)
    return user


def logout_user(request):
    logout(request)


def register_user(request, email, password):
    email = email.strip().lower()
    if User.objects.filter(username__iexact=email).exists():
        raise ValidationError({"email": "An account with this email already exists."})
    try:
        validate_password(password)
    except DjangoValidationError as exc:
        raise ValidationError({"password": list(exc.messages)}) from exc
    user = User.objects.create_user(username=email, email=email, password=password)
    login(request, user)
    request.session.pop(COMPANY_SESSION_KEY, None)
    return user


def user_payload(user, request):
    memberships = memberships_for_user(user)
    active_id = request.session.get(COMPANY_SESSION_KEY)
    companies = [
        {
            "id": membership.company_id,
            "name": membership.company.name,
            "timezone": membership.company.timezone,
            "role": membership.role,
        }
        for membership in memberships
    ]
    active = next((company for company in companies if company["id"] == active_id), None)
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "companies": companies,
        "active_company": active,
    }
