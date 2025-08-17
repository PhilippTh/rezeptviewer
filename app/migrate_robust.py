#!/usr/bin/env python3
"""
Robust DBF migration with manual parsing and encoding detection
"""

import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from database import Recipe
from datetime import datetime
import struct
import chardet

def detect_and_clean_text(raw_bytes):
    """Detect encoding and clean text from raw bytes"""
    if not raw_bytes:
        return ''
    
    # Remove null bytes and strip
    raw_bytes = raw_bytes.rstrip(b'\x00')
    if not raw_bytes:
        return ''
    
    # German/French DBF files can use various encodings
    # Try encodings in order of likelihood for German/French text
    encodings = ['cp850', 'iso-8859-1', 'cp1252', 'iso-8859-15', 'utf-8']
    
    for encoding in encodings:
        try:
            decoded = raw_bytes.decode(encoding).strip()
            
            # Check if this looks like proper German text
            # Look for common German words and proper umlaut patterns
            if decoded:
                # Check for suspicious character patterns that indicate wrong encoding
                suspicious_patterns = ['„', '‚', '‰', '€', '†', '‡']
                has_suspicious = any(char in decoded for char in suspicious_patterns)
                
                # Check for proper German characters
                german_chars = ['ä', 'ö', 'ü', 'ß', 'Ä', 'Ö', 'Ü']
                has_german = any(char in decoded for char in german_chars)
                
                # Check for proper French characters
                french_chars = ['é', 'è', 'ê', 'ë', 'à', 'â', 'ç', 'î', 'ï', 'ô', 'ù', 'û', 'ü', 'ÿ', 'É', 'È', 'Ê', 'Ë', 'À', 'Â', 'Ç', 'Î', 'Ï', 'Ô', 'Ù', 'Û', 'Ü', 'Ÿ']
                has_french = any(char in decoded for char in french_chars)
                
                # If we have German or French characters and no suspicious patterns, this is likely correct
                if (has_german or has_french) and not has_suspicious:
                    return decoded
                    
                # If no suspicious patterns and no special chars, it might still be correct
                if not has_suspicious and not has_german and not has_french:
                    # Store this as a fallback
                    fallback_decoded = decoded
                    continue
                    
                # If we have suspicious patterns, try next encoding
                if has_suspicious:
                    continue
                    
                return decoded
        except:
            continue
    
    # If we found a fallback without German chars but also without suspicious patterns
    try:
        return fallback_decoded
    except:
        pass
    
    # Last resort: decode with errors replaced
    try:
        return raw_bytes.decode('cp850', errors='replace').strip()
    except:
        return ''

def parse_dbf_manually(dbf_file):
    """Manually parse DBF file to handle encoding issues"""
    
    records = []
    
    with open(dbf_file, 'rb') as f:
        # Read DBF header (32 bytes)
        header = f.read(32)
        
        if len(header) < 32:
            raise Exception("Invalid DBF file: header too short")
        
        # Parse header
        version = header[0]
        year = header[1] + 1900 if header[1] > 50 else header[1] + 2000
        month = header[2]
        day = header[3]
        record_count = struct.unpack('<L', header[4:8])[0]
        header_length = struct.unpack('<H', header[8:10])[0]
        record_length = struct.unpack('<H', header[10:12])[0]
        
        print(f"📊 DBF Info: {record_count} records, {record_length} bytes each")
        
        # Read field descriptors
        field_count = (header_length - 33) // 32
        fields = []
        
        for i in range(field_count):
            field_desc = f.read(32)
            if len(field_desc) < 32:
                break
            
            field_name = field_desc[:11].rstrip(b'\x00').decode('ascii')
            field_type = chr(field_desc[11])
            field_length = field_desc[16]
            field_decimal = field_desc[17]
            
            fields.append({
                'name': field_name,
                'type': field_type,
                'length': field_length,
                'decimal': field_decimal
            })
        
        print(f"📋 Fields: {[f['name'] for f in fields]}")
        
        # Skip to records (after header terminator 0x0D)
        f.seek(header_length)
        
        # Read all records
        for record_num in range(record_count):
            try:
                record_data = f.read(record_length)
                if len(record_data) < record_length:
                    break
                
                # Skip deletion marker (first byte)
                data = record_data[1:]
                
                # Parse fields
                record = {}
                offset = 0
                
                for field in fields:
                    field_data = data[offset:offset + field['length']]
                    
                    if field['name'] in ['REZEPTTITE', 'KATEGORIE', 'PORTIONEN', 'ZUTATEN', 'ANWEISUNGE', 'HINWEISE']:
                        # String fields - handle encoding carefully
                        record[field['name']] = detect_and_clean_text(field_data)
                    elif field['name'] == 'ERSTELLT_A':
                        # Date field
                        date_str = detect_and_clean_text(field_data)
                        record[field['name']] = date_str
                    else:
                        # Other fields
                        record[field['name']] = detect_and_clean_text(field_data)
                    
                    offset += field['length']
                
                records.append(record)
                
                # Show progress
                if (record_num + 1) % 20 == 0:
                    print(f"⏳ Parsed {record_num + 1}/{record_count} records...")
                    
            except Exception as e:
                print(f"⚠️  Error parsing record {record_num + 1}: {str(e)[:50]}...")
                continue
    
    return records

