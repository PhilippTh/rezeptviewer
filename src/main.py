from fastapi import FastAPI, Depends, HTTPException, Query, File, UploadFile, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from typing import List, Optional
from pydantic import BaseModel
from datetime import date, datetime
import os
import uuid
import re
from pathlib import Path
from database import get_db, Recipe, Category, create_tables

app = FastAPI(title="Recipe Viewer", description="Web app for viewing and managing recipes")

# Add CORS middleware to ensure proper encoding
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create uploads directory
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Create tables on startup
@app.on_event("startup")
async def startup_event():
    create_tables()

class RecipeBase(BaseModel):
    title: str
    category: Optional[str] = None
    portions: Optional[str] = None
    ingredients: str
    instructions: Optional[str] = None
    notes: Optional[str] = None
    image_filename: Optional[str] = None

class RecipeCreate(RecipeBase):
    pass

class RecipeResponse(RecipeBase):
    id: int
    created_date: date = None
    
    class Config:
        from_attributes = True

@app.get("/")
def read_root():
    return RedirectResponse(url="/static/frontend.html")

@app.get("/recipes", response_model=List[RecipeResponse])
def get_recipes(
    skip: int = 0, 
    limit: int = 1000, 
    search: Optional[str] = Query(None, description="Full-text search across all recipe fields"),
    category: Optional[str] = Query(None, description="Filter by category"),
    db: Session = Depends(get_db)
):
    query = db.query(Recipe)
    
    # Apply full-text search if provided
    if search:
        search_query = text("""
            SELECT * FROM recipes 
            WHERE to_tsvector('german', 
                coalesce(title,'') || ' ' || 
                coalesce(ingredients,'') || ' ' || 
                coalesce(instructions,'') || ' ' || 
                coalesce(notes,'') || ' ' || 
                coalesce(category,'')
            ) @@ plainto_tsquery('german', :search_term)
            ORDER BY ts_rank(
                to_tsvector('german', 
                    coalesce(title,'') || ' ' || 
                    coalesce(ingredients,'') || ' ' || 
                    coalesce(instructions,'') || ' ' || 
                    coalesce(notes,'') || ' ' || 
                    coalesce(category,'')
                ), 
                plainto_tsquery('german', :search_term)
            ) DESC
            OFFSET :skip LIMIT :limit_val
        """)
        
        result = db.execute(search_query, {
            "search_term": search, 
            "skip": skip, 
            "limit_val": limit
        })
        
        recipes = []
        for row in result:
            recipe = Recipe(
                id=row.id,
                title=row.title,
                category=row.category,
                portions=row.portions,
                ingredients=row.ingredients,
                instructions=row.instructions,
                notes=row.notes,
                created_date=row.created_date
            )
            recipes.append(recipe)
        return recipes
    
    # Apply category filter if provided
    if category:
        query = query.filter(Recipe.category == category)
    
    # Regular query without search
    recipes = query.offset(skip).limit(limit).all()
    return recipes

@app.get("/recipes/{recipe_id}", response_model=RecipeResponse)
def get_recipe(recipe_id: int, db: Session = Depends(get_db)):
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe

@app.post("/recipes", response_model=RecipeResponse)
async def create_recipe(
    title: str = Form(...),
    category: str = Form(""),
    portions: str = Form(""),
    ingredients: str = Form(...),
    instructions: str = Form(""),
    notes: str = Form(""),
    image: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    # Handle image upload if provided
    image_filename = None
    if image and image.filename:
        # Validate file type
        allowed_types = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
        if image.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="Only JPEG, PNG, and WebP images are allowed")
        
        # Save image
        file_extension = image.filename.split('.')[-1].lower()
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        file_path = UPLOAD_DIR / unique_filename
        
        try:
            with open(file_path, "wb") as buffer:
                content = await image.read()
                buffer.write(content)
            image_filename = unique_filename
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Could not save image: {str(e)}")
    
    db_recipe = Recipe(
        title=title,
        category=category or "",
        portions=portions or "",
        ingredients=ingredients,
        instructions=instructions or "",
        notes=notes or "",
        created_date=datetime.now().date(),
        image_filename=image_filename
    )
    db.add(db_recipe)
    db.commit()
    db.refresh(db_recipe)
    return db_recipe

