# Task: security-input-validation
# Pipeline status: approved
# Target file: tests/test_feature.py

# feature.py
from app import crud
from app.schemas import UserCreate
from app.utils import validate_email, validate_password
from fastapi import HTTPException
from logging import getLogger

logger = getLogger(__name__)

def validate_user_input(user_in: UserCreate) -> None:
    """
    Validate user input for email and password.
    """
    if not validate_email(user_in.email):
        raise HTTPException(
            status_code=400,
            detail="Invalid email format.",
        )
    if not validate_password(user_in.password):
        raise HTTPException(
            status_code=400,
            detail="Password does not meet the required strength.",
        )

def create_user(*, session: Session, user_in: UserCreate) -> Any:
    """
    Create new user with input validation.
    """
    validate_user_input(user_in)
    user = crud.get_user_by_email(session=session, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system.",
        )

    user = crud.create_user(session=session, user_create=user_in)
    if settings.emails_enabled and user_in.email:
        email_data = generate_new_account_email
        # ... (rest of the email sending logic remains the same)
    return user