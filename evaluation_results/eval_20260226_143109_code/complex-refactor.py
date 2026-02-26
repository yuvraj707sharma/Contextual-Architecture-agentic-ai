# Task: complex-refactor
# Pipeline status: approved
# Target file: app/crud.py

# database_crud.py

from typing import List
from sqlalchemy.orm import Session
from app import models, schemas

class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_user(self, user_id: int):
        return self.db.query(models.User).filter(models.User.id == user_id).first()

    def get_users(self, skip: int = 0, limit: int = 100):
        return self.db.query(models.User).offset(skip).limit(limit).all()

    def create_user(self, user_in: schemas.UserCreate):
        db_user = models.User(**user_in.dict())
        self.db.add(db_user)
        self.db.commit()
        self.db.refresh(db_user)
        return db_user

    def update_user(self, user_id: int, user_in: schemas.UserUpdate):
        db_user = self.get_user(user_id)
        if db_user:
            db_user.name = user_in.name
            db_user.email = user_in.email
            self.db.commit()
            self.db.refresh(db_user)
            return db_user
        return None

    def delete_user(self, user_id: int):
        db_user = self.get_user(user_id)
        if db_user:
            self.db.delete(db_user)
            self.db.commit()
            return True
        return False


class ItemRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_item(self, item_id: int):
        return self.db.query(models.Item).filter(models.Item.id == item_id).first()

    def get_items(self, skip: int = 0, limit: int = 100):
        return self.db.query(models.Item).offset(skip).limit(limit).all()

    def create_item(self, item_in: schemas.ItemCreate, owner_id: int):
        db_item = models.Item(**item_in.dict(), owner_id=owner_id)
        self.db.add(db_item)
        self.db.commit()
        self.db.refresh(db_item)
        return db_item

    def update_item(self, item_id: int, item_in: schemas.ItemUpdate):
        db_item = self.get_item(item_id)
        if db_item:
            db_item.title = item_in.title
            db_item.description = item_in.description
            self.db.commit()
            self.db.refresh(db_item)
            return db_item
        return None

    def delete_item(self, item_id: int):
        db_item = self.get_item(item_id)
        if db_item:
            self.db.delete(db_item)
            self.db.commit()
            return True
        return False