@app.put("/recipes/{recipe_id}", response_model=RecipeResponse)
async def update_recipe(
    recipe_id: int,
    title: str = Form(...),
    category: str = Form(""),
    portions: str = Form(""),
    ingredients: str = Form(...),
    instructions: str = Form(""),
    notes: str = Form(""),
    image: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    db_recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if db_recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    
    # Handle image upload if provided
    image_filename = db_recipe.image_filename  # Keep existing image by default
    if image and image.filename:
        # Validate file type
        allowed_types = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
        if image.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="Only JPEG, PNG, and WebP images are allowed")
        
        # Delete old image if exists
        if db_recipe.image_filename:
            old_file_path = UPLOAD_DIR / db_recipe.image_filename
            if old_file_path.exists():
                old_file_path.unlink()
        
        # Save new image
        file_extension = image.filename.split('.')[-1].lower()
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        file_path = UPLOAD_DIR / unique_filename
        
        try:
            with open(file_path, "wb") as buffer:
                content = await image.read()
                buffer.write(content)
            image_filename = unique_filename
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Could not save image: {str(e)}")
    
    # Update recipe data
    db_recipe.title = title
    db_recipe.category = category or ""
    db_recipe.portions = portions or ""
    db_recipe.ingredients = ingredients
    db_recipe.instructions = instructions or ""
    db_recipe.notes = notes or ""
    db_recipe.image_filename = image_filename
    
    db.commit()
    db.refresh(db_recipe)
    return db_recipe

@app.delete("/recipes/{recipe_id}")
def delete_recipe(recipe_id: int, db: Session = Depends(get_db)):
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    
    # Delete associated image if exists
    if recipe.image_filename:
        file_path = UPLOAD_DIR / recipe.image_filename
        if file_path.exists():
            file_path.unlink()
    
    db.delete(recipe)
    db.commit()
    return {"message": "Recipe deleted successfully"}

# Category Management
class CategoryCreate(BaseModel):
    name: str

class CategoryResponse(BaseModel):
    id: int
    name: str
    recipe_count: int

@app.get("/categories", response_model=List[CategoryResponse])
def get_categories(db: Session = Depends(get_db)):
    # Get all categories from Category table and recipe categories with counts
    category_recipes = db.query(
        Recipe.category.label('name'),
        func.count(Recipe.id).label('recipe_count')
    ).filter(
        Recipe.category.isnot(None),
        Recipe.category != ""
    ).group_by(Recipe.category).all()
    
    # Get standalone categories from Category table
    standalone_categories = db.query(Category).all()
    
    # Combine and deduplicate
    category_dict = {}
    
    # Add recipe categories with counts
    for name, count in category_recipes:
        category_dict[name] = count
    
    # Add standalone categories (with 0 count if not in recipes)
    for cat in standalone_categories:
        if cat.name not in category_dict:
            category_dict[cat.name] = 0
    
    # Convert to response format
    categories = []
    for i, (name, count) in enumerate(sorted(category_dict.items()), 1):
        categories.append(CategoryResponse(id=i, name=name, recipe_count=count))
    
    return categories

@app.get("/categories/simple")
def get_simple_categories(db: Session = Depends(get_db)):
    """Simple list of category names for backwards compatibility"""
    # Get categories from both tables
    recipe_categories = db.query(Recipe.category).distinct().all()
    standalone_categories = db.query(Category.name).all()
    
    # Combine and deduplicate
    all_categories = set()
    for cat in recipe_categories:
        if cat[0]:
            all_categories.add(cat[0])
    for cat in standalone_categories:
        all_categories.add(cat[0])
    
    return sorted(list(all_categories))

@app.post("/categories", response_model=dict)
def create_category(category: CategoryCreate, db: Session = Depends(get_db)):
    """Create a new category"""
    # Check if category already exists in Category table or recipes
    existing_category = db.query(Category).filter(Category.name == category.name).first()
    existing_recipe_category = db.query(Recipe).filter(Recipe.category == category.name).first()
    
    if existing_category or existing_recipe_category:
        return {"message": "Category already exists", "category": category.name}
    
    # Create new category
    db_category = Category(name=category.name)
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    
    return {"message": f"Category '{category.name}' created successfully", "category": category.name}

