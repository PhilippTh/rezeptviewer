const API_BASE = '';
let allRecipes = [];
let currentSort = 'title';
let currentUser = null;

// Portion calculator state management
let portionStates = {}; // Store portion multipliers for each recipe

// Load portion states from localStorage on page load
function loadPortionStates() {
    try {
        const saved = localStorage.getItem('rezeptviewer_portions');
        if (saved) {
            portionStates = JSON.parse(saved);
        }
    } catch (error) {
        console.error('Error loading portion states:', error);
        portionStates = {};
    }
}

// Save portion states to localStorage
function savePortionStates() {
    try {
        localStorage.setItem('rezeptviewer_portions', JSON.stringify(portionStates));
    } catch (error) {
        console.error('Error saving portion states:', error);
    }
}

// Get current portion multiplier for a recipe
function getPortionMultiplier(recipeId) {
    return portionStates[recipeId] || 1.0;
}

// Set portion multiplier for a recipe
function setPortionMultiplier(recipeId, multiplier) {
    portionStates[recipeId] = multiplier;
    savePortionStates();
}

// Get current portions for display (considering saved multiplier)
function getCurrentPortions(recipeId, originalPortions) {
    const multiplier = getPortionMultiplier(recipeId);
    const original = parseFloat(originalPortions) || 1;
    const current = (original * multiplier).toFixed(1).replace(/\.0$/, '');
    return current;
}

// Reset portion to original
function resetPortion(recipeId) {
    const recipe = allRecipes.find(r => r.id === recipeId);
    if (!recipe) return;

    // Reset multiplier
    setPortionMultiplier(recipeId, 1.0);

    const originalPortions = parseFloat(recipe.portions) || 1;

    // Update card view
    const currentElement = document.getElementById(`current-portions-${recipeId}`);
    const ingredientsElement = document.getElementById(`ingredients-${recipeId}`);
    if (currentElement && ingredientsElement) {
        currentElement.textContent = originalPortions;
        ingredientsElement.innerHTML = recipe.ingredients;
    }

    // Update single recipe view if open
    const singleCurrentElement = document.getElementById(`single-current-portions-${recipeId}`);
    const singleIngredientsElement = document.getElementById(`single-ingredients-${recipeId}`);
    if (singleCurrentElement && singleIngredientsElement) {
        singleCurrentElement.textContent = originalPortions;
        singleIngredientsElement.innerHTML = recipe.ingredients;
    }
}

// Get ingredients scaled according to saved multiplier
function getScaledIngredients(recipeId, originalIngredients) {
    const multiplier = getPortionMultiplier(recipeId);
    if (multiplier === 1.0) {
        return originalIngredients;
    }
    return scaleIngredients(originalIngredients, multiplier);
}

document.addEventListener('DOMContentLoaded', function () {
    // Initialize admin buttons as hidden
    updateAdminButtons();

    // Load portion states from localStorage
    loadPortionStates();

    // Then check auth status
    checkAuthStatus();
    loadRecipes();
    loadCategories();

    // Add Enter key support for login
    document.getElementById('password').addEventListener('keypress', function (e) {
        if (e.key === 'Enter') {
            login();
        }
    });
});

async function checkAuthStatus() {
    try {
        const response = await fetch(`${API_BASE}/auth/me`, {
            credentials: 'include' // Include cookies in request
        });
        const result = await response.json();

        console.log('Auth status check:', result); // Debug log

        if (result.authenticated) {
            currentUser = result.user;
            console.log('User authenticated:', currentUser); // Debug log
            showUserSection();
            updateAdminButtons();
        } else {
            currentUser = null;
            showLoginSection();
            updateAdminButtons();
        }
    } catch (error) {
        console.error('Error checking auth status:', error);
        currentUser = null;
        showLoginSection();
        updateAdminButtons();
    }
}

function showLoginSection() {
    document.getElementById('loginSection').style.display = 'flex';
    document.getElementById('userSection').style.display = 'none';
}

function showUserSection() {
    document.getElementById('loginSection').style.display = 'none';
    document.getElementById('userSection').style.display = 'flex';
    document.getElementById('userDisplay').textContent = `👤 ${currentUser.username}${currentUser.is_admin ? ' (Admin)' : ''}`;
}

function updateAdminButtons() {
    const adminButtons = document.querySelectorAll('.admin-buttons');
    adminButtons.forEach(button => {
        if (currentUser && currentUser.is_admin) {
            button.classList.add('show');
        } else {
            button.classList.remove('show');
        }
    });

    // Refresh recipes to show/hide edit/delete buttons
    displayRecipes(allRecipes);
}

