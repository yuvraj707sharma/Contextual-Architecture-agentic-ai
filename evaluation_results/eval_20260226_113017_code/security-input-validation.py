# Task: security-input-validation
# Pipeline status: approved
# Target file: app/api/routes/users.py

# feature.py
from fastapi import HTTPException
from pydantic import BaseModel, EmailStr, validator
from typing import Optional
import re

class UserCreateRequest(BaseModel):
    """Request model for user creation"""
    email: EmailStr
    password: str

    @validator('password')
    def validate_password(cls, v):
        """Validate password strength"""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not re.search("[a-z]", v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search("[A-Z]", v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search("[0-9]", v):
            raise ValueError('Password must contain at least one digit')
        return v

def create_user(user_request: UserCreateRequest):
    """Create a new user"""
    try:
        # TO DO: Implement user creation logic here
        # For demonstration purposes, assume user creation is successful
        return {"message": "User created successfully"}
    except Exception as e:
        # Wrap errors with context
        raise HTTPException(status_code=400, detail=f"Failed to create user: {str(e)}")

# Example usage:
# user_request = UserCreateRequest(email="example@example.com", password="StrongP@ssw0rd")
# response = create_user(user_request)
# print(response)