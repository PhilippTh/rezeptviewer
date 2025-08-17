from fastapi import FastAPI, Depends, HTTPException, Query, File, UploadFile, Form, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from typing import List, Optional
from datetime import date, datetime
from schema import *
import os
import uuid
import re
import subprocess
import tempfile
from pathlib import Path
from database import get_db, Recipe, Category, User, create_tables

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

# Session management
SESSIONS = {}  # Simple in-memory session store

def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in SESSIONS:
        return None
    
    username = SESSIONS[session_id]
    return db.query(User).filter(User.username == username).first()

def require_admin(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_current_user(request, db)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

# Create tables on startup
@app.on_event("startup")
async def startup_event():
    create_tables()

@app.get("/")
def read_root():
    return RedirectResponse(url="/static/frontend.html")

# Authentication endpoints
@app.post("/auth/login")
async def login(login_request: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == login_request.username).first()
    
    if not user or not user.verify_password(login_request.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Create session
    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = user.username
    
    # Set secure cookie
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",
        max_age=86400  # 24 hours
    )
    
    return {"message": "Login successful", "user": UserInfo(username=user.username, is_admin=user.is_admin)}

@app.post("/auth/logout")
async def logout(request: Request, response: Response):
    session_id = request.cookies.get("session_id")
    if session_id in SESSIONS:
        del SESSIONS[session_id]
    
    response.delete_cookie("session_id")
    return {"message": "Logout successful"}

@app.get("/auth/me")
async def get_current_user_info(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return {"authenticated": False}
    
    return {
        "authenticated": True, 
        "user": UserInfo(username=user.username, is_admin=user.is_admin)
    }

@app.post("/auth/change-password")
async def change_password(password_request: PasswordChangeRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Change admin password"""
    # Verify current password
    if not current_user.verify_password(password_request.current_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    # Update password
    current_user.password_hash = User.hash_password(password_request.new_password)
    db.commit()
    
    return {"message": "Password changed successfully"}

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
    request: Request,
    title: str = Form(...),
    category: str = Form(""),
    portions: str = Form(""),
    ingredients: str = Form(...),
    instructions: str = Form(""),
    notes: str = Form(""),
    image: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
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
    request: Request,
    title: str = Form(...),
    category: str = Form(""),
    portions: str = Form(""),
    ingredients: str = Form(...),
    instructions: str = Form(""),
    notes: str = Form(""),
    image: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
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
def delete_recipe(recipe_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
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
def create_category(category: CategoryCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
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
def update_category(old_name: str, category: CategoryCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
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
def delete_category(category_name: str, request: Request, action: str = Query("clear", description="Action: 'clear' or 'delete_recipes'"), db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
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
async def upload_recipe_image(recipe_id: int, request: Request, file: UploadFile = File(...), db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
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
def delete_recipe_image(recipe_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
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

@app.get("/admin/export/database")
async def export_database(request: Request, current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Export the complete database as SQL dump"""
    try:
        # First, try to use pg_dump if available
        try:
            return await _export_with_pg_dump()
        except Exception as pg_dump_error:
            # Fallback to SQLAlchemy-based export
            print(f"pg_dump failed, using fallback method: {pg_dump_error}")
            return await _export_with_sqlalchemy(db)
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export database: {str(e)}")

async def _export_with_pg_dump():
    """Try to export using pg_dump"""
    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        # Build from individual components
        db_host = os.getenv("DB_HOST", "postgres" if os.path.exists("/.dockerenv") else "localhost")
        db_port = os.getenv("DB_PORT", "5432")
        db_name = os.getenv("DB_NAME", "rezepte_db")
        db_user = os.getenv("DB_USER", "rezepte_user")
        db_password = os.getenv("DB_PASSWORD", "rezepte_password")
        database_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    
    # Check if pg_dump is available
    try:
        subprocess.run(["pg_dump", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise Exception("pg_dump not available")
    
    # Create temporary file for the SQL dump
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as temp_file:
        temp_file_path = temp_file.name
    
    try:
        # Use pg_dump with connection string
        cmd = [
            "pg_dump",
            database_url,
            "--no-password",
            "--verbose",
            "--clean",
            "--create",
            "--if-exists",
            "--file", temp_file_path
        ]
        
        # Execute pg_dump
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode != 0:
            raise Exception(f"pg_dump failed: {result.stderr}")
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"rezepte_database_backup_{timestamp}.sql"
        
        # Return the file
        return FileResponse(
            path=temp_file_path,
            filename=filename,
            media_type="application/sql"
        )
        
    except Exception as e:
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
        raise e

async def _export_with_sqlalchemy(db: Session):
    """Fallback export using SQLAlchemy"""
    try:
        # Generate SQL statements for all data
        sql_lines = []
        
        # Add header
        sql_lines.append("-- Recipe Database Export")
        sql_lines.append(f"-- Generated: {datetime.now().isoformat()}")
        sql_lines.append("-- Exported using SQLAlchemy fallback method")
        sql_lines.append("")
        
        # Export Users table
        sql_lines.append("-- Users")
        users = db.query(User).all()
        for user in users:
            sql_lines.append(f"INSERT INTO users (username, password_hash, is_admin) VALUES ('{user.username}', '{user.password_hash}', {user.is_admin});")
        sql_lines.append("")
        
        # Export Categories table
        sql_lines.append("-- Categories")
        categories = db.query(Category).all()
        for category in categories:
            safe_name = category.name.replace("'", "''")
            sql_lines.append(f"INSERT INTO categories (name) VALUES ('{safe_name}');")
        sql_lines.append("")
        
        # Export Recipes table
        sql_lines.append("-- Recipes")
        recipes = db.query(Recipe).all()
        for recipe in recipes:
            title = recipe.title.replace("'", "''") if recipe.title else ''
            category = recipe.category.replace("'", "''") if recipe.category else ''
            portions = recipe.portions.replace("'", "''") if recipe.portions else ''
            ingredients = recipe.ingredients.replace("'", "''") if recipe.ingredients else ''
            instructions = recipe.instructions.replace("'", "''") if recipe.instructions else ''
            notes = recipe.notes.replace("'", "''") if recipe.notes else ''
            
            # Handle image filename
            if recipe.image_filename:
                image_part = f"'{recipe.image_filename}'"
            else:
                image_part = 'NULL'
                
            # Handle created date
            if recipe.created_date:
                date_part = f"'{recipe.created_date}'"
            else:
                date_part = 'NULL'
            
            sql_lines.append(
                f"INSERT INTO recipes (title, category, portions, ingredients, instructions, notes, image_filename, created_date) "
                f"VALUES ('{title}', '{category}', '{portions}', '{ingredients}', '{instructions}', '{notes}', "
                f"{image_part}, {date_part});"
            )
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False, encoding='utf-8') as temp_file:
            temp_file.write('\n'.join(sql_lines))
            temp_file_path = temp_file.name
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"rezepte_database_fallback_{timestamp}.sql"
        
        return FileResponse(
            path=temp_file_path,
            filename=filename,
            media_type="application/sql"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fallback export failed: {str(e)}")

@app.get("/admin/export/recipes")
async def export_recipes_json(request: Request, current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Export all recipes as JSON"""
    try:
        # Get all recipes
        recipes = db.query(Recipe).all()
        
        # Convert to dict format
        recipes_data = []
        for recipe in recipes:
            recipe_dict = {
                "id": recipe.id,
                "title": recipe.title,
                "category": recipe.category,
                "portions": recipe.portions,
                "ingredients": recipe.ingredients,
                "instructions": recipe.instructions,
                "notes": recipe.notes,
                "created_date": recipe.created_date.isoformat() if recipe.created_date else None,
                "image_filename": recipe.image_filename
            }
            recipes_data.append(recipe_dict)
        
        # Create temporary JSON file
        import json
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as temp_file:
            json.dump(recipes_data, temp_file, ensure_ascii=False, indent=2)
            temp_file_path = temp_file.name
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"rezepte_export_{timestamp}.json"
        
        return FileResponse(
            path=temp_file_path,
            filename=filename,
            media_type="application/json"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export recipes: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)