async function login() {
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;

    if (!username || !password) {
        alert('Bitte Benutzername und Passwort eingeben.');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
            credentials: 'include' // Include cookies in request
        });

        if (response.ok) {
            const result = await response.json();
            currentUser = result.user;
            console.log('Login successful, user:', currentUser); // Debug log
            showUserSection();
            updateAdminButtons();

            // Clear login form
            document.getElementById('username').value = '';
            document.getElementById('password').value = '';

            alert(`Willkommen, ${currentUser.username}!`);
        } else {
            const errorText = await response.text();
            console.error('Login failed:', response.status, errorText);
            alert('Ungültige Anmeldedaten.');
        }
    } catch (error) {
        console.error('Login error:', error);
        alert('Fehler beim Anmelden.');
    }
}

async function logout() {
    try {
        await fetch(`${API_BASE}/auth/logout`, {
            method: 'POST',
            credentials: 'include'
        });
        currentUser = null;
        showLoginSection();
        updateAdminButtons();
        alert('Erfolgreich abgemeldet.');
    } catch (error) {
        console.error('Logout error:', error);
        alert('Fehler beim Abmelden.');
    }
}

function showPasswordChangeForm() {
    document.getElementById('passwordChangeForm').style.display = 'block';
    document.getElementById('passwordChangeForm').scrollIntoView({ behavior: 'smooth' });
}

function closePasswordChangeForm() {
    document.getElementById('passwordChangeForm').style.display = 'none';
    // Clear form
    document.getElementById('currentPassword').value = '';
    document.getElementById('newPassword').value = '';
    document.getElementById('confirmPassword').value = '';
}

