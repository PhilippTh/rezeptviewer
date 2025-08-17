from pydantic import BaseModel
from datetime import date

# Authentication models
class LoginRequest(BaseModel):
    username: str
    password: str

class UserInfo(BaseModel):
    username: str
    is_admin: bool

class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

class RecipeBase(BaseModel):
    title: str
    category: str | None = None
    portions: str | None = None
    ingredients: str
    instructions: str | None = None
    notes: str | None = None
    image_filename: str | None = None

class RecipeCreate(RecipeBase):
    pass

class RecipeResponse(RecipeBase):
    id: int
    created_date: date = None
    
    class Config:
        from_attributes = True

# Category Management
class CategoryCreate(BaseModel):
    name: str

class CategoryResponse(BaseModel):
    id: int
    name: str
    recipe_count: int

class PortionScale(BaseModel):
    original_portions: str
    target_portions: int
    
class ScaledRecipeResponse(RecipeResponse):
    scaled_ingredients: str
    scaling_factor: float

class ShoppingListRequest(BaseModel):
    recipe_ids: list[int]
    portions_override: dict | None = {}  # Optional dict of recipe_id -> desired_portions

class IngredientItem(BaseModel):
    name: str
    amount: float | None = None
    unit: str | None = None
    recipes: list[str]  # List of recipe titles that contain this ingredient

class ShoppingListResponse(BaseModel):
    ingredients: list[IngredientItem]
    recipe_count: int