@app.put("/categories/{old_name}")
def update_category(old_name: str, category: CategoryCreate, db: Session = Depends(get_db)):
    """Rename a category across all recipes and standalone categories"""
    # Update all recipes with the old category name
    updated_count = db.query(Recipe).filter(
        Recipe.category == old_name
    ).update({Recipe.category: category.name})
    
    # Check for standalone category
    standalone_category = db.query(Category).filter(Category.name == old_name).first()
    
    if updated_count == 0 and not standalone_category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    # Update standalone category if it exists
    if standalone_category:
        standalone_category.name = category.name
    
    db.commit()
    return {"message": f"Renamed category '{old_name}' to '{category.name}'", "updated_recipes": updated_count}

@app.delete("/categories/{category_name}")
def delete_category(category_name: str, action: str = Query("clear", description="Action: 'clear' or 'delete_recipes'"), db: Session = Depends(get_db)):
    """Delete/clear a category"""
    recipes_with_category = db.query(Recipe).filter(Recipe.category == category_name).all()
    standalone_category = db.query(Category).filter(Category.name == category_name).first()
    
    # Check if category exists anywhere
    if not recipes_with_category and not standalone_category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    if action == "delete_recipes" and recipes_with_category:
        # Delete all recipes in this category
        for recipe in recipes_with_category:
            # Delete associated images
            if recipe.image_filename:
                file_path = UPLOAD_DIR / recipe.image_filename
                if file_path.exists():
                    file_path.unlink()
            db.delete(recipe)
        deleted_count = len(recipes_with_category)
        
        # Also delete standalone category if it exists
        if standalone_category:
            db.delete(standalone_category)
        
        db.commit()
        return {"message": f"Deleted category '{category_name}' and {deleted_count} recipes"}
    else:
        # Clear the category from recipes (set to empty)
        updated_count = 0
        if recipes_with_category:
            updated_count = db.query(Recipe).filter(
                Recipe.category == category_name
            ).update({Recipe.category: ""})
        
        # Delete standalone category
        if standalone_category:
            db.delete(standalone_category)
        
        db.commit()
        
        if updated_count > 0:
            return {"message": f"Cleared category '{category_name}' from {updated_count} recipes"}
        else:
            return {"message": f"Deleted empty category '{category_name}'"}

@app.get("/recipes/category/{category}", response_model=List[RecipeResponse])
def get_recipes_by_category(category: str, db: Session = Depends(get_db)):
    recipes = db.query(Recipe).filter(Recipe.category == category).all()
    return recipes

@app.get("/search/recipes", response_model=List[RecipeResponse])
def search_recipes(q: str = Query(..., description="Search term"), db: Session = Depends(get_db)):
    """Advanced search endpoint with ranking"""
    search_query = text("""
        SELECT *, ts_rank(
            to_tsvector('german', 
                coalesce(title,'') || ' ' || 
                coalesce(ingredients,'') || ' ' || 
                coalesce(instructions,'') || ' ' || 
                coalesce(notes,'') || ' ' || 
                coalesce(category,'')
            ), 
            plainto_tsquery('german', :search_term)
        ) as rank
        FROM recipes 
        WHERE to_tsvector('german', 
            coalesce(title,'') || ' ' || 
            coalesce(ingredients,'') || ' ' || 
            coalesce(instructions,'') || ' ' || 
            coalesce(notes,'') || ' ' || 
            coalesce(category,'')
        ) @@ plainto_tsquery('german', :search_term)
        ORDER BY rank DESC, title ASC
        LIMIT 50
    """)
    
    result = db.execute(search_query, {"search_term": q})
    
    recipes = []
    for row in result:
        recipe = Recipe(
            id=row.id,
            title=row.title,
            category=row.category,
            portions=row.portions,
            ingredients=row.ingredients,
            instructions=row.instructions,
            notes=row.notes,
            created_date=row.created_date
        )
        recipes.append(recipe)
    return recipes