async function changePassword() {
    const currentPassword = document.getElementById('currentPassword').value;
    const newPassword = document.getElementById('newPassword').value;
    const confirmPassword = document.getElementById('confirmPassword').value;

    if (!currentPassword || !newPassword || !confirmPassword) {
        alert('Bitte alle Felder ausfüllen.');
        return;
    }

    if (newPassword !== confirmPassword) {
        alert('Neues Passwort und Bestätigung stimmen nicht überein.');
        return;
    }

    if (newPassword.length < 6) {
        alert('Das neue Passwort muss mindestens 6 Zeichen lang sein.');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/auth/change-password`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                current_password: currentPassword,
                new_password: newPassword
            }),
            credentials: 'include'
        });

        if (response.ok) {
            alert('Passwort erfolgreich geändert!');
            closePasswordChangeForm();
        } else {
            const errorData = await response.json();
            alert(`Fehler: ${errorData.detail || 'Passwort konnte nicht geändert werden'}`);
        }
    } catch (error) {
        console.error('Password change error:', error);
        alert('Fehler beim Ändern des Passworts.');
    }
}

async function loadRecipes() {
    try {
        const response = await fetch(`${API_BASE}/recipes`);
        allRecipes = await response.json();
        sortRecipes();
    } catch (error) {
        console.error('Error loading recipes:', error);
        document.getElementById('recipeGrid').innerHTML = '<p>Fehler beim Laden der Rezepte.</p>';
    }
}

async function loadCategories() {
    try {
        const response = await fetch(`${API_BASE}/categories/simple`);
        const categories = await response.json();

        // Update filter dropdown
        const filterSelect = document.getElementById('categoryFilter');
        filterSelect.innerHTML = '<option value="">📂 Alle Kategorien</option>';

        // Update recipe form dropdown
        const categorySelect = document.getElementById('category');
        categorySelect.innerHTML = '<option value="">-- Kategorie wählen --</option>';

        categories.forEach(cat => {
            if (cat) {
                // Filter dropdown
                const filterOption = document.createElement('option');
                filterOption.value = cat;
                filterOption.textContent = cat;
                filterSelect.appendChild(filterOption);

                // Form dropdown
                const formOption = document.createElement('option');
                formOption.value = cat;
                formOption.textContent = cat;
                categorySelect.appendChild(formOption);
            }
        });

        // Add "New Category" option
        const newOption = document.createElement('option');
        newOption.value = '__NEW__';
        newOption.textContent = '+ Neue Kategorie';
        categorySelect.appendChild(newOption);

    } catch (error) {
        console.error('Error loading categories:', error);
    }
}

// Handle category dropdown change
document.addEventListener('DOMContentLoaded', function () {
    const categorySelect = document.getElementById('category');
    const newCategoryInput = document.getElementById('newCategory');

    if (categorySelect) {
        categorySelect.addEventListener('change', function () {
            if (this.value === '__NEW__') {
                newCategoryInput.style.display = 'block';
                newCategoryInput.focus();
            } else {
                newCategoryInput.style.display = 'none';
                newCategoryInput.value = '';
            }
        });
    }
});

function displayRecipes(recipes) {
    const grid = document.getElementById('recipeGrid');
    grid.innerHTML = '';

    if (recipes.length === 0) {
        grid.innerHTML = '<p style="text-align: center; color: white; font-size: 1.2em;">Keine Rezepte gefunden.</p>';
        return;
    }

    recipes.forEach((recipe, index) => {
        const card = document.createElement('div');
        card.className = 'recipe-card clickable fade-in';
        card.style.animationDelay = `${index * 0.1}s`;

        card.innerHTML = `
            <div class="recipe-card-click-hint">Klicken zum Anzeigen</div>
            ${recipe.image_filename ? `<img src="/uploads/${recipe.image_filename}" alt="${recipe.title}" class="recipe-image">` : ''}
            
            <div class="recipe-card-content">
                <div class="recipe-header">
                    <h2 class="recipe-title">${recipe.title || 'Ohne Titel'}</h2>
                </div>
                
                <div class="recipe-meta">
                    ${recipe.category ? `<div class="meta-item">📂 ${recipe.category}</div>` : ''}
                    ${recipe.portions ? `<div class="meta-item">👥 ${recipe.portions}</div>` : ''}
                    ${recipe.created_date ? `<div class="meta-item">📅 ${recipe.created_date}</div>` : ''}
                </div>
                
                <div class="recipe-actions">
                    <button class="btn btn-small btn-secondary" onclick="event.stopPropagation(); togglePortionCalculator(${recipe.id})">
                        📊 Portionen
                    </button>
                    <button class="btn btn-small btn-secondary" onclick="event.stopPropagation(); printRecipe(${recipe.id})">
                        🖨️ Drucken
                    </button>
                    ${currentUser && currentUser.is_admin ? `
                    <button class="btn btn-small btn-primary" onclick="event.stopPropagation(); editRecipe(${recipe.id})">
                        ✏️ Bearbeiten
                    </button>
                    <button class="btn btn-small btn-danger" onclick="event.stopPropagation(); deleteRecipe(${recipe.id})">
                        🗑️ Löschen
                    </button>
                    ` : ''}
                </div>
                
                <div class="recipe-content">
                    ${recipe.ingredients ? `
                        <div class="recipe-section">
                            <h4>🥄 Zutaten:</h4>
                            <p id="ingredients-${recipe.id}">${getScaledIngredients(recipe.id, recipe.ingredients)}</p>
                        </div>
                    ` : ''}
                    ${recipe.instructions ? `
                        <div class="recipe-section">
                            <h4>👨‍🍳 Anweisungen:</h4>
                            <p>${recipe.instructions}</p>
                        </div>
                    ` : ''}
                    ${recipe.notes ? `
                        <div class="recipe-section">
                            <h4>💡 Hinweise:</h4>
                            <p>${recipe.notes}</p>
                        </div>
                    ` : ''}
                </div>
                
                <div class="portion-calculator" id="calculator-${recipe.id}" style="display: none;">
                    <div class="portion-controls">
                        <button class="portion-btn" onclick="event.stopPropagation(); adjustPortion(${recipe.id}, -1)">−</button>
                        <div class="portion-display">
                            <span id="current-portions-${recipe.id}">${getCurrentPortions(recipe.id, recipe.portions)}</span> Portionen
                        </div>
                        <button class="portion-btn" onclick="event.stopPropagation(); adjustPortion(${recipe.id}, 1)">+</button>
                    </div>
                    <div style="font-size: 0.9em; color: var(--neutral-600); margin-top: 8px;">
                        Original: ${recipe.portions} Portionen
                        <button class="btn btn-small btn-secondary" onclick="event.stopPropagation(); resetPortion(${recipe.id})" style="margin-left: 8px; padding: 2px 6px; font-size: 0.8em;">↺ Reset</button>
                    </div>
                </div>
            </div>
        `;

        // Add click event to open single recipe view
        card.addEventListener('click', function () {
            openSingleRecipe(recipe.id);
        });

        grid.appendChild(card);
    });
}

function togglePortionCalculator(recipeId) {
    const calculator = document.getElementById(`calculator-${recipeId}`);
    calculator.style.display = calculator.style.display === 'none' ? 'block' : 'none';
}

function adjustPortion(recipeId, change) {
    const recipe = allRecipes.find(r => r.id === recipeId);
    const currentElement = document.getElementById(`current-portions-${recipeId}`);
    const ingredientsElement = document.getElementById(`ingredients-${recipeId}`);

    let currentPortions = parseFloat(currentElement.textContent);
    let newPortions = Math.max(0.5, currentPortions + (change * 0.5));

    currentElement.textContent = newPortions;

    const originalPortions = parseFloat(recipe.portions) || 1;
    const scaleFactor = newPortions / originalPortions;

    // Save the multiplier to persistent storage
    setPortionMultiplier(recipeId, scaleFactor);

    const scaledIngredients = scaleIngredients(recipe.ingredients, scaleFactor);
    ingredientsElement.innerHTML = scaledIngredients;

    // Update single recipe view if it's open for the same recipe
    const singleIngredientsElement = document.getElementById(`single-ingredients-${recipeId}`);
    const singleCurrentElement = document.getElementById(`single-current-portions-${recipeId}`);
    if (singleIngredientsElement && singleCurrentElement) {
        singleCurrentElement.textContent = newPortions;
        singleIngredientsElement.innerHTML = scaledIngredients;
    }
}

function scaleIngredients(ingredients, factor) {
    if (!ingredients) return '';

    // Enhanced scaling with better pattern matching
    return ingredients.replace(/(\d+(?:[.,]\d+)?(?:\s*[-–]\s*\d+(?:[.,]\d+)?)?)\s*(g|kg|ml|l|TL|EL|Prise|Stück|Stk\.?|Zehe|Zehen|dag|Liter|lt\.?|Teelöffel|Esslöffel|Messerspitze|MS|Bund|Packung|Dose|Glas|Becher|cl|dl)\b/gi, (match, amount, unit) => {
        // Handle ranges (e.g., "2-3 Stück" or "1,5 - 2 kg")
        if (amount.includes('-') || amount.includes('–')) {
            const rangeParts = amount.split(/\s*[-–]\s*/);
            const scaledRange = rangeParts.map(part => {
                const normalizedAmount = part.replace(',', '.');
                return (parseFloat(normalizedAmount) * factor).toFixed(1).replace(/\.0$/, '');
            }).join(' - ');
            return `${scaledRange} ${unit}`;
        } else {
            // Handle single amounts
            const normalizedAmount = amount.replace(',', '.');
            const scaledAmount = (parseFloat(normalizedAmount) * factor).toFixed(1).replace(/\.0$/, '');
            return `${scaledAmount} ${unit}`;
        }
    }).replace(/(\d+(?:[.,]\d+)?)\s*(Vanilleschoten?|Zitronen?|Orangen?|Äpfel|Zwiebeln?|Knoblauchzehen?|Eier?|Dotter|Eigelb|Eiweiß|Eiklar)/gi, (match, amount, item) => {
        // Handle countable items without explicit units
        const normalizedAmount = amount.replace(',', '.');
        const scaledAmount = Math.max(1, Math.round(parseFloat(normalizedAmount) * factor));
        return `${scaledAmount} ${item}`;
    });
}

function printRecipe(recipeId) {
    const recipe = allRecipes.find(r => r.id === recipeId);
    if (!recipe) return;

    const printWindow = window.open('', '_blank');
    printWindow.document.write(`
        <!DOCTYPE html>
        <html>
        <head>
            <title>${recipe.title}</title>
            <style>
                body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
                .header { text-align: center; margin-bottom: 30px; }
                .logo { max-height: 60px; margin-bottom: 10px; }
                h1 { color: #333; margin: 10px 0; }
                h2 { color: #666; margin: 15px 0 10px 0; }
                .meta { background: #f5f5f5; padding: 15px; border-radius: 8px; margin: 20px 0; }
                .section { margin: 20px 0; }
                .ingredients, .instructions { white-space: pre-wrap; line-height: 1.6; }
                @media print { .no-print { display: none; } }
            </style>
        </head>
        <body>
            <div class="header">
                <img src="/static/logo.png" alt="Waldschenke Logo" class="logo">
                <h1>${recipe.title}</h1>
            </div>
            <div class="meta">
                <strong>Kategorie:</strong> ${recipe.category || 'Nicht angegeben'}<br>
                <strong>Portionen:</strong> ${recipe.portions || 'Nicht angegeben'}<br>
                <strong>Datum:</strong> ${recipe.created_date || 'Nicht angegeben'}
            </div>
            ${recipe.ingredients ? `<div class="section"><h2>🥄 Zutaten:</h2><div class="ingredients">${recipe.ingredients}</div></div>` : ''}
            ${recipe.instructions ? `<div class="section"><h2>👨‍🍳 Anweisungen:</h2><div class="instructions">${recipe.instructions}</div></div>` : ''}
            ${recipe.notes ? `<div class="section"><h2>💡 Hinweise:</h2><div class="instructions">${recipe.notes}</div></div>` : ''}
            <button class="no-print" onclick="window.print()">Drucken</button>
        </body>
        </html>
    `);
    printWindow.document.close();
}

function sortRecipes() {
    const sortBy = document.getElementById('sortBy').value;
    currentSort = sortBy;

    allRecipes.sort((a, b) => {
        switch (sortBy) {
            case 'date':
                return new Date(b.created_date || 0) - new Date(a.created_date || 0);
            case 'category':
                return (a.category || '').localeCompare(b.category || '');
            case 'title':
            default:
                return (a.title || '').localeCompare(b.title || '');
        }
    });

    displayRecipes(allRecipes);
}

function filterByCategory() {
    const category = document.getElementById('categoryFilter').value;
    if (!category) {
        displayRecipes(allRecipes);
    } else {
        const filtered = allRecipes.filter(recipe => recipe.category === category);
        displayRecipes(filtered);
    }
}

function searchRecipes() {
    const search = document.getElementById('searchInput').value.toLowerCase();
    if (!search) {
        displayRecipes(allRecipes);
        return;
    }

    const filtered = allRecipes.filter(recipe =>
        (recipe.title && recipe.title.toLowerCase().includes(search)) ||
        (recipe.ingredients && recipe.ingredients.toLowerCase().includes(search)) ||
        (recipe.instructions && recipe.instructions.toLowerCase().includes(search)) ||
        (recipe.category && recipe.category.toLowerCase().includes(search)) ||
        (recipe.notes && recipe.notes.toLowerCase().includes(search))
    );
    displayRecipes(filtered);
}



function generateShoppingList() {
    const ingredients = [];
    const visibleRecipes = document.querySelectorAll('.recipe-card');

    visibleRecipes.forEach(card => {
        const ingredientText = card.querySelector('[id^="ingredients-"]');
        if (ingredientText) {
            const lines = ingredientText.textContent.split('\n');
            lines.forEach(line => {
                line = line.trim();
                if (line) {
                    ingredients.push(line);
                }
            });
        }
    });

    const shoppingList = document.getElementById('shoppingList');
    const shoppingItems = document.getElementById('shoppingItems');

    shoppingItems.innerHTML = '';
    ingredients.forEach(ingredient => {
        const item = document.createElement('div');
        item.className = 'shopping-item';
        item.innerHTML = `
            <input type="checkbox" id="item-${ingredients.indexOf(ingredient)}">
            <label for="item-${ingredients.indexOf(ingredient)}">${ingredient}</label>
        `;
        shoppingItems.appendChild(item);
    });

    shoppingList.style.display = 'block';
    shoppingList.scrollIntoView({ behavior: 'smooth' });
}

function closeShoppingList() {
    document.getElementById('shoppingList').style.display = 'none';
}

function exportRecipes() {
    if (!currentUser || !currentUser.is_admin) {
        alert('Admin-Zugriff erforderlich für Export-Funktionen.');
        return;
    }

    // Use backend endpoint for JSON export
    window.open(`${API_BASE}/admin/export/recipes`, '_blank');
}

function exportDatabase() {
    if (!currentUser || !currentUser.is_admin) {
        alert('Admin-Zugriff erforderlich für Export-Funktionen.');
        return;
    }

    if (!confirm('SQL-Export der kompletten Datenbank erstellen?\n\nDies kann einige Minuten dauern und erstellt eine vollständige Backup-Datei.')) {
        return;
    }

    // Show loading message
    const originalText = event.target.textContent;
    event.target.textContent = '⏳ Export läuft...';
    event.target.disabled = true;

    // Use backend endpoint for SQL export
    fetch(`${API_BASE}/admin/export/database`, {
        method: 'GET',
        credentials: 'include'
    })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.blob();
        })
        .then(blob => {
            // Create download link
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `rezepte_database_backup_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.sql`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            alert('Datenbank-Export erfolgreich heruntergeladen!');
        })
        .catch(error => {
            console.error('Export error:', error);
            alert('Fehler beim Export der Datenbank. Bitte versuchen Sie es erneut.');
        })
        .finally(() => {
            // Reset button
            event.target.textContent = originalText;
            event.target.disabled = false;
        });
}

// Export Management Functions
function toggleExportManagement() {
    const form = document.getElementById('exportManagement');
    if (form.style.display === 'none' || !form.style.display) {
        form.style.display = 'block';
        form.scrollIntoView({ behavior: 'smooth' });
    } else {
        form.style.display = 'none';
    }
}

// Edit and Delete functionality
let editingRecipeId = null;

function editRecipe(recipeId) {
    const recipe = allRecipes.find(r => r.id === recipeId);
    if (!recipe) return;

    editingRecipeId = recipeId;

    // Update form title
    document.getElementById('formTitle').textContent = '✏️ Rezept bearbeiten';

    // Fill form with current values
    document.getElementById('title').value = recipe.title || '';
    document.getElementById('category').value = recipe.category || '';
    document.getElementById('portions').value = recipe.portions || '';
    document.getElementById('ingredients').value = recipe.ingredients || '';
    document.getElementById('instructions').value = recipe.instructions || '';
    document.getElementById('notes').value = recipe.notes || '';

    // Show form
    document.getElementById('addRecipeForm').style.display = 'block';
    document.getElementById('addRecipeForm').scrollIntoView({ behavior: 'smooth' });
}

async function deleteRecipe(recipeId) {
    const recipe = allRecipes.find(r => r.id === recipeId);
    if (!recipe) return;

    if (!confirm(`Sind Sie sicher, dass Sie "${recipe.title}" löschen möchten?`)) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/recipes/${recipeId}`, {
            method: 'DELETE',
            credentials: 'include'
        });

        if (response.ok) {
            alert('Rezept erfolgreich gelöscht!');
            loadRecipes();
            loadCategories();
        } else {
            alert('Fehler beim Löschen des Rezepts.');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Fehler beim Löschen des Rezepts.');
    }
}

function resetForm() {
    editingRecipeId = null;
    document.getElementById('formTitle').textContent = '➕ Neues Rezept hinzufügen';
    document.querySelector('#addRecipeForm form').reset();
}

async function submitRecipe(event) {
    event.preventDefault();

    const formData = new FormData();
    formData.append('title', document.getElementById('title').value);

    // Handle category selection
    const categorySelect = document.getElementById('category');
    const newCategoryInput = document.getElementById('newCategory');
    let categoryValue = '';

    if (categorySelect.value === '__NEW__' && newCategoryInput.value.trim()) {
        categoryValue = newCategoryInput.value.trim();
    } else if (categorySelect.value && categorySelect.value !== '__NEW__') {
        categoryValue = categorySelect.value;
    }

    formData.append('category', categoryValue);
    formData.append('portions', document.getElementById('portions').value);
    formData.append('ingredients', document.getElementById('ingredients').value);
    formData.append('instructions', document.getElementById('instructions').value);
    formData.append('notes', document.getElementById('notes').value);

    const imageFile = document.getElementById('image').files[0];
    if (imageFile) {
        formData.append('image', imageFile);
    }

    try {
        const url = editingRecipeId
            ? `${API_BASE}/recipes/${editingRecipeId}`
            : `${API_BASE}/recipes`;

        const method = editingRecipeId ? 'PUT' : 'POST';

        const response = await fetch(url, {
            method: method,
            body: formData,
            credentials: 'include'
        });

        if (response.ok) {
            const action = editingRecipeId ? 'aktualisiert' : 'hinzugefügt';
            alert(`Rezept erfolgreich ${action}!`);
            resetForm();
            toggleAddForm();
            loadRecipes();
            loadCategories();
        } else {
            const action = editingRecipeId ? 'Aktualisieren' : 'Hinzufügen';
            alert(`Fehler beim ${action} des Rezepts.`);
        }
    } catch (error) {
        console.error('Error:', error);
        const action = editingRecipeId ? 'Aktualisieren' : 'Hinzufügen';
        alert(`Fehler beim ${action} des Rezepts.`);
    }
}

// Update the toggle function to reset form when closing
function toggleAddForm() {
    const form = document.getElementById('addRecipeForm');
    if (form.style.display === 'none' || !form.style.display) {
        resetForm();
        form.style.display = 'block';
        form.scrollIntoView({ behavior: 'smooth' });
    } else {
        form.style.display = 'none';
        resetForm();
    }
}

// Category Management Functions
async function toggleCategoryManagement() {
    const form = document.getElementById('categoryManagement');
    if (form.style.display === 'none' || !form.style.display) {
        await loadCategoryManagement();
        form.style.display = 'block';
        form.scrollIntoView({ behavior: 'smooth' });
    } else {
        form.style.display = 'none';
    }
}

async function loadCategoryManagement() {
    try {
        const response = await fetch(`${API_BASE}/categories`);
        const categories = await response.json();
        const container = document.getElementById('categoryList');

        container.innerHTML = `
            <div style="margin-bottom: 20px; padding: 16px; background: #e6fffa; border-radius: 8px; border: 1px solid #81e6d9;">
                <h4 style="margin: 0 0 12px 0; color: #2d3748;">➕ Neue Kategorie erstellen</h4>
                <div style="display: flex; gap: 8px; align-items: center;">
                    <input type="text" id="newCategoryName" placeholder="Kategorie-Name eingeben..." 
                           style="flex: 1; padding: 8px 12px; border: 2px solid #4fd1c7; border-radius: 6px;"
                           onkeypress="if(event.key==='Enter') createNewCategory()">
                    <button class="btn btn-primary" onclick="createNewCategory()">
                        ✅ Erstellen
                    </button>
                </div>
            </div>
            <div style="margin-bottom: 16px;">
                <h4 style="margin: 0; color: #2d3748;">📂 Vorhandene Kategorien</h4>
            </div>
        `;

        categories.forEach(category => {
            const categoryDiv = document.createElement('div');
            categoryDiv.className = 'category-item';
            categoryDiv.style.cssText = 'display: flex; align-items: center; justify-content: space-between; padding: 12px; margin-bottom: 8px; background: #f7fafc; border-radius: 8px; border: 1px solid #e2e8f0;';

            categoryDiv.innerHTML = `
                <div>
                    <strong>${category.name}</strong>
                    <span style="color: #666; margin-left: 8px;">(${category.recipe_count} Rezepte)</span>
                </div>
                <div style="display: flex; gap: 8px;">
                    <button class="btn btn-small btn-secondary" onclick="editCategory('${category.name}')">
                        ✏️ Umbenennen
                    </button>
                    <button class="btn btn-small btn-danger" onclick="deleteCategory('${category.name}', ${category.recipe_count})">
                        🗑️ Löschen
                    </button>
                </div>
            `;

            container.appendChild(categoryDiv);
        });

    } catch (error) {
        console.error('Error loading category management:', error);
    }
}

async function editCategory(oldName) {
    const newName = prompt(`Kategorie "${oldName}" umbenennen zu:`, oldName);
    if (!newName || newName === oldName) return;

    try {
        const response = await fetch(`${API_BASE}/categories/${encodeURIComponent(oldName)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: newName }),
            credentials: 'include'
        });

        if (response.ok) {
            const result = await response.json();
            alert(`Kategorie erfolgreich umbenannt! ${result.updated_recipes} Rezepte aktualisiert.`);
            await loadCategoryManagement();
            await loadCategories();
            await loadRecipes();
        } else {
            alert('Fehler beim Umbenennen der Kategorie.');
        }
    } catch (error) {
        console.error('Error renaming category:', error);
        alert('Fehler beim Umbenennen der Kategorie.');
    }
}

async function createNewCategory() {
    const nameInput = document.getElementById('newCategoryName');
    const categoryName = nameInput.value.trim();

    if (!categoryName) {
        alert('Bitte geben Sie einen Kategorie-Namen ein.');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/categories`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: categoryName }),
            credentials: 'include'
        });

        if (response.ok) {
            const result = await response.json();
            alert(`Kategorie "${categoryName}" erfolgreich erstellt!`);
            nameInput.value = ''; // Clear input
            await loadCategoryManagement();
            await loadCategories();
        } else {
            alert('Fehler beim Erstellen der Kategorie.');
        }
    } catch (error) {
        console.error('Error creating category:', error);
        alert('Fehler beim Erstellen der Kategorie.');
    }
}