def migrate_dbf_to_postgres(dbf_file: str, database_url: str):
    """Migrate recipes from DBF file to PostgreSQL using manual parsing"""
    
    if not os.path.exists(dbf_file):
        print(f"❌ Error: DBF file '{dbf_file}' not found!")
        sys.exit(1)
    
    print(f"📁 DBF file found: {dbf_file}")
    print(f"🗄️  Database URL: {database_url}")
    
    # Create database connection
    engine = create_engine(database_url)
    
    # Create tables
    Recipe.metadata.create_all(bind=engine)
    print("✅ Database tables created/verified")
    
    # Create session
    session = Session(engine)
    
    try:
        print(f"📖 Manually parsing DBF file...")
        records = parse_dbf_manually(dbf_file)
        
        print(f"✅ Successfully parsed {len(records)} records")
        
        # Check if recipes already exist
        existing_count = session.query(Recipe).count()
        if existing_count > 0:
            print(f"ℹ️  Database already contains {existing_count} recipes.")
            print("🔄 Continuing with import (duplicates will be added)")
        
        imported_count = 0
        skipped_count = 0
        
        for i, record in enumerate(records):
            try:
                # Parse date
                created_date = None
                if record.get('ERSTELLT_A'):
                    try:
                        date_str = str(record['ERSTELLT_A']).replace('-', '').replace('/', '')
                        if len(date_str) == 8 and date_str.isdigit():  # YYYYMMDD format
                            created_date = datetime.strptime(date_str, '%Y%m%d').date()
                    except:
                        pass
                
                # Create recipe object
                recipe = Recipe(
                    title=record.get('REZEPTTITE', '').strip(),
                    category=record.get('KATEGORIE', '').strip(),
                    portions=record.get('PORTIONEN', '').strip(),
                    ingredients=record.get('ZUTATEN', '').strip(),
                    instructions=record.get('ANWEISUNGE', '').strip(),
                    notes=record.get('HINWEISE', '').strip(),
                    created_date=created_date
                )
                
                session.add(recipe)
                imported_count += 1
                
                # Show progress
                if imported_count % 20 == 0:
                    print(f"⏳ Imported {imported_count}/{len(records)} recipes...")
                    
            except Exception as e:
                skipped_count += 1
                print(f"⚠️  Skipped record {i + 1} due to error: {str(e)[:50]}...")
                continue
        
        session.commit()
        final_count = session.query(Recipe).count()
        
        print(f"✅ Migration completed successfully!")
        print(f"📈 Imported: {imported_count} recipes")
        if skipped_count > 0:
            print(f"⚠️  Skipped: {skipped_count} recipes due to errors")
        print(f"📊 Total in database: {final_count} recipes")
        
        # Show a sample recipe
        if imported_count > 0:
            sample = session.query(Recipe).first()
            print(f"\n📝 Sample recipe:")
            print(f"   Title: {sample.title}")
            print(f"   Category: {sample.category}")
            print(f"   Ingredients: {sample.ingredients[:50]}..." if len(sample.ingredients) > 50 else f"   Ingredients: {sample.ingredients}")
        
    except Exception as e:
        session.rollback()
        print(f"❌ Error during migration: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        session.close()

def main():
    print("🍽️  Recipe Viewer - Robust DBF Migration")
    print("=" * 60)
    
    # Get environment variables
    dbf_file = os.getenv("DBF_FILE", "Rezepte.dbf")
    database_url = os.getenv("DATABASE_URL", "postgresql://rezepte_user:rezepte_password@postgres:5432/rezepte_db")
    
    migrate_dbf_to_postgres(dbf_file, database_url)
    
    print()
    print("🎉 Ready to start the web application!")
    print("   docker compose up -d web")

if __name__ == "__main__":
    main()