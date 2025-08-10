from sqlalchemy import create_engine, Column, Integer, String, Date, Text, func, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

Base = declarative_base()

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
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_tables():
    Base.metadata.create_all(bind=engine)
    
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