class PortionScale(BaseModel):
    original_portions: str
    target_portions: int
    
class ScaledRecipeResponse(RecipeResponse):
    scaled_ingredients: str
    scaling_factor: float

class ShoppingListRequest(BaseModel):
    recipe_ids: List[int]
    portions_override: Optional[dict] = {}  # Optional dict of recipe_id -> desired_portions

class IngredientItem(BaseModel):
    name: str
    amount: Optional[float] = None
    unit: Optional[str] = None
    recipes: List[str]  # List of recipe titles that contain this ingredient

class ShoppingListResponse(BaseModel):
    ingredients: List[IngredientItem]
    recipe_count: int

@app.post("/recipes/{recipe_id}/scale", response_model=ScaledRecipeResponse)
def scale_recipe_portions(recipe_id: int, scale_request: PortionScale, db: Session = Depends(get_db)):
    """Scale recipe ingredients for different portion sizes"""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    
    # Simple portion scaling logic
    import re
    
    def scale_ingredient_line(line: str, factor: float) -> str:
        # Match numbers (including decimals) at the start of ingredient lines
        number_pattern = r'^(\d+(?:[,.]\d+)?)\s*'
        match = re.match(number_pattern, line.strip())
        
        if match:
            original_amount = float(match.group(1).replace(',', '.'))
            scaled_amount = original_amount * factor
            
            # Format the scaled amount nicely
            if scaled_amount == int(scaled_amount):
                scaled_str = str(int(scaled_amount))
            else:
                scaled_str = f"{scaled_amount:.1f}".replace('.', ',')
            
            return re.sub(number_pattern, f"{scaled_str} ", line.strip())
        
        return line.strip()
    
    # Extract original portion count (simple heuristic)
    original_portions_text = recipe.portions.lower()
    original_count = 1
    
    # Try to extract number from portion text
    portion_match = re.search(r'(\d+)', original_portions_text)
    if portion_match:
        original_count = int(portion_match.group(1))
    
    scaling_factor = scale_request.target_portions / original_count if original_count > 0 else 1.0
    
    # Scale ingredients
    ingredient_lines = recipe.ingredients.split('\n') if recipe.ingredients else []
    scaled_lines = [scale_ingredient_line(line, scaling_factor) for line in ingredient_lines]
    scaled_ingredients = '\n'.join(scaled_lines)
    
    return ScaledRecipeResponse(
        id=recipe.id,
        title=recipe.title,
        category=recipe.category,
        portions=f"{scale_request.target_portions} Portionen",
        ingredients=recipe.ingredients,
        instructions=recipe.instructions,
        notes=recipe.notes,
        created_date=recipe.created_date,
        scaled_ingredients=scaled_ingredients,
        scaling_factor=scaling_factor
    )

