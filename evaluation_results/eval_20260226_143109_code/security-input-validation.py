# Task: security-input-validation
# Pipeline status: approved
# Target file: input_validation_user.py

# input_validation_user.py

import re
from typing import Optional
from app.crud import create_user, get_user_by_email
from app.schemas import UserCreate
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)

def validate_email_format(email: str) -> bool:
    """
    Validate email format using a regular expression.
    """
    email_regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return bool(re.match(email_regex, email))

def validate_password_strength(password: str) -> bool:
    """
    Validate password strength.
    """
    # Password should be at least 8 characters long, contain at least one uppercase letter,
    # one lowercase letter, one digit, and one special character.
    password_regex = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!%*#?&]{8,}$"
    return bool(re.match(password_regex, password))

def validate_user_input(user_in: UserCreate) -> None:
    """
    Validate user input.
    """
    if not validate_email_format(user_in.email):
        raise HTTPException(
            status_code=400,
            detail="Invalid email format.",
        )

    if not validate_password_strength(user_in.password):
        raise HTTPException(
            status_code=400,
            detail="Password should be at least 8 characters long, contain at least one uppercase letter, "
                   "one lowercase letter, one digit, and one special character.",
        )

    existing_user = get_user_by_email(email=user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system.",
        )

def create_user_with_validation(session: Session, user_in: UserCreate) -> Any:
    """
    Create new user with input validation.
    """
    validate_user_input(user_in)
    return create_user(session=session, user_in=user_in)