async function deleteCategory(categoryName, recipeCount) {
    let action = 'clear';
    let message = `Was möchten Sie mit der Kategorie "${categoryName}" (${recipeCount} Rezepte) tun?`;

    if (recipeCount > 0) {
        const choice = confirm(`${message}\n\nOK = Kategorie nur entfernen (Rezepte behalten)\nAbbrechen = Aktion abbrechen\n\nWARNING: Es gibt aktuell keine Option zum Löschen der Rezepte über die UI.`);
        if (!choice) return;
        action = 'clear';
    } else {
        if (!confirm(`Leere Kategorie "${categoryName}" löschen?`)) return;
    }

    try {
        const response = await fetch(`${API_BASE}/categories/${encodeURIComponent(categoryName)}?action=${action}`, {
            method: 'DELETE',
            credentials: 'include'
        });

        if (response.ok) {
            const result = await response.json();
            alert(result.message);
            await loadCategoryManagement();
            await loadCategories();
            await loadRecipes();
        } else {
            alert('Fehler beim Löschen der Kategorie.');
        }
    } catch (error) {
        console.error('Error deleting category:', error);
        alert('Fehler beim Löschen der Kategorie.');
    }
}

// Single Recipe View Functions
function openSingleRecipe(recipeId) {
    const recipe = allRecipes.find(r => r.id === recipeId);
    if (!recipe) return;

    // Populate title
    document.getElementById('singleRecipeTitle').textContent = recipe.title || 'Ohne Titel';

    // Populate meta information
    const metaDiv = document.getElementById('singleRecipeMeta');
    metaDiv.innerHTML = '';

    if (recipe.category) {
        const categoryMeta = document.createElement('div');
        categoryMeta.className = 'meta-item';
        categoryMeta.innerHTML = `📂 ${recipe.category}`;
        metaDiv.appendChild(categoryMeta);
    }

    if (recipe.portions) {
        const portionsMeta = document.createElement('div');
        portionsMeta.className = 'meta-item';
        portionsMeta.innerHTML = `👥 ${recipe.portions}`;
        metaDiv.appendChild(portionsMeta);
    }

    if (recipe.created_date) {
        const dateMeta = document.createElement('div');
        dateMeta.className = 'meta-item';
        dateMeta.innerHTML = `📅 ${recipe.created_date}`;
        metaDiv.appendChild(dateMeta);
    }

    // Populate actions
    const actionsDiv = document.getElementById('singleRecipeActions');
    actionsDiv.innerHTML = `
        <button class="btn btn-small btn-secondary" onclick="toggleSingleRecipePortionCalculator(${recipe.id})">
            📊 Portionen
        </button>
        <button class="btn btn-small btn-secondary" onclick="printRecipe(${recipe.id})">
            🖨️ Drucken
        </button>
        ${currentUser && currentUser.is_admin ? `
        <button class="btn btn-small btn-primary" onclick="editRecipe(${recipe.id}); closeSingleRecipe();">
            ✏️ Bearbeiten
        </button>
        <button class="btn btn-small btn-danger" onclick="deleteRecipe(${recipe.id})">
            🗑️ Löschen
        </button>
        ` : ''}
    `;

    // Populate content
    const contentDiv = document.getElementById('singleRecipeContent');
    contentDiv.innerHTML = '';

    // Add image if exists
    if (recipe.image_filename) {
        const img = document.createElement('img');
        img.src = `/uploads/${recipe.image_filename}`;
        img.alt = recipe.title;
        img.className = 'single-recipe-image';
        contentDiv.appendChild(img);
    }

    // Add ingredients
    if (recipe.ingredients) {
        const ingredientsSection = document.createElement('div');
        ingredientsSection.className = 'single-recipe-section';
        ingredientsSection.innerHTML = `
            <h4>🥄 Zutaten</h4>
            <p id="single-ingredients-${recipe.id}">${getScaledIngredients(recipe.id, recipe.ingredients)}</p>
        `;
        contentDiv.appendChild(ingredientsSection);
    }

    // Add instructions
    if (recipe.instructions) {
        const instructionsSection = document.createElement('div');
        instructionsSection.className = 'single-recipe-section';
        instructionsSection.innerHTML = `
            <h4>👨‍🍳 Zubereitung</h4>
            <p>${recipe.instructions}</p>
        `;
        contentDiv.appendChild(instructionsSection);
    }

    // Add notes
    if (recipe.notes) {
        const notesSection = document.createElement('div');
        notesSection.className = 'single-recipe-section';
        notesSection.innerHTML = `
            <h4>💡 Hinweise & Tipps</h4>
            <p>${recipe.notes}</p>
        `;
        contentDiv.appendChild(notesSection);
    }

    // Add portion calculator
    const calculatorDiv = document.createElement('div');
    calculatorDiv.className = 'single-recipe-portion-calculator';
    calculatorDiv.id = `single-calculator-${recipe.id}`;
    calculatorDiv.style.display = 'none';
    calculatorDiv.innerHTML = `
        <h5>📊 Portionen anpassen</h5>
        <div class="portion-controls">
            <button class="portion-btn" onclick="adjustSingleRecipePortion(${recipe.id}, -1)">−</button>
            <div class="portion-display">
                <span id="single-current-portions-${recipe.id}">${getCurrentPortions(recipe.id, recipe.portions)}</span> Portionen
            </div>
            <button class="portion-btn" onclick="adjustSingleRecipePortion(${recipe.id}, 1)">+</button>
        </div>
        <div style="font-size: 0.9em; color: #0369a1; margin-top: 12px; font-weight: 500;">
            Original: ${recipe.portions} Portionen
            <button class="btn btn-small btn-secondary" onclick="resetPortion(${recipe.id})" style="margin-left: 8px; padding: 2px 6px; font-size: 0.8em;">↺ Reset</button>
        </div>
    `;
    contentDiv.appendChild(calculatorDiv);

    // Show overlay
    document.getElementById('singleRecipeOverlay').style.display = 'flex';
    document.body.style.overflow = 'hidden'; // Prevent background scrolling
}