@app.post("/recipes/{recipe_id}/image")
async def upload_recipe_image(recipe_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload an image for a recipe"""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    
    # Validate file type
    allowed_types = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, and WebP images are allowed")
    
    # Generate unique filename
    file_extension = file.filename.split('.')[-1].lower()
    unique_filename = f"{uuid.uuid4()}.{file_extension}"
    file_path = UPLOAD_DIR / unique_filename
    
    try:
        # Save file
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Update recipe with image filename
        recipe.image_filename = unique_filename
        db.commit()
        
        return {"message": "Image uploaded successfully", "filename": unique_filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not save image: {str(e)}")

@app.delete("/recipes/{recipe_id}/image")
def delete_recipe_image(recipe_id: int, db: Session = Depends(get_db)):
    """Delete an image for a recipe"""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    
    if recipe.image_filename:
        # Delete file from filesystem
        file_path = UPLOAD_DIR / recipe.image_filename
        if file_path.exists():
            file_path.unlink()
        
        # Remove filename from database
        recipe.image_filename = None
        db.commit()
        
        return {"message": "Image deleted successfully"}
    else:
        raise HTTPException(status_code=404, detail="No image found for this recipe")

@app.post("/shopping-list", response_model=ShoppingListResponse)
def generate_shopping_list(request: ShoppingListRequest, db: Session = Depends(get_db)):
    """Generate a consolidated shopping list from selected recipes"""
    
    # Get recipes
    recipes = db.query(Recipe).filter(Recipe.id.in_(request.recipe_ids)).all()
    if not recipes:
        raise HTTPException(status_code=404, detail="No recipes found")
    
    def parse_ingredient_line(line: str, recipe_title: str, portion_multiplier: float = 1.0) -> IngredientItem:
        """Parse a single ingredient line"""
        line = line.strip()
        if not line:
            return None
            
        # Regex patterns for different ingredient formats
        patterns = [
            # "500g Mehl" or "500 g Mehl"
            r'^(\d+(?:[,.]?\d+)?)\s*([a-zA-ZäöüßÄÖÜ]*)\s+(.+)$',
            # "1 Prise Salz" 
            r'^(\d+(?:[,.]?\d+)?)\s+(Prise|Prisen|EL|TL|Esslöffel|Teelöffel|Becher|Tasse|Tassen|Liter|ml|cl|dl|kg|g|Stück|Stk)\s+(.+)$',
            # "Salz nach Geschmack" (no amount)
            r'^(.+)$'
        ]
        
        for pattern in patterns:
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                groups = match.groups()
                
                if len(groups) == 3 and groups[0].replace(',', '.').replace('.', '').isdigit():
                    # Has amount and unit
                    amount = float(groups[0].replace(',', '.')) * portion_multiplier
                    unit = groups[1].strip()
                    name = groups[2].strip()
                elif len(groups) == 3:
                    # Pattern with Prise, EL, TL etc.
                    try:
                        amount = float(groups[0].replace(',', '.')) * portion_multiplier
                        unit = groups[1].strip()
                        name = groups[2].strip()
                    except:
                        amount = None
                        unit = None
                        name = line
                else:
                    # No amount, just ingredient name
                    amount = None
                    unit = None
                    name = line
                
                return IngredientItem(
                    name=name,
                    amount=amount,
                    unit=unit,
                    recipes=[recipe_title]
                )
        
        return IngredientItem(name=line, recipes=[recipe_title])
    
    def merge_ingredients(ingredients: List[IngredientItem]) -> List[IngredientItem]:
        """Merge similar ingredients"""
        merged = {}
        
        for ingredient in ingredients:
            if not ingredient:
                continue
                
            # Create a key for merging (normalize name)
            key = ingredient.name.lower().strip()
            
            if key in merged:
                # Merge with existing
                existing = merged[key]
                existing.recipes.extend(ingredient.recipes)
                existing.recipes = list(set(existing.recipes))  # Remove duplicates
                
                # Try to merge amounts if units match
                if (existing.amount is not None and ingredient.amount is not None and 
                    existing.unit and ingredient.unit and 
                    existing.unit.lower() == ingredient.unit.lower()):
                    existing.amount += ingredient.amount
                elif existing.amount is None and ingredient.amount is not None:
                    existing.amount = ingredient.amount
                    existing.unit = ingredient.unit
            else:
                merged[key] = ingredient
        
        return list(merged.values())
    
    # Process all recipes
    all_ingredients = []
    
    for recipe in recipes:
        # Get portion multiplier
        recipe_id = recipe.id
        original_portions = 1
        target_portions = request.portions_override.get(recipe_id, 1)
        
        # Try to extract portion count from recipe
        if recipe.portions:
            portion_match = re.search(r'(\d+)', recipe.portions)
            if portion_match:
                original_portions = int(portion_match.group(1))
        
        multiplier = target_portions / original_portions if original_portions > 0 else 1.0
        
        # Parse ingredients
        if recipe.ingredients:
            lines = recipe.ingredients.split('\n')
            for line in lines:
                ingredient = parse_ingredient_line(line, recipe.title, multiplier)
                if ingredient:
                    all_ingredients.append(ingredient)
    
    # Merge similar ingredients
    merged_ingredients = merge_ingredients(all_ingredients)
    
    # Sort by name
    merged_ingredients.sort(key=lambda x: x.name.lower())
    
    return ShoppingListResponse(
        ingredients=merged_ingredients,
        recipe_count=len(recipes)
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)