# Task: complex-refactor
# Pipeline status: approved
# Target file: feature.py

# app/crud.py
from typing import List
from sqlalchemy.orm import Session
from app import models, schemas

class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_user(self, user_id: int):
        try:
            return self.db.query(models.User).filter(models.User.id == user_id).first()
        except Exception as e:
            # Wrap errors with context
            raise ValueError(f"Failed to retrieve user with id {user_id}") from e

    def get_users(self, skip: int = 0, limit: int = 100):
        try:
            return self.db.query(models.User).offset(skip).limit(limit).all()
        except Exception as e:
            # Wrap errors with context
            raise ValueError("Failed to retrieve users") from e

    def create_user(self, user: schemas.UserCreate):
        try:
            db_user = models.User(**user.dict())
            self.db.add(db_user)
            self.db.commit()
            self.db.refresh(db_user)
            return db_user
        except Exception as e:
            # Wrap errors with context
            raise ValueError("Failed to create user") from e

    def update_user(self, user_id: int, user: schemas.UserUpdate):
        try:
            db_user = self.db.query(models.User).filter(models.User.id == user_id).first()
            if db_user:
                db_user.name = user.name
                db_user.email = user.email
                self.db.commit()
                self.db.refresh(db_user)
                return db_user
            else:
                raise ValueError("User not found")
        except Exception as e:
            # Wrap errors with context
            raise ValueError(f"Failed to update user with id {user_id}") from e

    def delete_user(self, user_id: int):
        try:
            db_user = self.db.query(models.User).filter(models.User.id == user_id).first()
            if db_user:
                self.db.delete(db_user)
                self.db.commit()
                return True
            else:
                raise ValueError("User not found")
        except Exception as e:
            # Wrap errors with context
            raise ValueError(f"Failed to delete user with id {user_id}") from e


class ItemRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_item(self, item_id: int):
        try:
            return self.db.query(models.Item).filter(models.Item.id == item_id).first()
        except Exception as e:
            # Wrap errors with context
            raise ValueError(f"Failed to retrieve item with id {item_id}") from e

    def get_items(self, skip: int = 0, limit: int = 100):
        try:
            return self.db.query(models.Item).offset(skip).limit(limit).all()
        except Exception as e:
            # Wrap errors with context
            raise ValueError("Failed to retrieve items") from e

    def create_item(self, item: schemas.ItemCreate):
        try:
            db_item = models.Item(**item.dict())
            self.db.add(db_item)
            self.db.commit()
            self.db.refresh(db_item)
            return db_item
        except Exception as e:
            # Wrap errors with context
            raise ValueError("Failed to create item") from e

    def update_item(self, item_id: int, item: schemas.ItemUpdate):
        try:
            db_item = self.db.query(models.Item).filter(models.Item.id == item_id).first()
            if db_item:
                db_item.name = item.name
                db_item.description = item.description
                self.db.commit()
                self.db.refresh(db_item)
                return db_item
            else:
                raise ValueError("Item not found")
        except Exception as e:
            # Wrap errors with context
            raise ValueError(f"Failed to update item with id {item_id}") from e

    def delete_item(self, item_id: int):
        try:
            db_item = self.db.query(models.Item).filter(models.Item.id == item_id).first()
            if db_item:
                self.db.delete(db_item)
                self.db.commit()
                return True
            else:
                raise ValueError("Item not found")
        except Exception as e:
            # Wrap errors with context
            raise ValueError(f"Failed to delete item with id {item_id}") from e