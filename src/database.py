from sqlalchemy import create_engine, Column, Integer, String, Date, Text, func, text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import hashlib

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False)
    created_date = Column(Date, default=datetime.now().date)
    
    @staticmethod
    def hash_password(password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()
    
    def verify_password(self, password: str) -> bool:
        return self.password_hash == self.hash_password(password)

class Category(Base):
    __tablename__ = "categories"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, index=True, nullable=False)
    created_date = Column(Date, default=datetime.now().date)

class Recipe(Base):
    __tablename__ = "recipes"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100), index=True)
    category = Column(String(50))
    portions = Column(String(50))
    ingredients = Column(Text)
    instructions = Column(Text)
    notes = Column(Text)
    created_date = Column(Date)
    image_filename = Column(String(255), nullable=True)

import os
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://rezepte_user:rezepte_password@localhost/rezepte_db")
engine = create_engine(DATABASE_URL, connect_args={"client_encoding": "utf8"})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_tables():
    Base.metadata.create_all(bind=engine)
    
    # Create default admin user if no users exist
    db = SessionLocal()
    try:
        user_count = db.query(User).count()
        if user_count == 0:
            # Create default admin user
            admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
            admin_user = User(
                username="admin",
                password_hash=User.hash_password(admin_password),
                is_admin=True
            )
            db.add(admin_user)
            db.commit()
            print(f"Created default admin user with password: {admin_password}")
    finally:
        db.close()
    
    # Create full-text search index for German language
    with engine.connect() as conn:
        try:
            # Create German text search configuration
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent;"))
            conn.execute(text("""
                CREATE OR REPLACE FUNCTION german_unaccent(text) 
                RETURNS text AS $$
                SELECT unaccent($1)
                $$ LANGUAGE sql IMMUTABLE;
            """))
            
            # Create full-text search index on recipe content
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_recipe_search 
                ON recipes 
                USING gin(to_tsvector('german', 
                    coalesce(title,'') || ' ' || 
                    coalesce(ingredients,'') || ' ' || 
                    coalesce(instructions,'') || ' ' || 
                    coalesce(notes,'') || ' ' || 
                    coalesce(category,'')
                ));
            """))
            
            conn.commit()
        except Exception as e:
            print(f"Note: Could not create search extensions: {e}")
            conn.rollback()