function closeSingleRecipe(event) {
    // Only close if clicking on overlay background, not the container
    if (event && event.target !== document.getElementById('singleRecipeOverlay')) {
        return;
    }

    document.getElementById('singleRecipeOverlay').style.display = 'none';
    document.body.style.overflow = 'auto'; // Re-enable background scrolling
}

function toggleSingleRecipePortionCalculator(recipeId) {
    const calculator = document.getElementById(`single-calculator-${recipeId}`);
    calculator.style.display = calculator.style.display === 'none' ? 'block' : 'none';
}

function adjustSingleRecipePortion(recipeId, change) {
    const recipe = allRecipes.find(r => r.id === recipeId);
    const currentElement = document.getElementById(`single-current-portions-${recipeId}`);
    const ingredientsElement = document.getElementById(`single-ingredients-${recipeId}`);

    let currentPortions = parseFloat(currentElement.textContent);
    let newPortions = Math.max(0.5, currentPortions + (change * 0.5));

    currentElement.textContent = newPortions;

    const originalPortions = parseFloat(recipe.portions) || 1;
    const scaleFactor = newPortions / originalPortions;

    // Save the multiplier to persistent storage
    setPortionMultiplier(recipeId, scaleFactor);

    const scaledIngredients = scaleIngredients(recipe.ingredients, scaleFactor);
    ingredientsElement.innerHTML = scaledIngredients;

    // Update card view if it exists
    const cardIngredientsElement = document.getElementById(`ingredients-${recipeId}`);
    const cardCurrentElement = document.getElementById(`current-portions-${recipeId}`);
    if (cardIngredientsElement && cardCurrentElement) {
        cardCurrentElement.textContent = newPortions;
        cardIngredientsElement.innerHTML = scaledIngredients;
    }
}

// Add keyboard event listener for ESC key to close single recipe view
document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') {
        closeSingleRecipe();
    }
});
