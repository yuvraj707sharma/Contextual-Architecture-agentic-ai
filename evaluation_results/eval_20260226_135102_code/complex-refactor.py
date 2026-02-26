# Task: complex-refactor
# Pipeline status: approved
# Target file: app/main.py

# app/crud.py
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

    def update_user(self, db_user: models.User, user_in: schemas.UserUpdate):
        for key, value in user_in.dict(exclude_unset=True).items():
            setattr(db_user, key, value)
        self.db.add(db_user)
        self.db.commit()
        self.db.refresh(db_user)
        return db_user

    def delete_user(self, user_id: int):
        db_user = self.get_user(user_id)
        if db_user:
            self.db.delete(db_user)
            self.db.commit()
        return db_user


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

    def update_item(self, db_item: models.Item, item_in: schemas.ItemUpdate):
        for key, value in item_in.dict(exclude_unset=True).items():
            setattr(db_item, key, value)
        self.db.add(db_item)
        self.db.commit()
        self.db.refresh(db_item)
        return db_item

    def delete_item(self, item_id: int):
        db_item = self.get_item(item_id)
        if db_item:
            self.db.delete(db_item)
            self.db.commit()
        return db_item