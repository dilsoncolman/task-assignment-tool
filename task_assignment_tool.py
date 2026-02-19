import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
from collections import Counter, defaultdict
import statistics
import requests
from typing import Dict, List, Any
import os
import time
import io
import re

# Page config
st.set_page_config(
    page_title="Team Task Assignment Tool",
    page_icon="📋",
    layout="wide"
)

# GitHub Configuration
GITHUB_TOKEN = st.secrets.get("github", {}).get("token", "")
GITHUB_REPO = st.secrets.get("github", {}).get("repo", "")  # format: "username/repo"
GITHUB_BRANCH = st.secrets.get("github", {}).get("branch", "main")
DATA_FILE = "task_assignment_data.json"

# GitHub API Functions
def get_github_headers():
    """Get headers for GitHub API requests"""
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

def get_data_from_github():
    """Load data from GitHub"""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return None, None
    
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{DATA_FILE}?ref={GITHUB_BRANCH}"
        response = requests.get(url, headers=get_github_headers())
        
        if response.status_code == 200:
            content = response.json()
            import base64
            data = json.loads(base64.b64decode(content['content']).decode('utf-8'))
            return data, content['sha']
        elif response.status_code == 404:
            # File doesn't exist yet, return empty structure
            return {
                "tasks": {},
                "assignments": {},
                "completed_tasks": [],
                "task_counter": 1,
                "assignment_history": [],
                "last_modified": {
                    "user": "System",
                    "timestamp": datetime.now().isoformat()
                }
            }, None
        else:
            st.error(f"GitHub API error: {response.status_code}")
            return None, None
    except Exception as e:
        st.error(f"Error loading data from GitHub: {e}")
        return None, None

def save_data_to_github(data, sha=None, file_name=DATA_FILE, retry_count=0):
    """Save data to GitHub with automatic retry on conflicts"""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        st.error("GitHub configuration missing in secrets")
        return False
    
    if retry_count > 3:
        st.error("Failed to save after multiple attempts. Please refresh and try again.")
        return False
    
    try:
        # Add last modified info
        data["last_modified"] = {
            "user": st.session_state.current_user,
            "timestamp": datetime.now().isoformat()
        }
        
        import base64
        content = base64.b64encode(json.dumps(data, indent=2).encode('utf-8')).decode('utf-8')
        
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_name}"
        
        payload = {
            "message": f"Update by {st.session_state.current_user} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "content": content,
            "branch": GITHUB_BRANCH
        }
        
        if sha:
            payload["sha"] = sha
        
        response = requests.put(url, json=payload, headers=get_github_headers())
        
        if response.status_code in [200, 201]:
            return True
        elif response.status_code == 409:
            # Conflict - someone else updated the file
            if retry_count == 0:
                st.warning("⚠️ Another user updated the data. Attempting to merge changes...")
            
            # Get the latest data
            latest_data, latest_sha = get_data_from_github()
            if latest_data:
                # Merge the changes (simple strategy - combine tasks and assignments)
                if "tasks" in data and "tasks" in latest_data:
                    latest_data["tasks"].update(data["tasks"])
                if "assignments" in data and "assignments" in latest_data:
                    latest_data["assignments"].update(data["assignments"])
                if "completed_tasks" in data:
                    # Merge completed tasks, avoiding duplicates
                    existing_ids = {ct['task_id'] for ct in latest_data.get("completed_tasks", [])}
                    for ct in data.get("completed_tasks", []):
                        if ct['task_id'] not in existing_ids:
                            latest_data["completed_tasks"].append(ct)
                if "assignment_history" in data:
                    # Merge assignment history
                    latest_data["assignment_history"].extend(data.get("assignment_history", []))
                if "task_counter" in data:
                    latest_data["task_counter"] = max(data.get("task_counter", 1), latest_data.get("task_counter", 1))
                
                # Retry with merged data
                time.sleep(0.5)  # Small delay to avoid rapid retries
                return save_data_to_github(latest_data, latest_sha, file_name, retry_count + 1)
            else:
                st.error("Failed to resolve conflict. Please refresh the page.")
                return False
        else:
            st.error(f"GitHub save error: {response.status_code}")
            return False
    except Exception as e:
        st.error(f"Error saving to GitHub: {e}")
        return False

# Data Management Functions
@st.cache_data(ttl=5)  # Reduced cache time to minimize conflicts
def load_all_data():
    """Load all data from GitHub"""
    data, sha = get_data_from_github()
    if data:
        # Ensure all fields exist
        if "assignment_history" not in data:
            data["assignment_history"] = []
        if "last_modified" not in data:
            data["last_modified"] = {
                "user": "Unknown",
                "timestamp": datetime.now().isoformat()
            }
        return data, sha
    return {
        "tasks": {},
        "assignments": {},
        "completed_tasks": [],
        "task_counter": 1,
        "assignment_history": [],
        "last_modified": {
            "user": "System",
            "timestamp": datetime.now().isoformat()
        }
    }, None

def save_all_data(data):
    """Save all data to GitHub with conflict resolution"""
    # Always get fresh SHA before saving
    _, current_sha = get_data_from_github()
    success = save_data_to_github(data, current_sha)
    if success:
        st.cache_data.clear()  # Clear cache to force reload
        return True
    else:
        # Show more helpful error message
        st.error("""
        ⚠️ **Save Conflict Detected**
        
        Another team lead has made changes. Please:
        1. Click the 🔄 Refresh button
        2. Review any changes
        3. Try your action again
        """)
        return False

def reset_all_data():
    """Reset all data to start fresh"""
    data = {
        "tasks": {},
        "assignments": {},
        "completed_tasks": [],
        "task_counter": 1,
        "assignment_history": [],
        "last_modified": {
            "user": st.session_state.current_user,
            "timestamp": datetime.now().isoformat()
        }
    }
    return save_all_data(data)

def load_tasks():
    """Load tasks from storage"""
    data, _ = load_all_data()
    return data.get("tasks", {})

def save_task(task_id, task_info):
    """Save a task with conflict handling"""
    max_retries = 3
    for attempt in range(max_retries):
        data, _ = load_all_data()
        
        # Preserve existing tasks and add/update the new one
        if "tasks" not in data:
            data["tasks"] = {}
        
        data["tasks"][task_id] = task_info
        
        if save_all_data(data):
            return True
        
        if attempt < max_retries - 1:
            st.warning(f"Retrying save... (Attempt {attempt + 2}/{max_retries})")
            time.sleep(1)
    
    return False

def delete_task(task_id):
    """Delete a task"""
    data, _ = load_all_data()
    if task_id in data.get("tasks", {}):
        del data["tasks"][task_id]
    if task_id in data.get("assignments", {}):
        del data["assignments"][task_id]
    save_all_data(data)

def load_assignments():
    """Load assignments"""
    data, _ = load_all_data()
    return data.get("assignments", {})

def save_assignments(task_id, testers):
    """Save assignments and track history with conflict handling"""
    max_retries = 3
    for attempt in range(max_retries):
        data, _ = load_all_data()
        
        # Ensure assignments dict exists
        if "assignments" not in data:
            data["assignments"] = {}
        
        # Track assignment history
        task_info = data.get("tasks", {}).get(task_id, {})
        if "assignment_history" not in data:
            data["assignment_history"] = []
            
        for tester in testers:
            data["assignment_history"].append({
                "task_id": task_id,
                "task_name": task_info.get("name", "Unknown"),
                "tester": tester,
                "assigned_at": datetime.now().isoformat(),
                "assigned_by": st.session_state.current_user,
                "languages": task_info.get("languages", []),
                "priority": task_info.get("priority", "Unknown")
            })
        
        data["assignments"][task_id] = testers
        
        if save_all_data(data):
            return True
        
        if attempt < max_retries - 1:
            st.warning(f"Retrying save... (Attempt {attempt + 2}/{max_retries})")
            time.sleep(1)
    
    return False

def load_completed_tasks():
    """Load completed tasks"""
    data, _ = load_all_data()
    return data.get("completed_tasks", [])

def mark_task_completed(task_id, completed_by):
    """Mark a task as completed"""
    data, _ = load_all_data()
    
    # Get task info before marking complete
    task_info = data.get("tasks", {}).get(task_id, {})
    assignees = data.get("assignments", {}).get(task_id, [])
    
    if "completed_tasks" not in data:
        data["completed_tasks"] = []
    
    data["completed_tasks"].append({
        'task_id': task_id,
        'task_name': task_info.get('name', 'Unknown'),
        'completed_by': completed_by,
        'completed_at': datetime.now().isoformat(),
        'assignees': assignees,
        'languages': task_info.get('languages', []),
        'priority': task_info.get('priority', 'Unknown'),
        'created_by': task_info.get('created_by', 'Unknown'),
        'created_at': task_info.get('created_at', '')
    })
    save_all_data(data)

def get_task_counter():
    """Get the next task counter"""
    data, _ = load_all_data()
    counter = data.get("task_counter", 1)
    data["task_counter"] = counter + 1
    save_all_data(data)
    return counter

def load_assignment_history():
    """Load assignment history"""
    data, _ = load_all_data()
    return data.get("assignment_history", [])

def get_last_modified_info():
    """Get information about last modification"""
    data, _ = load_all_data()
    last_modified = data.get("last_modified", {})
    return last_modified.get("user", "Unknown"), last_modified.get("timestamp", "Unknown")

# Initialize session state
if 'roster_data' not in st.session_state:
    st.session_state.roster_data = None
if 'current_user' not in st.session_state:
    query_params = st.query_params
    st.session_state.current_user = query_params.get('user', None)
if 'show_conflict_message' not in st.session_state:
    st.session_state.show_conflict_message = False
if 'last_conflict_message' not in st.session_state:
    st.session_state.last_conflict_message = None
if 'show_reset_confirmation' not in st.session_state:
    st.session_state.show_reset_confirmation = False
if 'last_uploaded_file_id' not in st.session_state:
    st.session_state.last_uploaded_file_id = None
if 'previous_roster_size' not in st.session_state:
    st.session_state.previous_roster_size = 0

# Helper Functions
def make_columns_unique(columns):
    """Make duplicate column names unique by adding suffixes"""
    seen = {}
    unique_columns = []
    
    for col in columns:
        col_str = str(col).strip()
        
        if col_str in seen:
            # This is a duplicate
            seen[col_str] += 1
            unique_columns.append(f"{col_str}_{seen[col_str]}")
        else:
            # First occurrence
            seen[col_str] = 1
            unique_columns.append(col_str)
    
    return unique_columns

def parse_csv_ultra_smart(file_content):
    """Ultra-smart CSV parser that handles various edge cases including duplicate columns"""
    try:
        # Always reset file pointer to beginning
        file_content.seek(0)
        
        # Read the raw content
        raw_content = file_content.read()
        
        # Reset pointer again
        file_content.seek(0)
        
        # Try to decode with different encodings
        text_content = None
        for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
            try:
                if isinstance(raw_content, bytes):
                    text_content = raw_content.decode(encoding)
                else:
                    text_content = raw_content
                break
            except:
                continue
        
        if not text_content:
            raise ValueError("Could not decode file with any encoding")
        
        # Split into lines
        lines = text_content.strip().split('\n')
        
        if not lines:
            raise ValueError("Empty file")
        
        # Function to detect if a row looks like headers
        def looks_like_headers(values):
            """Check if values look like column headers"""
            if not values:
                return False
            
            # Check for common header patterns
            header_patterns = [
                'first', 'last', 'name', 'language', 'lang', 'device', 
                'serial', 'type', 'index', 'experience', 'currently', 'used'
            ]
            
            # Check if values contain header-like words
            values_lower = [str(v).lower() for v in values if v]
            matches = sum(1 for v in values_lower for pattern in header_patterns if pattern in v)
            
            # If many matches, likely headers
            return matches >= 2
        
        # Function to parse a line considering quotes
        def parse_csv_line(line, delimiter=','):
            """Parse a CSV line handling quotes properly"""
            values = []
            current_value = ""
            in_quotes = False
            
            for i, char in enumerate(line):
                if char == '"' and (i == 0 or line[i-1] != '\\'):
                    in_quotes = not in_quotes
                elif char == delimiter and not in_quotes:
                    values.append(current_value.strip().strip('"'))
                    current_value = ""
                else:
                    current_value += char
            
            if current_value:
                values.append(current_value.strip().strip('"'))
            
            return values
        
        # Try different delimiters
        best_delimiter = ','
        max_columns = 0
        
        for delimiter in [',', '\t', ';', '|']:
            first_line_values = parse_csv_line(lines[0], delimiter)
            if len(first_line_values) > max_columns:
                max_columns = len(first_line_values)
                best_delimiter = delimiter
        
        # Parse all lines with best delimiter
        all_data = []
        for line in lines:
            if line.strip():
                values = parse_csv_line(line, best_delimiter)
                all_data.append(values)
        
        if not all_data:
            raise ValueError("No data found")
        
        # Find the header row
        header_row_idx = 0
        
        # Check first few rows for headers
        for i in range(min(3, len(all_data))):
            if looks_like_headers(all_data[i]):
                header_row_idx = i
                break
        
        # Special case: if first row is just letters (A, B, C...) skip it
        first_row = all_data[0]
        if all(len(str(v).strip()) <= 2 and str(v).strip().isalpha() for v in first_row if v):
            header_row_idx = 1
        
        # Extract headers and data
        headers = all_data[header_row_idx] if header_row_idx < len(all_data) else all_data[0]
        data_rows = all_data[header_row_idx + 1:] if header_row_idx + 1 < len(all_data) else []
        
        # Clean headers and make them unique
        headers = [str(h).strip() for h in headers]
        headers = make_columns_unique(headers)  # Make duplicate columns unique
        
        # Ensure all rows have same number of columns
        max_cols = len(headers)
        cleaned_data = []
        
        for row in data_rows:
            # Pad short rows
            while len(row) < max_cols:
                row.append('')
            # Trim long rows
            row = row[:max_cols]
            cleaned_data.append(row)
        
        # Create DataFrame
        df = pd.DataFrame(cleaned_data, columns=headers)
        
        # Remove completely empty rows
        df = df.dropna(how='all')
        
        # Remove rows where all values are empty strings
        df = df[~(df == '').all(axis=1)]
        
        return df
        
    except Exception as e:
        # If all else fails, try pandas with different options
        try:
            file_content.seek(0)
            # Try reading with pandas, handling duplicate columns
            df = pd.read_csv(file_content)
            
            # Make columns unique if there are duplicates
            if df.columns.duplicated().any():
                df.columns = make_columns_unique(df.columns.tolist())
            
            return df
        except Exception as pandas_error:
            raise Exception(f"Failed to parse CSV: {str(e)}. Pandas error: {str(pandas_error)}")

def normalize_column_names(df):
    """Normalize column names with extensive mapping"""
    if df.empty:
        return df
    
    # Remove any unnamed columns at the start
    while len(df.columns) > 0 and (
        'unnamed' in str(df.columns[0]).lower() or 
        df.columns[0] == '' or 
        pd.isna(df.columns[0]) or
        (isinstance(df.columns[0], str) and df.columns[0].isdigit())
    ):
        df = df.iloc[:, 1:]
    
    # Create comprehensive mapping - now handles numbered versions
    column_mappings = {
        'first_name': [
            'first_name', 'firstname', 'first name', 'fname', 'given_name', 
            'given name', 'first', 'name', 'forename', 'prenom', 'given'
        ],
        'last_name': [
            'last_name', 'lastname', 'last name', 'lname', 'surname', 
            'family_name', 'family name', 'last', 'family', 'nom'
        ],
        'language_1': [
            'language_1', 'language1', 'language 1', 'lang1', 'lang_1', 
            'lang 1', 'primary_language', 'primary language', 'language', 
            'first_language', 'first language'
        ],
        'language_2': [
            'language_2', 'language2', 'language 2', 'lang2', 'lang_2', 
            'lang 2', 'secondary_language', 'secondary language', 
            'second_language', 'second language'
        ],
        'language_3': [
            'language_3', 'language3', 'language 3', 'lang3', 'lang_3', 
            'lang 3', 'third_language', 'third language'
        ],
        'language_4': [
            'language_4', 'language4', 'language 4', 'lang4', 'lang_4', 
            'lang 4', 'fourth_language', 'fourth language'
        ],
        'public_device_name': [
            'public_device_name', 'device_name', 'device name', 'device', 
            'public device name', 'device_id', 'device id'
        ],
        'public_device_name_2': [
            'public_device_name_2', 'public_device_name_2', 'device_name_2', 
            'device name 2', 'device 2', 'public device name 2'
        ],
        'public_device_name_3': [
            'public_device_name_3', 'public_device_name_3', 'device_name_3', 
            'device name 3', 'device 3', 'public device name 3'
        ],
        'public_device_name_4': [
            'public_device_name_4', 'public_device_name_4', 'device_name_4', 
            'device name 4', 'device 4', 'public device name 4'
        ],
        'device_type': [
            'device_type', 'type', 'device type', 'device_model', 'model'
        ],
        'device_type_2': [
            'device_type_2', 'type_2', 'device type 2', 'device_model_2', 'model 2'
        ],
        'device_type_3': [
            'device_type_3', 'type_3', 'device type 3', 'device_model_3', 'model 3'
        ],
        'device_type_4': [
            'device_type_4', 'type_4', 'device type 4', 'device_model_4', 'model 4'
        ],
        'serial_number': [
            'serial_number', 'serial', 'sn', 'serial number', 'serial no', 
            'serial_no', 'serialnumber', 'serial#'
        ],
        'serial_number_2': [
            'serial_number_2', 'serial_2', 'sn_2', 'serial number 2', 'serial no 2'
        ],
        'serial_number_3': [
            'serial_number_3', 'serial_3', 'sn_3', 'serial number 3', 'serial no 3'
        ],
        'serial_number_4': [
            'serial_number_4', 'serial_4', 'sn_4', 'serial number 4', 'serial no 4'
        ],
        'currently_used_by': [
            'currently_used_by', 'used_by', 'current_user', 'used by', 
            'currently used by', 'current user', 'assigned_to', 'assigned to'
        ],
        'currently_used_by_2': [
            'currently_used_by_2', 'currently used by_2', 'used_by_2', 'used by 2'
        ],
        'currently_used_by_3': [
            'currently_used_by_3', 'currently used by_3', 'used_by_3', 'used by 3'
        ],
        'currently_used_by_4': [
            'currently_used_by_4', 'currently used by_4', 'used_by_4', 'used by 4'
        ]
    }
    
    # Apply mapping
    new_columns = {}
    used_mappings = set()
    
    for col in df.columns:
        if pd.isna(col) or str(col).strip() == '':
            continue
        
        col_lower = str(col).strip().lower()
        mapped = False
        
        # Try exact match first
        for standard_name, variations in column_mappings.items():
            if col_lower in variations:
                new_columns[col] = standard_name
                used_mappings.add(standard_name)
                mapped = True
                break
        
        # If no exact match, try partial match
        if not mapped:
            for standard_name, variations in column_mappings.items():
                if standard_name not in used_mappings:
                    for variation in variations:
                        if variation in col_lower or col_lower in variation:
                            new_columns[col] = standard_name
                            used_mappings.add(standard_name)
                            mapped = True
                            break
                    if mapped:
                        break
        
        # If still no match, clean the column name
        if not mapped:
            clean_name = re.sub(r'[^a-zA-Z0-9_]', '_', col_lower)
            clean_name = re.sub(r'_+', '_', clean_name).strip('_')
            new_columns[col] = clean_name if clean_name else f'column_{len(new_columns)}'
    
    df = df.rename(columns=new_columns)
    
    # Remove completely empty columns
    df = df.dropna(axis=1, how='all')
    
    return df

def validate_required_columns(df):
    """Check required columns"""
    required = ['first_name', 'last_name']
    missing = []
    
    for col in required:
        if col not in df.columns:
            missing.append(col)
    
    return missing

def normalize_language(lang):
    """Normalize language codes - UPDATED TO EXCLUDE NA"""
    if pd.isna(lang) or lang == '' or str(lang).lower() == 'nan':
        return None
    
    lang = str(lang).strip()
    lang_upper = lang.upper()
    
    # Skip NA (Not Applicable)
    if lang_upper == 'NA' or lang_upper == 'N/A':
        return None
    
    language_map = {
        'EN': 'English', 'EN_US': 'English', 'EN_GB': 'English', 'EN_IE': 'English',
        'EN_AU': 'English', 'EN_CA': 'English', 'ENGLISH': 'English',
        'IT': 'Italian', 'IT_IT': 'Italian', 'ITALIAN': 'Italian',
        'FR': 'French', 'FR_FR': 'French', 'FR_CA': 'French', 'FRENCH': 'French',
        'NB': 'Norwegian', 'NB_NO': 'Norwegian', 'NO': 'Norwegian', 'NORWEGIAN': 'Norwegian',
        'RU': 'Russian', 'RU_RU': 'Russian', 'RUSSIAN': 'Russian',
        'ZH': 'Chinese', 'ZH_CN': 'Chinese (Simplified)', 'ZH_XC': 'Chinese (Simplified)',
        'ZH_TW': 'Chinese (Traditional)', 'CHINESE': 'Chinese',
        'HE': 'Hebrew', 'HE_IL': 'Hebrew', 'IL_HE': 'Hebrew', 'HEBREW': 'Hebrew',
        'DE': 'German', 'DE_DE': 'German', 'GERMAN': 'German',
        'ES': 'Spanish', 'ES_ES': 'Spanish', 'ES_MX': 'Spanish', 'SPANISH': 'Spanish',
        'PT': 'Portuguese', 'PT_PT': 'Portuguese', 'PT_BR': 'Portuguese', 'PORTUGUESE': 'Portuguese',
        'JA': 'Japanese', 'JA_JP': 'Japanese', 'JAPANESE': 'Japanese',
        'KO': 'Korean', 'KO_KR': 'Korean', 'KOREAN': 'Korean',
        'NL': 'Dutch', 'NL_NL': 'Dutch', 'DUTCH': 'Dutch',
        'SV': 'Swedish', 'SV_SE': 'Swedish', 'SWEDISH': 'Swedish',
        'DA': 'Danish', 'DA_DK': 'Danish', 'DANISH': 'Danish',
        'FI': 'Finnish', 'FI_FI': 'Finnish', 'FINNISH': 'Finnish',
        'PL': 'Polish', 'PL_PL': 'Polish', 'POLISH': 'Polish',
        'TR': 'Turkish', 'TR_TR': 'Turkish', 'TURKISH': 'Turkish',
        'AR': 'Arabic', 'AR_SA': 'Arabic', 'ARABIC': 'Arabic',
        'TH': 'Thai', 'TH_TH': 'Thai', 'THAI': 'Thai',
        'HI': 'Hindi', 'HI_IN': 'Hindi', 'HINDI': 'Hindi',
    }
    
    if '_' in lang.lower():
        prefix = lang.lower().split('_')[0].upper()
        if prefix in language_map:
            return language_map[prefix]
    
    if lang_upper in language_map:
        return language_map[lang_upper]
    
    return lang.capitalize()

def validate_roster_data(df):
    """Validate roster data"""
    issues = []
    if 'first_name' in df.columns and 'last_name' in df.columns:
        df['first_name'] = df['first_name'].fillna('')
        df['last_name'] = df['last_name'].fillna('')
        df['full_name'] = df['first_name'].astype(str) + ' ' + df['last_name'].astype(str)
        
        valid_names = df[df['full_name'].str.strip() != '']
        if not valid_names.empty:
            duplicates = valid_names[valid_names.duplicated(subset=['full_name'], keep=False)]
            if not duplicates.empty:
                duplicate_names = duplicates['full_name'].unique().tolist()
                issues.append(f"⚠️ Duplicates: {', '.join(duplicate_names)}")
    return issues

def get_tester_languages(row):
    """Get languages for a tester"""
    languages = set()
    for col in ['language_1', 'language_2', 'language_3', 'language_4']:
        if col in row.index:
            lang = normalize_language(row[col])
            if lang:
                languages.add(lang)
    return languages

def get_tester_device_info(row):
    """Get device information for a tester - now handles multiple devices"""
    device_info = {}
    
    # Check for primary device
    if 'public_device_name' in row.index and pd.notna(row['public_device_name']):
        device_info['device_name'] = str(row['public_device_name'])
    if 'device_type' in row.index and pd.notna(row['device_type']):
        device_info['device_type'] = str(row['device_type'])
    if 'serial_number' in row.index and pd.notna(row['serial_number']):
        device_info['serial_number'] = str(row['serial_number'])
    if 'currently_used_by' in row.index and pd.notna(row['currently_used_by']):
        device_info['currently_used_by'] = str(row['currently_used_by'])
    
    # Check for additional devices (2, 3, 4)
    for i in range(2, 5):
        device_key = f'device_{i}'
        if f'public_device_name_{i}' in row.index and pd.notna(row[f'public_device_name_{i}']):
            if device_key not in device_info:
                device_info[device_key] = {}
            device_info[device_key]['device_name'] = str(row[f'public_device_name_{i}'])
        if f'device_type_{i}' in row.index and pd.notna(row[f'device_type_{i}']):
            if device_key not in device_info:
                device_info[device_key] = {}
            device_info[device_key]['device_type'] = str(row[f'device_type_{i}'])
        if f'serial_number_{i}' in row.index and pd.notna(row[f'serial_number_{i}']):
            if device_key not in device_info:
                device_info[device_key] = {}
            device_info[device_key]['serial_number'] = str(row[f'serial_number_{i}'])
        if f'currently_used_by_{i}' in row.index and pd.notna(row[f'currently_used_by_{i}']):
            if device_key not in device_info:
                device_info[device_key] = {}
            device_info[device_key]['currently_used_by'] = str(row[f'currently_used_by_{i}'])
    
    return device_info

def get_available_testers(language_requirements, match_all=False):
    """Get available testers - UPDATED TO SHOW ALL LANGUAGES"""
    if st.session_state.roster_data is None:
        return []
    
    tasks = load_tasks()
    assignments = load_assignments()
    completed_tasks = load_completed_tasks()
    completed_task_ids = [ct['task_id'] for ct in completed_tasks]
    
    available_testers = []
    df = st.session_state.roster_data.fillna('')
    
    for _, row in df.iterrows():
        if not row.get('first_name') or not row.get('last_name'):
            continue
            
        full_name = f"{row['first_name']} {row['last_name']}".strip()
        if not full_name or full_name == ' ':
            continue
            
        tester_languages = get_tester_languages(row)
        device_info = get_tester_device_info(row)
        
        if match_all:
            language_match = all(lang in tester_languages for lang in language_requirements)
        else:
            language_match = any(lang in tester_languages for lang in language_requirements) if language_requirements else True
        
        if language_match or not language_requirements:
            assigned_task_names = {}
            for task_id, task_info in tasks.items():
                if task_id not in completed_task_ids:
                    if full_name in assignments.get(task_id, []):
                        assigned_task_names[task_info['name']] = task_info['priority']
            
            assigned_tasks = [(name, priority) for name, priority in assigned_task_names.items()]
            matching_languages = [lang for lang in language_requirements if lang in tester_languages]
            
            available_testers.append({
                'name': full_name,
                'languages': tester_languages,  # All languages
                'matching_languages': matching_languages,  # Only matching ones
                'assigned_tasks': assigned_tasks,
                'is_available': len(assigned_tasks) == 0,
                'device_info': device_info
            })
    
    available_testers.sort(key=lambda x: (-len(x['matching_languages']), not x['is_available'], x['name']))
    return available_testers

def get_all_testers_with_languages():
    """Get all testers with their language information"""
    if st.session_state.roster_data is None:
        return []
    
    testers = []
    df = st.session_state.roster_data.fillna('')
    
    for _, row in df.iterrows():
        if not row.get('first_name') or not row.get('last_name'):
            continue
            
        full_name = f"{row['first_name']} {row['last_name']}".strip()
        if not full_name or full_name == ' ':
            continue
            
        tester_languages = get_tester_languages(row)
        testers.append({
            'name': full_name,
            'languages': tester_languages
        })
    
    return testers

# NEW FUNCTION: Get testers assigned to multiple tasks
def get_multi_assigned_testers():
    """Get list of testers assigned to multiple active tasks"""
    tasks = load_tasks()
    assignments = load_assignments()
    completed_tasks = load_completed_tasks()
    completed_task_ids = [ct['task_id'] for ct in completed_tasks]
    
    # Count assignments per tester
    tester_assignments = defaultdict(list)
    
    for task_id, assignees in assignments.items():
        if task_id not in completed_task_ids:  # Only count active tasks
            task_info = tasks.get(task_id, {})
            for tester in assignees:
                tester_assignments[tester].append({
                    'task_id': task_id,
                    'task_name': task_info.get('name', 'Unknown'),
                    'priority': task_info.get('priority', 'Unknown'),
                    'languages': task_info.get('languages', [])
                })
    
    # Filter to only those with multiple assignments
    multi_assigned = {}
    for tester, tasks_list in tester_assignments.items():
        if len(tasks_list) > 1:
            multi_assigned[tester] = tasks_list
    
    return multi_assigned

def generate_detailed_report():
    """Generate comprehensive analytics report - UPDATED WITH TAKEAWAYS"""
    tasks = load_tasks()
    assignments = load_assignments()
    completed_tasks = load_completed_tasks()
    assignment_history = load_assignment_history()
    completed_task_ids = [ct['task_id'] for ct in completed_tasks]
    
    total_tasks = len(tasks)
    active_tasks = [(tid, tinfo) for tid, tinfo in tasks.items() if tid not in completed_task_ids]
    now = datetime.now()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    
    total_testers = len(st.session_state.roster_data) if st.session_state.roster_data is not None else 0
    
    # Active assignments
    assigned_testers = set()
    tester_workload = defaultdict(int)
    
    for task_id, assignees in assignments.items():
        if task_id not in completed_task_ids:
            for tester in assignees:
                assigned_testers.add(tester)
                tester_workload[tester] += 1
    
    # Calculate available testers (not assigned to any task)
    available_testers_count = total_testers - len(assigned_testers)
    
    # Historical analysis
    tester_assignment_count = defaultdict(int)
    tester_weekly_count = defaultdict(int)
    tester_monthly_count = defaultdict(int)
    language_demand = defaultdict(int)
    language_weekly_demand = defaultdict(int)
    priority_distribution = defaultdict(int)
    
    # Analyze assignment history
    for record in assignment_history:
        tester_assignment_count[record['tester']] += 1
        
        try:
            assigned_date = datetime.fromisoformat(record['assigned_at'].replace('Z', '+00:00'))
            if assigned_date >= week_ago:
                tester_weekly_count[record['tester']] += 1
            if assigned_date >= month_ago:
                tester_monthly_count[record['tester']] += 1
        except:
            pass
        
        for lang in record.get('languages', []):
            language_demand[lang] += 1
            try:
                assigned_date = datetime.fromisoformat(record['assigned_at'].replace('Z', '+00:00'))
                if assigned_date >= week_ago:
                    language_weekly_demand[lang] += 1
            except:
                pass
    
    # Analyze completed tasks
    completion_times = []
    tester_completion_count = defaultdict(int)
    
    for ct in completed_tasks:
        tester_completion_count[ct['completed_by']] += 1
        
        if 'created_at' in ct and ct['created_at']:
            try:
                created = datetime.fromisoformat(ct['created_at'].replace('Z', '+00:00'))
                completed = datetime.fromisoformat(ct['completed_at'].replace('Z', '+00:00'))
                completion_time = (completed - created).total_seconds() / 3600  # hours
                completion_times.append(completion_time)
            except:
                pass
    
    avg_completion_time = statistics.mean(completion_times) if completion_times else 0
    
    utilization_rate = (len(assigned_testers) / total_testers * 100) if total_testers > 0 else 0
    completion_rate = (len(completed_tasks) / total_tasks * 100) if total_tasks > 0 else 0
    
    # Priority analysis
    for task_info in tasks.values():
        priority_distribution[task_info['priority']] += 1
    
    # Get device information for testers
    tester_devices = {}
    if st.session_state.roster_data is not None:
        for _, row in st.session_state.roster_data.iterrows():
            name = f"{row.get('first_name', '')} {row.get('last_name', '')}".strip()
            if name:
                device_info = get_tester_device_info(row)
                if device_info:
                    tester_devices[name] = device_info
    
    # Date range for the report
    date_range_str = f"{week_ago.strftime('%B %d, %Y')} - {now.strftime('%B %d, %Y')}"
    
    # Get multi-assigned testers
    multi_assigned = get_multi_assigned_testers()
    
    # Generate takeaways
    takeaways = []
    
    # Utilization takeaway
    if utilization_rate > 80:
        takeaways.append("🔴 **High Utilization Alert**: Over 80% of testers are currently assigned. Consider redistributing tasks or bringing in additional resources.")
    elif utilization_rate < 50:
        takeaways.append("🟢 **Resource Availability**: Less than 50% of testers are assigned. There's capacity for additional tasks.")
    else:
        takeaways.append("🟡 **Balanced Utilization**: Team utilization is at a healthy level between 50-80%.")
    
    # Multi-assignment takeaway
    if len(multi_assigned) > 0:
        takeaways.append(f"⚠️ **Assignment Conflicts**: {len(multi_assigned)} testers are assigned to multiple tasks. Review the Multi-Assigned tab to resolve conflicts.")
    
    # Completion rate takeaway
    if completion_rate > 75:
        takeaways.append("✅ **Strong Completion Rate**: Over 75% of tasks have been completed. Team is performing well.")
    elif completion_rate < 25:
        takeaways.append("📊 **Early Stage**: Less than 25% completion rate indicates most tasks are still in progress.")
    
    # Language demand takeaway
    if language_demand:
        top_lang = max(language_demand.items(), key=lambda x: x[1])[0]
        takeaways.append(f"🌐 **Language Focus**: {top_lang} is the most demanded language. Ensure adequate {top_lang} speakers are available.")
    
    # Priority balance takeaway
    critical_active = len([t for t in active_tasks if t[1]['priority'] == 'P0 - Critical'])
    if critical_active > 0:
        takeaways.append(f"🚨 **Critical Tasks**: {critical_active} P0-Critical tasks are active and should be prioritized.")
    
    # Available resources takeaway
    if available_testers_count == 0:
        takeaways.append("⚡ **All Hands on Deck**: All testers are currently assigned. No spare capacity available.")
    elif available_testers_count > total_testers * 0.3:
        takeaways.append(f"💡 **Underutilized Resources**: {available_testers_count} testers are available. Consider assigning them to pending tasks.")
    
    # Prepare text report content
    text_report = f"""
================================================================================
COMPREHENSIVE TASK ASSIGNMENT REPORT
================================================================================
Generated: {now.strftime('%B %d, %Y at %I:%M %p')}
By: {st.session_state.current_user}

================================================================================
EXECUTIVE SUMMARY
================================================================================
Total Tasks: {total_tasks}
Active Tasks: {len(active_tasks)}
Completed Tasks: {len(completed_tasks)}
Completion Rate: {completion_rate:.1f}%

Key Insights:
- Average task completion time: {avg_completion_time:.1f} hours
- Most active tester this week: {max(tester_weekly_count.items(), key=lambda x: x[1])[0] if tester_weekly_count else 'N/A'} ({max(tester_weekly_count.values()) if tester_weekly_count else 0} tasks)
- Most demanded language: {max(language_demand.items(), key=lambda x: x[1])[0] if language_demand else 'N/A'} ({max(language_demand.values()) if language_demand else 0} tasks)

================================================================================
KEY TAKEAWAYS & RECOMMENDATIONS
================================================================================
"""
    for takeaway in takeaways:
        text_report += f"• {takeaway}\n"
    
    text_report += f"""
================================================================================
RESOURCE UTILIZATION
================================================================================
Total Testers: {total_testers}
Currently Assigned: {len(assigned_testers)}
Available (Unassigned): {available_testers_count}
Current Utilization: {utilization_rate:.1f}%

================================================================================
TESTERS WITH MULTIPLE ASSIGNMENTS
================================================================================
Total testers with multiple active tasks: {len(multi_assigned)}

"""
    
    if multi_assigned:
        for tester, tasks_list in sorted(multi_assigned.items()):
            text_report += f"\n{tester} - Assigned to {len(tasks_list)} tasks:\n"
            for task in tasks_list:
                text_report += f"  • {task['task_name']} ({task['priority']}) - Languages: {', '.join(task['languages'])}\n"
    
    text_report += f"""
================================================================================
LANGUAGE DEMAND ANALYSIS (Week: {date_range_str})
================================================================================
"""
    
    if language_demand:
        for lang, count in sorted(language_demand.items(), key=lambda x: x[1], reverse=True):
            weekly = language_weekly_demand.get(lang, 0)
            text_report += f"{lang}: {count} total ({weekly} this week)\n"
    
    text_report += """
================================================================================
PRIORITY DISTRIBUTION
================================================================================
"""
    
    for priority in ["P0 - Critical", "P1 - High", "P2 - Medium", "P3 - Low"]:
        total_priority = priority_distribution.get(priority, 0)
        completed_priority = len([ct for ct in completed_tasks if ct.get('priority') == priority])
        active_priority = total_priority - completed_priority
        rate = (completed_priority / total_priority * 100) if total_priority > 0 else 0
        text_report += f"{priority}: Total={total_priority}, Active={active_priority}, Completed={completed_priority}, Rate={rate:.1f}%\n"
    
    # Add device information section to text report
    text_report += """
================================================================================
TESTER DEVICE INFORMATION
================================================================================
"""
    
    for tester_name, device_info in sorted(tester_devices.items()):
        if device_info:
            text_report += f"\n{tester_name}:\n"
            # Primary device
            if device_info.get('device_name'):
                text_report += f"  Device 1: {device_info['device_name']}"
                if device_info.get('serial_number'):
                    text_report += f" (SN: {device_info['serial_number']})"
                text_report += "\n"
            
            # Additional devices
            for i in range(2, 5):
                device_key = f'device_{i}'
                if device_key in device_info:
                    dev = device_info[device_key]
                    if dev.get('device_name'):
                        text_report += f"  Device {i}: {dev['device_name']}"
                        if dev.get('serial_number'):
                            text_report += f" (SN: {dev['serial_number']})"
                        text_report += "\n"
    
    text_report += """
================================================================================
ACTIVE TASKS DETAILS
================================================================================
"""
    
    for task_id, task_info in active_tasks:
        assignees = assignments.get(task_id, [])
        assignee_count = len(assignees)
        try:
            created_date = datetime.fromisoformat(task_info['created_at'].replace('Z', '+00:00')).strftime('%m/%d/%Y') if 'created_at' in task_info else 'N/A'
        except:
            created_date = 'N/A'
        text_report += f"\nTask: {task_info['name']}\n"
        text_report += f"  Priority: {task_info['priority']}\n"
        text_report += f"  Languages: {', '.join(task_info['languages'])}\n"
        text_report += f"  Created By: {task_info['created_by']} on {created_date}\n"
        text_report += f"  Assignees ({assignee_count}): {', '.join(assignees)}\n"
    
    text_report += """
================================================================================
RECENTLY COMPLETED TASKS
================================================================================
"""
    
    for ct in completed_tasks[-10:]:
        try:
            completion_date = datetime.fromisoformat(ct['completed_at'].replace('Z', '+00:00')).strftime('%m/%d/%Y %I:%M %p')
        except:
            completion_date = 'N/A'
        assignees = ct.get('assignees', [])
        assignee_count = len(assignees)
        text_report += f"\nTask: {ct.get('task_name', 'Unknown')}\n"
        text_report += f"  Priority: {ct.get('priority', 'Unknown')}\n"
        text_report += f"  Languages: {', '.join(ct.get('languages', []))}\n"
        text_report += f"  Completed By: {ct['completed_by']} on {completion_date}\n"
        text_report += f"  Assignees ({assignee_count}): {', '.join(assignees)}\n"
    
    text_report += """
================================================================================
END OF REPORT
================================================================================
"""
    
    # Generate HTML report with improved styling
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Comprehensive Task Assignment Report</title>
        <meta charset="UTF-8">
        <style>
            body {{ 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                min-height: 100vh; 
                padding: 20px; 
                margin: 0; 
            }}
            .container {{ 
                max-width: 1400px; 
                margin: 0 auto; 
                background: white; 
                border-radius: 20px; 
                box-shadow: 0 25px 50px rgba(0,0,0,0.2); 
                overflow: hidden; 
            }}
            .header {{ 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                color: white; 
                padding: 40px; 
                text-align: center; 
            }}
            .header h1 {{ 
                font-size: 2.5em; 
                margin: 0 0 10px 0; 
            }}
            .content {{ 
                padding: 40px; 
            }}
            h2 {{ 
                color: #667eea; 
                border-bottom: 3px solid #667eea; 
                padding-bottom: 10px; 
                margin-top: 30px; 
            }}
            h3 {{ 
                color: #764ba2; 
                margin-top: 20px; 
            }}
            .metrics {{ 
                display: grid; 
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
                gap: 20px; 
                margin: 20px 0; 
            }}
            .metric {{ 
                background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); 
                padding: 25px; 
                border-radius: 15px; 
                text-align: center; 
            }}
            .metric .value {{ 
                font-size: 2.5em; 
                font-weight: bold; 
                color: #667eea; 
            }}
            .metric .label {{ 
                color: #666; 
                margin-top: 5px; 
            }}
            .takeaways {{
                background: #e3f2fd;
                padding: 25px;
                border-radius: 15px;
                margin: 20px 0;
                border-left: 5px solid #2196f3;
            }}
            .takeaways h3 {{
                color: #1976d2;
                margin-top: 0;
            }}
            .takeaways ul {{
                margin: 10px 0;
                padding-left: 20px;
            }}
            .takeaways li {{
                margin: 10px 0;
                line-height: 1.6;
            }}
            table {{ 
                width: 100%; 
                border-collapse: collapse; 
                margin: 20px 0; 
            }}
            th {{ 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                color: white; 
                padding: 12px; 
                text-align: left; 
            }}
            td {{ 
                padding: 12px; 
                border-bottom: 1px solid #eee; 
                vertical-align: top;
            }}
            tr:hover {{ 
                background: #f8f9fa; 
            }}
            .tag {{ 
                display: inline-block; 
                padding: 4px 12px; 
                border-radius: 15px; 
                font-size: 0.85em; 
            }}
            .tag-critical {{ 
                background: #dc3545; 
                color: white; 
            }}
            .tag-high {{ 
                background: #fd7e14; 
                color: white; 
            }}
            .tag-medium {{ 
                background: #ffc107; 
                color: #333; 
            }}
            .tag-low {{ 
                background: #28a745; 
                color: white; 
            }}
            .highlight {{ 
                background: #fff3cd; 
                padding: 15px; 
                border-radius: 10px; 
                margin: 10px 0; 
            }}
            .multi-assigned {{
                background: #ffeaa7;
                padding: 20px;
                border-radius: 10px;
                margin: 20px 0;
            }}
            .multi-assigned-item {{
                background: white;
                padding: 15px;
                margin: 10px 0;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            .language-chart {{
                margin: 20px 0;
            }}
            .language-row {{
                display: flex;
                align-items: center;
                margin: 10px 0;
                padding: 10px;
                background: #f8f9fa;
                border-radius: 8px;
            }}
            .language-name {{
                width: 200px;
                font-weight: bold;
                color: #333;
            }}
            .language-bar-container {{
                flex: 1;
                background: #e9ecef;
                height: 35px;
                border-radius: 5px;
                position: relative;
                margin: 0 15px;
            }}
            .language-bar-fill {{
                background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
                height: 100%;
                border-radius: 5px;
                transition: width 0.3s ease;
            }}
            .language-stats {{
                min-width: 150px;
                text-align: right;
                font-weight: bold;
                color: #333;
            }}
            .assignee-list {{
                max-width: none;
                word-wrap: break-word;
            }}
            .footer {{ 
                background: #f8f9fa; 
                padding: 20px; 
                text-align: center; 
                color: #666; 
            }}
            .text-report {{
                background: #f8f9fa;
                padding: 20px;
                margin-top: 40px;
                border-radius: 10px;
            }}
            .text-report pre {{
                background: white;
                padding: 20px;
                border-radius: 5px;
                overflow-x: auto;
                font-family: 'Courier New', monospace;
                font-size: 0.9em;
                line-height: 1.5;
            }}
            .date-range {{
                color: #764ba2;
                font-style: italic;
                margin-top: 5px;
            }}
        </style>
    </head>
    <body>
    <div class="container">
        <div class="header">
            <h1>📊 Comprehensive Task Assignment Report</h1>
            <p>Generated: {now.strftime('%B %d, %Y at %I:%M %p')}</p>
            <p>By: {st.session_state.current_user}</p>
        </div>
        <div class="content">
            <h2>📈 Executive Summary</h2>
            <div class="metrics">
                <div class="metric"><div class="value">{total_tasks}</div><div class="label">Total Tasks</div></div>
                <div class="metric"><div class="value">{len(active_tasks)}</div><div class="label">Active</div></div>
                <div class="metric"><div class="value">{len(completed_tasks)}</div><div class="label">Completed</div></div>
                <div class="metric"><div class="value">{completion_rate:.1f}%</div><div class="label">Completion Rate</div></div>
            </div>
            
            <div class="highlight">
                <strong>Key Insights:</strong>
                <ul>
                    <li>Average task completion time: {avg_completion_time:.1f} hours</li>
                    <li>Most active tester this week: {max(tester_weekly_count.items(), key=lambda x: x[1])[0] if tester_weekly_count else 'N/A'} ({max(tester_weekly_count.values()) if tester_weekly_count else 0} tasks)</li>
                    <li>Most demanded language: {max(language_demand.items(), key=lambda x: x[1])[0] if language_demand else 'N/A'} ({max(language_demand.values()) if language_demand else 0} tasks)</li>
                </ul>
            </div>
            
            <div class="takeaways">
                <h3>🎯 Key Takeaways & Recommendations</h3>
                <ul>
    """
    
    for takeaway in takeaways:
        html += f"<li>{takeaway}</li>\n"
    
    html += f"""
                </ul>
            </div>
            
            <h2>👥 Resource Utilization</h2>
            <div class="metrics">
                <div class="metric"><div class="value">{total_testers}</div><div class="label">Total Testers</div></div>
                <div class="metric"><div class="value">{len(assigned_testers)}</div><div class="label">Currently Assigned</div></div>
                <div class="metric"><div class="value">{available_testers_count}</div><div class="label">Available (Unassigned)</div></div>
                <div class="metric"><div class="value">{utilization_rate:.1f}%</div><div class="label">Current Utilization</div></div>
            </div>
    """
    
    # Add multi-assigned testers section
    if multi_assigned:
        html += f"""
            <div class="multi-assigned">
                <h2>⚠️ Testers with Multiple Assignments</h2>
                <p>Total testers assigned to multiple active tasks: <strong>{len(multi_assigned)}</strong></p>
        """
        
        for tester, tasks_list in sorted(multi_assigned.items()):
            html += f"""
                <div class="multi-assigned-item">
                    <h4>{tester} - Assigned to {len(tasks_list)} tasks:</h4>
                    <ul>
            """
            for task in tasks_list:
                tag_class = {'P0 - Critical': 'tag-critical', 'P1 - High': 'tag-high', 'P2 - Medium': 'tag-medium', 'P3 - Low': 'tag-low'}.get(task['priority'], '')
                html += f"""<li><strong>{task['task_name']}</strong> <span class="tag {tag_class}">{task['priority']}</span> - Languages: {', '.join(task['languages'])}</li>"""
            html += """
                    </ul>
                </div>
            """
        
        html += "</div>"
    
    html += f"""
            <h3>📊 Tester Activity (This Week)</h3>
            <table>
                <tr><th>Tester</th><th>Tasks This Week</th><th>Tasks This Month</th><th>Total Tasks</th><th>Completed</th><th>Current Load</th><th>Device Info</th></tr>
    """
    
    # Sort testers by weekly activity
    all_testers = set()
    if st.session_state.roster_data is not None:
        for _, row in st.session_state.roster_data.iterrows():
            name = f"{row.get('first_name', '')} {row.get('last_name', '')}".strip()
            if name:
                all_testers.add(name)
    
    tester_stats = []
    for tester in all_testers:
        weekly = tester_weekly_count.get(tester, 0)
        monthly = tester_monthly_count.get(tester, 0)
        total = tester_assignment_count.get(tester, 0)
        completed = tester_completion_count.get(tester, 0)
        current = tester_workload.get(tester, 0)
        tester_stats.append((tester, weekly, monthly, total, completed, current))
    
    tester_stats.sort(key=lambda x: x[1], reverse=True)  # Sort by weekly activity
    
    for tester, weekly, monthly, total, completed, current in tester_stats[:20]:  # Top 20
        device_info = tester_devices.get(tester, {})
        device_str = ""
        if device_info:
            if device_info.get('device_name'):
                device_str = device_info['device_name']
                if device_info.get('serial_number'):
                    device_str += f" (SN: {device_info['serial_number']})"
            # Check for additional devices
            for i in range(2, 5):
                device_key = f'device_{i}'
                if device_key in device_info and device_info[device_key].get('device_name'):
                    device_str += f", {device_info[device_key]['device_name']}"
        # Don't show "-" if no device info
        html += f'<tr><td><strong>{tester}</strong></td><td>{weekly}</td><td>{monthly}</td><td>{total}</td><td>{completed}</td><td>{current}</td><td>{device_str}</td></tr>'
    
    html += f"""
            </table>
            
            <h2>🌐 Language Demand Analysis</h2>
            <h3>Language Requirements (All Time)</h3>
            <p class="date-range">Week Period: {date_range_str}</p>
            <div class="language-chart">
    """
    
    # Improved language demand chart - TEXT ALWAYS VISIBLE
    if language_demand:
        max_demand = max(language_demand.values())
        for lang, count in sorted(language_demand.items(), key=lambda x: x[1], reverse=True):
            width = (count / max_demand * 100) if max_demand > 0 else 0
            weekly = language_weekly_demand.get(lang, 0)
            html += f'''
                <div class="language-row">
                    <div class="language-name">{lang}</div>
                    <div class="language-bar-container">
                        <div class="language-bar-fill" style="width: {width}%;"></div>
                    </div>
                    <div class="language-stats">{count} total ({weekly} this week)</div>
                </div>
            '''
    
    html += """
            </div>
            
            <h2>🎯 Priority Distribution</h2>
            <table>
                <tr><th>Priority</th><th>Total Tasks</th><th>Active</th><th>Completed</th><th>Completion Rate</th></tr>
    """
    
    for priority in ["P0 - Critical", "P1 - High", "P2 - Medium", "P3 - Low"]:
        total_priority = priority_distribution.get(priority, 0)
        completed_priority = len([ct for ct in completed_tasks if ct.get('priority') == priority])
        active_priority = total_priority - completed_priority
        rate = (completed_priority / total_priority * 100) if total_priority > 0 else 0
        tag_class = {'P0 - Critical': 'tag-critical', 'P1 - High': 'tag-high', 'P2 - Medium': 'tag-medium', 'P3 - Low': 'tag-low'}.get(priority, '')
        html += f'<tr><td><span class="tag {tag_class}">{priority}</span></td><td>{total_priority}</td><td>{active_priority}</td><td>{completed_priority}</td><td>{rate:.1f}%</td></tr>'
    
    html += """
            </table>
            
            <h2>📋 Active Tasks Details</h2>
            <table>
                <tr><th>Task</th><th>Priority</th><th>Languages</th><th>Assignees</th><th>Count</th><th>Created By</th><th>Created</th></tr>
    """
    
    # Show ALL assignees without ellipsis
    for task_id, task_info in active_tasks:
        assignees = assignments.get(task_id, [])
        assignee_count = len(assignees)
        try:
            created_date = datetime.fromisoformat(task_info['created_at'].replace('Z', '+00:00')).strftime('%m/%d/%Y') if 'created_at' in task_info else 'N/A'
        except:
            created_date = 'N/A'
        tag_class = {'P0 - Critical': 'tag-critical', 'P1 - High': 'tag-high', 'P2 - Medium': 'tag-medium', 'P3 - Low': 'tag-low'}.get(task_info['priority'], '')
        # Show ALL assignees
        assignee_display = ', '.join(assignees) if assignees else 'None'
        html += f'<tr><td><strong>{task_info["name"]}</strong></td><td><span class="tag {tag_class}">{task_info["priority"]}</span></td><td>{", ".join(task_info["languages"])}</td><td class="assignee-list">{assignee_display}</td><td><strong>{assignee_count}</strong></td><td>{task_info["created_by"]}</td><td>{created_date}</td></tr>'
    
    html += """
            </table>
            
            <h2>✅ Recently Completed Tasks</h2>
            <table>
                <tr><th>Task</th><th>Priority</th><th>Languages</th><th>Completed By</th><th>Completion Time</th><th>Assignees</th><th>Count</th></tr>
    """
    
    # Show last 10 completed tasks with ALL assignees
    for ct in completed_tasks[-10:]:
        try:
            completion_date = datetime.fromisoformat(ct['completed_at'].replace('Z', '+00:00')).strftime('%m/%d/%Y %I:%M %p')
        except:
            completion_date = 'N/A'
        tag_class = {'P0 - Critical': 'tag-critical', 'P1 - High': 'tag-high', 'P2 - Medium': 'tag-medium', 'P3 - Low': 'tag-low'}.get(ct.get('priority', ''), '')
        assignees = ct.get('assignees', [])
        assignee_count = len(assignees)
        # Show ALL assignees
        assignee_display = ', '.join(assignees) if assignees else 'None'
        html += f'<tr><td><strong>{ct.get("task_name", "Unknown")}</strong></td><td><span class="tag {tag_class}">{ct.get("priority", "Unknown")}</span></td><td>{", ".join(ct.get("languages", []))}</td><td>{ct["completed_by"]}</td><td>{completion_date}</td><td class="assignee-list">{assignee_display}</td><td><strong>{assignee_count}</strong></td></tr>'
    
    # Add text report at the bottom
    html += f"""
            </table>
            
            <div class="text-report">
                <h2>📄 Text Version of Report</h2>
                <pre>{text_report}</pre>
            </div>
        </div>
        <div class="footer">
            <p>Task Assignment Tool v7.3 | Comprehensive Analytics Report | Generated: {now.strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
    </div>
    </body>
    </html>
    """
    
    return html

def dismiss_conflict_message():
    """Dismiss conflict message"""
    st.session_state.show_conflict_message = False
    st.session_state.last_conflict_message = None

# Add custom JavaScript for persistent user and keep-alive
st.markdown("""
<script>
    // Save user to localStorage
    const urlParams = new URLSearchParams(window.location.search);
    const user = urlParams.get('user');
    if (user) {
        localStorage.setItem('taskAssignmentUser', user);
    }
    
    // Restore user from localStorage if not in URL
    if (!user) {
        const savedUser = localStorage.getItem('taskAssignmentUser');
        if (savedUser) {
            const newUrl = window.location.pathname + '?user=' + encodeURIComponent(savedUser);
            window.history.replaceState({}, '', newUrl);
        }
    }
    
    // Keep-alive ping to prevent sleep
    setInterval(() => {
        fetch(window.location.href, {method: 'HEAD'});
    }, 60000); // Ping every minute
</script>
""", unsafe_allow_html=True)

# Main UI
st.title("📋 Team Task Assignment Tool")

# Add refresh button at the top
col1, col2 = st.columns([10, 1])
with col2:
    if st.button("🔄", help="Refresh to see latest changes"):
        st.cache_data.clear()
        st.rerun()

# Check GitHub configuration
if not GITHUB_TOKEN or not GITHUB_REPO:
    st.error("⚠️ GitHub configuration missing!")
    st.info("""
    Please add the following to your Streamlit secrets:
    ```toml
    [github]
    token = "your-github-personal-access-token"
    repo = "username/repository-name"
    branch = "main"
    ```
    """)
    st.stop()

# User identification
if st.session_state.current_user is None:
    st.warning("Please enter your name to continue")
    user_name = st.text_input("Your Name (Team Lead)", placeholder="e.g., John Smith")
    if user_name:
        st.session_state.current_user = user_name
        st.query_params['user'] = user_name
        st.rerun()
else:
    # Multi-user warning banner
    st.info("""
    💡 **Multi-User Support Active**: This tool supports multiple team leads working simultaneously. 
    The system will automatically handle conflicts and merge changes when possible.
    Use the 🔄 button to refresh and see the latest updates from other users.
    """)
    
    # Show last modified info
    last_user, last_time = get_last_modified_info()
    if last_time != "Unknown":
        try:
            last_modified_dt = datetime.fromisoformat(last_time.replace('Z', '+00:00'))
            time_ago = datetime.now() - last_modified_dt.replace(tzinfo=None)
            if time_ago.total_seconds() < 60:
                time_str = f"{int(time_ago.total_seconds())} seconds ago"
            elif time_ago.total_seconds() < 3600:
                time_str = f"{int(time_ago.total_seconds() / 60)} minutes ago"
            else:
                time_str = f"{int(time_ago.total_seconds() / 3600)} hours ago"
            
            st.info(f"📝 Last modified by **{last_user}** {time_str}")
        except:
            st.info(f"📝 Last modified by **{last_user}**")
    
    col1, col2 = st.columns([6, 1])
    with col1:
        st.caption(f"👤 Current User: {st.session_state.current_user}")
    with col2:
        if st.button("Switch User"):
            st.session_state.current_user = None
            st.query_params.clear()
            st.rerun()

# Main interface
if st.session_state.current_user:
    # Conflict message
    if st.session_state.last_conflict_message and st.session_state.show_conflict_message:
        with st.container():
            col1, col2 = st.columns([10, 1])
            with col1:
                st.warning("⚠️ **Assignment Conflicts:**")
                for conflict in st.session_state.last_conflict_message['conflicts']:
                    st.write(f"  • {conflict}")
            with col2:
                if st.button("✖"):
                    dismiss_conflict_message()
                    st.rerun()
    
    # Sidebar - UPDATED WITH BETTER FILE HANDLING
    with st.sidebar:
        st.header("📊 Team Roster")
        st.info("💡 Export from Numbers as CSV (.csv) for best results")
        
        # File uploader
        uploaded_file = st.file_uploader("Upload roster", type=['xlsx', 'csv'], key="roster_upload")
        
        if uploaded_file:
            # Create file identifier
            file_id = f"{uploaded_file.name}_{uploaded_file.size}_{uploaded_file.file_id}"
            
            # Check if it's a new file
            is_new_file = st.session_state.last_uploaded_file_id != file_id
            
            if is_new_file:
                st.session_state.last_uploaded_file_id = file_id
                # Clear old roster data
                if 'roster_data' in st.session_state:
                    del st.session_state.roster_data
                st.info("📁 New file detected, processing...")
            
            # Add manual refresh button
            col1, col2 = st.columns([2, 1])
            with col2:
                if st.button("🔄 Refresh", key="refresh_roster"):
                    st.cache_data.clear()
                    if 'roster_data' in st.session_state:
                        del st.session_state.roster_data
                    st.rerun()
            
            try:
                # Always read from the beginning
                uploaded_file.seek(0)
                
                if uploaded_file.name.endswith('.csv'):
                    # Use our ultra-smart CSV parser
                    df = parse_csv_ultra_smart(uploaded_file)
                else:
                    uploaded_file.seek(0)  # Reset again for Excel
                    df = pd.read_excel(uploaded_file, engine='openpyxl')
                
                # Debug: Show raw columns before normalization
                with st.expander("🔍 Debug: Column Detection", expanded=False):
                    st.write("**File:** ", uploaded_file.name)
                    st.write("**Size:** ", uploaded_file.size, "bytes")
                    st.write("**Raw columns detected:**")
                    st.write(list(df.columns))
                    st.write("**First few rows:**")
                    st.dataframe(df.head())
                
                df = normalize_column_names(df)
                
                # Debug: Show normalized columns
                with st.expander("🔍 Debug: After Normalization", expanded=False):
                    st.write("**Normalized columns:**")
                    st.write(list(df.columns))
                    st.write("**Data preview:**")
                    st.dataframe(df.head())
                
                missing = validate_required_columns(df)
                
                if missing:
                    st.error(f"Missing required columns: {', '.join(missing)}")
                    st.warning("""
                    **Required columns:**
                    - First Name (or similar: firstname, first, fname, given name)
                    - Last Name (or similar: lastname, last, lname, surname, family name)
                    
                    **Optional columns:**
                    - Language 1, Language 2, Language 3, Language 4
                    - Device Name, Device Type, Serial Number, etc.
                    
                    **Tips:**
                    - Make sure your CSV has headers in the first or second row
                    - Column names are case-insensitive
                    - Spaces, underscores, and hyphens are handled automatically
                    - Duplicate column names are automatically numbered (e.g., currently_used_by_2)
                    """)
                else:
                    # Filter out empty rows
                    df = df[(df['first_name'].notna()) & (df['first_name'] != '') &
                           (df['last_name'].notna()) & (df['last_name'] != '')]
                    
                    # Force update session state
                    st.session_state.roster_data = df.copy()  # Use copy to ensure it's a new object
                    
                    st.success(f"✅ Loaded {len(df)} team members from {uploaded_file.name}")
                    
                    # Show what changed if it's a new file
                    if is_new_file and 'previous_roster_size' in st.session_state:
                        diff = len(df) - st.session_state.previous_roster_size
                        if diff > 0:
                            st.info(f"📈 Added {diff} team members")
                        elif diff < 0:
                            st.info(f"📉 Removed {abs(diff)} team members")
                    
                    st.session_state.previous_roster_size = len(df)
                    
                    # Show validation issues if any
                    issues = validate_roster_data(df)
                    if issues:
                        for issue in issues:
                            st.warning(issue)
                            
            except Exception as e:
                st.error(f"Error loading file: {str(e)}")
                # Clear cache on error
                if st.button("Clear cache and try again"):
                    st.cache_data.clear()
                    if 'roster_data' in st.session_state:
                        del st.session_state.roster_data
                    st.rerun()
                
                st.info("""
                **Tips for CSV files:**
                - Make sure the file has column headers
                - Common delimiters are supported (comma, tab, semicolon)
                - The tool can handle extra header rows (like A, B, C...)
                - Duplicate column names are automatically handled
                - Export from Numbers/Excel as "CSV UTF-8" for best results
                """)
        
        # Live task summary
        if st.session_state.roster_data is not None:
            try:
                tasks = load_tasks()
                assignments = load_assignments()
                completed = load_completed_tasks()
                completed_ids = [c['task_id'] for c in completed]
                active_task_ids = [t for t in tasks if t not in completed_ids]
                
                # Calculate available testers
                all_testers = set()
                assigned_testers = set()
                
                for _, row in st.session_state.roster_data.iterrows():
                    name = f"{row.get('first_name', '')} {row.get('last_name', '')}".strip()
                    if name:
                        all_testers.add(name)
                
                for task_id, assignees in assignments.items():
                    if task_id not in completed_ids:
                        assigned_testers.update(assignees)
                
                available_count = len(all_testers - assigned_testers)
                
                st.divider()
                st.subheader("📊 Live Dashboard")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Active Tasks", len(active_task_ids))
                    st.metric("Available Testers", available_count, help="Testers not assigned to any active task")
                with col2:
                    st.metric("Total Tasks", len(tasks))
                    st.metric("Team Size", len(st.session_state.roster_data))
                
                # Show completed today metric
                today_completed = 0
                for c in completed:
                    try:
                        if datetime.fromisoformat(c['completed_at'].replace('Z', '+00:00')).date() == datetime.now().date():
                            today_completed += 1
                    except:
                        pass
                st.metric("Completed Today", today_completed)
                
                # NEW: Show multi-assigned testers count
                multi_assigned = get_multi_assigned_testers()
                if multi_assigned:
                    st.warning(f"⚠️ {len(multi_assigned)} testers have multiple tasks")
                
                # Active Tasks List
                st.divider()
                st.subheader("📋 Active Tasks")
                
                if active_task_ids:
                    # Sort tasks by priority
                    priority_order = {"P0 - Critical": 0, "P1 - High": 1, "P2 - Medium": 2, "P3 - Low": 3}
                    sorted_tasks = sorted(active_task_ids, 
                                        key=lambda tid: priority_order.get(tasks[tid]['priority'], 4))
                    
                    for task_id in sorted_tasks:
                        task_info = tasks[task_id]
                        assignees = assignments.get(task_id, [])
                        assignee_count = len(assignees)
                        
                        # Priority color coding
                        priority_colors = {
                            "P0 - Critical": "🔴",
                            "P1 - High": "🟠",
                            "P2 - Medium": "🟡",
                            "P3 - Low": "🟢"
                        }
                        priority_icon = priority_colors.get(task_info['priority'], "⚪")
                        
                        with st.expander(f"{priority_icon} {task_info['name']} ({assignee_count} assignees)"):
                            st.write(f"**Priority:** {task_info['priority']}")
                            st.write(f"**Languages:** {', '.join(task_info['languages'])}")
                            st.write(f"**Created by:** {task_info['created_by']}")
                            st.write(f"**Assignee Count:** {assignee_count}")
                            
                            if assignees:
                                st.write("**Assigned to:**")
                                for assignee in sorted(assignees):
                                    st.write(f"  • {assignee}")
                            else:
                                st.write("**No assignees yet**")
                else:
                    st.info("No active tasks")
                
                st.divider()
                if st.button("🔄 Refresh Dashboard", use_container_width=True, type="primary"):
                    st.cache_data.clear()
                    st.rerun()
                
                st.caption("⚠️ Refresh frequently if multiple users are active")
                    
            except Exception as e:
                st.error(f"Data loading error: {e}")
        
        # Reports and Data Management section
        if st.session_state.roster_data is not None:
            st.divider()
            st.subheader("📈 Reports")
            
            # Reports
            if st.button("📊 Generate Report", type="primary", use_container_width=True):
                report = generate_detailed_report()
                st.download_button(
                    "📥 Download Report",
                    data=report,
                    file_name=f"detailed_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
                    mime="text/html",
                    use_container_width=True
                )
            
            # Data Management - More visible
            st.divider()
            st.subheader("🗄️ Data Management")
            
            # Show data reset confirmation
            if st.session_state.show_reset_confirmation:
                st.error("⚠️ **WARNING: Reset All Data?**")
                st.warning("This will permanently delete:")
                st.write("• All tasks")
                st.write("• All assignments")
                st.write("• All history")
                st.write("• All completed tasks")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("✅ Yes, Reset Everything", type="primary", use_container_width=True):
                        if reset_all_data():
                            st.success("✅ All data has been reset!")
                            st.session_state.show_reset_confirmation = False
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error("Failed to reset data")
                with col2:
                    if st.button("❌ Cancel", use_container_width=True):
                        st.session_state.show_reset_confirmation = False
                        st.rerun()
            else:
                # Make the reset button more prominent
                st.warning("⚠️ **Start Fresh**")
                st.caption("Use this to reset all data and start a new week/period")
                if st.button("🗑️ RESET ALL DATA", type="secondary", use_container_width=True, 
                           help="Delete all tasks and start fresh"):
                    st.session_state.show_reset_confirmation = True
                    st.rerun()
    
    # Main content
    if st.session_state.roster_data is None:
        st.info("👈 Upload the team roster to start")
    else:
        try:
            tasks = load_tasks()
            assignments = load_assignments()
            completed_tasks = load_completed_tasks()
            completed_task_ids = [ct['task_id'] for ct in completed_tasks]
            
            # NEW: Add a fourth tab for multi-assigned testers
            tab1, tab2, tab3, tab4 = st.tabs(["📝 Create Task", "👥 Manage", "✅ Status", "⚠️ Multi-Assigned"])
            
            # Tab 1: Create Task - UPDATED TO SHOW ALL LANGUAGES
            with tab1:
                st.header("Create New Task")
                
                # Refresh reminder
                col1, col2 = st.columns([4, 1])
                with col2:
                    if st.button("🔄 Refresh", help="Refresh to see latest changes"):
                        st.cache_data.clear()
                        st.rerun()
                
                col1, col2 = st.columns(2)
                
                with col1:
                    task_name = st.text_input("Task Name", placeholder="e.g., Siri Validation")
                    priority = st.selectbox("Priority", ["P0 - Critical", "P1 - High", "P2 - Medium", "P3 - Low"])
                
                with col2:
                    all_languages = set()
                    for _, row in st.session_state.roster_data.iterrows():
                        all_languages.update(get_tester_languages(row))
                    all_languages = {l for l in all_languages if l}
                    
                    language_requirements = st.multiselect("Languages", sorted(all_languages))
                    match_all = st.checkbox("Require ALL languages", value=False)
                
                if task_name and language_requirements:
                    st.subheader("📋 Available Testers")
                    
                    available_testers = get_available_testers(language_requirements, match_all)
                    
                    if available_testers:
                        fully_available = [t for t in available_testers if t['is_available']]
                        if fully_available:
                            st.success(f"✨ {len(fully_available)} fully available")
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            if st.button("✅ Select Available", use_container_width=True):
                                for i, t in enumerate(available_testers):
                                    st.session_state[f"check_{i}"] = t['is_available']
                                st.rerun()
                        with col2:
                            if st.button("☑️ Select All", use_container_width=True):
                                for i in range(len(available_testers)):
                                    st.session_state[f"check_{i}"] = True
                                st.rerun()
                        with col3:
                            if st.button("❌ Clear", use_container_width=True):
                                for i in range(len(available_testers)):
                                    st.session_state[f"check_{i}"] = False
                                st.rerun()
                        
                        st.divider()
                        
                        selected_testers = []
                        for i, tester in enumerate(available_testers):
                            col1, col2, col3, col4 = st.columns([3, 1, 2, 3])
                            
                            with col1:
                                key = f"check_{i}"
                                if key not in st.session_state:
                                    st.session_state[key] = tester['is_available']
                                if st.checkbox(tester['name'], key=key):
                                    selected_testers.append(tester['name'])
                            
                            with col2:
                                st.write("🟢" if tester['is_available'] else "🔴")
                            
                            with col3:
                                # Show ALL languages, not just matching ones
                                st.write(", ".join(sorted(tester['languages'])))
                            
                            with col4:
                                if tester['assigned_tasks']:
                                    task_list = [f"{n}" for n, p in tester['assigned_tasks']]
                                    st.write(", ".join(task_list))
                                else:
                                    st.write("-")
                        
                        st.metric("Selected", len(selected_testers))
                        
                        if st.button("🚀 Create Task", type="primary", use_container_width=True):
                            if selected_testers:
                                existing = [t['name'] for t in tasks.values()]
                                if task_name in existing:
                                    st.error("Task name exists!")
                                else:
                                    task_id = f"TASK_{get_task_counter():03d}"
                                    
                                    task_info = {
                                        'name': task_name,
                                        'priority': priority,
                                        'languages': language_requirements,
                                        'created_at': datetime.now().isoformat(),
                                        'created_by': st.session_state.current_user
                                    }
                                    
                                    # Save task first
                                    if save_task(task_id, task_info):
                                        # Save ALL selected testers (including those already assigned)
                                        save_assignments(task_id, selected_testers)
                                        
                                        # Check for conflicts but still assign them
                                        conflicts = []
                                        for name in selected_testers:
                                            tester = next((t for t in available_testers if t['name'] == name), None)
                                            if tester and not tester['is_available']:
                                                other_tasks = [task_name for task_name, _ in tester['assigned_tasks']]
                                                conflicts.append(f"{name} is also assigned to: {', '.join(other_tasks)}")
                                        
                                        if conflicts:
                                            st.session_state.last_conflict_message = {'task_name': task_name, 'priority': priority, 'conflicts': conflicts}
                                            st.session_state.show_conflict_message = True
                                        
                                        for i in range(len(available_testers)):
                                            if f"check_{i}" in st.session_state:
                                                del st.session_state[f"check_{i}"]
                                        
                                        st.success(f"✅ Task created with {len(selected_testers)} assignees!")
                                        st.rerun()
                                    else:
                                        st.error("Failed to save task. Please try again.")
                            else:
                                st.error("Select at least one tester")
                    else:
                        st.warning("No testers match criteria")
            
            # Tab 2: Manage - ENHANCED WITH LANGUAGE FILTERING
            with tab2:
                st.header("Manage Assignments")
                
                # Refresh reminder
                col1, col2 = st.columns([4, 1])
                with col2:
                    if st.button("🔄 Refresh", key="refresh_manage", help="Refresh to see latest changes"):
                        st.cache_data.clear()
                        st.rerun()
                
                active_tasks = [(tid, tinfo) for tid, tinfo in tasks.items() if tid not in completed_task_ids]
                
                if active_tasks:
                    priority_order = {"P0 - Critical": 0, "P1 - High": 1, "P2 - Medium": 2, "P3 - Low": 3}
                    active_tasks.sort(key=lambda x: priority_order.get(x[1]['priority'], 4))
                    
                    for task_id, task_info in active_tasks:
                        current_assignees = assignments.get(task_id, [])
                        assignee_count = len(current_assignees)
                        
                        with st.expander(f"📌 {task_info['name']} - {task_info['priority']} ({assignee_count} assignees)"):
                            st.write(f"**Created by:** {task_info['created_by']}")
                            st.write(f"**Languages:** {', '.join(task_info['languages'])}")
                            st.write(f"**Assigned ({assignee_count}):** {', '.join(current_assignees) if current_assignees else 'None'}")
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                new_priority = st.selectbox(
                                    "Priority",
                                    ["P0 - Critical", "P1 - High", "P2 - Medium", "P3 - Low"],
                                    index=["P0 - Critical", "P1 - High", "P2 - Medium", "P3 - Low"].index(task_info['priority']),
                                    key=f"pri_{task_id}"
                                )
                                if new_priority != task_info['priority']:
                                    if st.button("Update", key=f"upd_{task_id}"):
                                        task_info['priority'] = new_priority
                                        save_task(task_id, task_info)
                                        st.rerun()
                            
                            with col2:
                                if st.button("✅ Complete", key=f"comp_{task_id}", type="primary"):
                                    mark_task_completed(task_id, st.session_state.current_user)
                                    st.rerun()
                            
                            st.divider()
                            
                            # ENHANCED: Get all testers with language info
                            all_testers_info = get_all_testers_with_languages()
                            
                            # Language filter for assignees
                            st.write("**Manage Assignees:**")
                            
                            # Get all unique languages from testers
                            all_tester_languages = set()
                            for tester_info in all_testers_info:
                                all_tester_languages.update(tester_info['languages'])
                            
                            # Filter by language
                            col1, col2 = st.columns([2, 3])
                            with col1:
                                filter_language = st.selectbox(
                                    "Filter by language",
                                    ["All"] + sorted(list(all_tester_languages)),
                                    key=f"filter_lang_{task_id}"
                                )
                            
                            # Filter testers based on selected language
                            if filter_language == "All":
                                filtered_testers = all_testers_info
                            else:
                                filtered_testers = [t for t in all_testers_info if filter_language in t['languages']]
                            
                            # Create display names with languages
                            tester_display_names = {}
                            for tester in filtered_testers:
                                langs_str = ", ".join(sorted(tester['languages']))
                                display_name = f"{tester['name']} [{langs_str}]"
                                tester_display_names[display_name] = tester['name']
                            
                            # Multiselect with language info
                            current_display_names = []
                            for assignee in current_assignees:
                                tester_info = next((t for t in all_testers_info if t['name'] == assignee), None)
                                if tester_info:
                                    langs_str = ", ".join(sorted(tester_info['languages']))
                                    current_display_names.append(f"{assignee} [{langs_str}]")
                            
                            new_assignees_display = st.multiselect(
                                f"Assignees (showing: {filter_language})",
                                sorted(list(tester_display_names.keys())),
                                default=[d for d in current_display_names if d in tester_display_names.keys()],
                                key=f"assign_{task_id}"
                            )
                            
                            # Convert display names back to actual names
                            new_assignees = [tester_display_names[display] for display in new_assignees_display]
                            
                            if len(new_assignees) != assignee_count:
                                st.info(f"Change: {assignee_count} → {len(new_assignees)} assignees")
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                if st.button("💾 Save", key=f"save_{task_id}"):
                                    save_assignments(task_id, new_assignees)
                                    st.rerun()
                            with col2:
                                if st.button("🗑️ Delete", key=f"del_{task_id}"):
                                    delete_task(task_id)
                                    st.rerun()
                else:
                    st.info("No active tasks")
            
            # Tab 3: Status - ENHANCED WITH DATE RANGE
            with tab3:
                st.header("Task Status Overview")
                
                # Refresh reminder
                col1, col2 = st.columns([4, 1])
                with col2:
                    if st.button("🔄 Refresh", key="refresh_status", help="Refresh to see latest changes"):
                        st.cache_data.clear()
                        st.rerun()
                
                # Calculate available testers for the metrics
                all_testers = set()
                assigned_testers = set()
                
                for _, row in st.session_state.roster_data.iterrows():
                    name = f"{row.get('first_name', '')} {row.get('last_name', '')}".strip()
                    if name:
                        all_testers.add(name)
                
                for task_id, assignees in assignments.items():
                    if task_id not in completed_task_ids:
                        assigned_testers.update(assignees)
                
                available_count = len(all_testers - assigned_testers)
                
                # Summary metrics
                col1, col2, col3, col4, col5 = st.columns(5)
                with col1:
                    st.metric("Active", len([t for t in tasks if t not in completed_task_ids]))
                with col2:
                    st.metric("Completed", len(completed_tasks))
                with col3:
                    st.metric("Total Tasks", len(tasks))
                with col4:
                    st.metric("Team Size", len(st.session_state.roster_data))
                with col5:
                    st.metric("Available", available_count, help="Testers not assigned to any task")
                
                st.divider()
                
                # Analytics section with date range
                st.subheader("📊 Quick Analytics")
                
                # Calculate date range
                now = datetime.now()
                week_ago = now - timedelta(days=7)
                date_range_str = f"{week_ago.strftime('%B %d, %Y')} - {now.strftime('%B %d, %Y')}"
                
                # Language demand this week
                assignment_history = load_assignment_history()
                language_weekly_demand = defaultdict(int)
                
                for record in assignment_history:
                    try:
                        assigned_date = datetime.fromisoformat(record['assigned_at'].replace('Z', '+00:00'))
                        if assigned_date >= week_ago:
                            for lang in record.get('languages', []):
                                language_weekly_demand[lang] += 1
                    except:
                        pass
                
                if language_weekly_demand:
                    st.write(f"**Most Demanded Languages This Week**")
                    st.caption(f"📅 Period: {date_range_str}")
                    for lang, count in sorted(language_weekly_demand.items(), key=lambda x: x[1], reverse=True)[:5]:
                        st.write(f"• {lang}: {count} tasks")
                
                st.divider()
                
                # Team Member Details
                with st.expander("👥 Team Member Details"):
                    df_display = st.session_state.roster_data.copy()
                    df_display['Full Name'] = df_display['first_name'] + ' ' + df_display['last_name']
                    
                    # Add task count
                    task_counts = {}
                    for _, row in df_display.iterrows():
                        name = f"{row['first_name']} {row['last_name']}".strip()
                        count = 0
                        for task_id, assignees in assignments.items():
                            if task_id not in completed_task_ids and name in assignees:
                                count += 1
                        task_counts[name] = count
                    
                    df_display['Active Tasks'] = df_display['Full Name'].map(task_counts).fillna(0).astype(int)
                    
                    # Select columns to display
                    display_columns = ['Full Name', 'Active Tasks']
                    for col in ['language_1', 'language_2', 'language_3', 'language_4']:
                        if col in df_display.columns:
                            display_columns.append(col)
                    
                    st.dataframe(df_display[display_columns].sort_values('Active Tasks', ascending=False))
                
                # Unassigned testers
                unassigned = all_testers - assigned_testers
                
                if unassigned:
                    with st.expander(f"⚠️ Available Testers ({len(unassigned)})"):
                        cols = st.columns(3)
                        for i, name in enumerate(sorted(unassigned)):
                            with cols[i % 3]:
                                st.write(f"• {name}")
                
                # Active and completed tasks with counts
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("🔴 Active Tasks")
                    for tid in [t for t in tasks if t not in completed_task_ids]:
                        info = tasks[tid]
                        assignees = assignments.get(tid, [])
                        assignee_count = len(assignees)
                        st.write(f"**{info['name']}**")
                        st.caption(f"{info['priority']} | **{assignee_count}** assignees | {', '.join(info['languages'])}")
                        st.divider()
                
                with col2:
                    st.subheader("✅ Recently Completed")
                    for ct in completed_tasks[-10:]:
                        assignee_count = len(ct.get('assignees', []))
                        st.write(f"**{ct.get('task_name', 'Unknown')}**")
                        try:
                            completion_time = datetime.fromisoformat(ct['completed_at'].replace('Z', '+00:00')).strftime('%m/%d %I:%M %p')
                        except:
                            completion_time = 'N/A'
                        st.caption(f"By {ct['completed_by']} | {assignee_count} assignees | {completion_time}")
                        st.divider()
            
            # NEW Tab 4: Multi-Assigned Testers
            with tab4:
                st.header("⚠️ Testers with Multiple Assignments")
                
                # Refresh reminder
                col1, col2 = st.columns([4, 1])
                with col2:
                    if st.button("🔄 Refresh", key="refresh_multi", help="Refresh to see latest changes"):
                        st.cache_data.clear()
                        st.rerun()
                
                multi_assigned = get_multi_assigned_testers()
                
                if multi_assigned:
                    st.warning(f"**{len(multi_assigned)} testers** are assigned to multiple active tasks")
                    st.info("Review these assignments and decide where each tester should be located")
                    
                    # Sort by number of assignments (descending)
                    sorted_multi = sorted(multi_assigned.items(), key=lambda x: len(x[1]), reverse=True)
                    
                    for tester, tasks_list in sorted_multi:
                        with st.expander(f"👤 {tester} - Assigned to {len(tasks_list)} tasks"):
                            st.write(f"**Current Assignments:**")
                            
                            for i, task in enumerate(tasks_list):
                                priority_colors = {
                                    "P0 - Critical": "🔴",
                                    "P1 - High": "🟠",
                                    "P2 - Medium": "🟡",
                                    "P3 - Low": "🟢"
                                }
                                priority_icon = priority_colors.get(task['priority'], "⚪")
                                
                                st.write(f"{i+1}. {priority_icon} **{task['task_name']}**")
                                st.caption(f"   Priority: {task['priority']} | Languages: {', '.join(task['languages'])}")
                            
                            st.divider()
                            
                            # Quick action buttons
                            st.write("**Quick Actions:**")
                            st.caption("Remove this tester from selected tasks:")
                            
                            cols = st.columns(min(len(tasks_list), 3))
                            for i, task in enumerate(tasks_list):
                                with cols[i % 3]:
                                    if st.button(f"Remove from {task['task_name'][:20]}...", 
                                               key=f"remove_{tester}_{task['task_id']}",
                                               use_container_width=True):
                                        # Remove tester from this task
                                        current_assignees = assignments.get(task['task_id'], [])
                                        if tester in current_assignees:
                                            current_assignees.remove(tester)
                                            save_assignments(task['task_id'], current_assignees)
                                            st.success(f"Removed {tester} from {task['task_name']}")
                                            st.rerun()
                else:
                    st.success("✅ No testers are assigned to multiple tasks!")
                    st.info("All testers are assigned to at most one active task.")
        
        except Exception as e:
            st.error(f"Data error: {e}")
            st.info("Click 'Refresh' to retry")

# Footer with tips
st.divider()
col1, col2 = st.columns([3, 1])
with col1:
    st.caption("Team Task Assignment Tool v7.3 | GitHub Storage | Multi-User Support")
with col2:
    with st.expander("💡 Tips"):
        st.markdown("""
        **To prevent app from sleeping:**
        - Keep the tab open and active
        - Interact with the app periodically
        - The app auto-pings every minute
        
        **CSV Upload Tips:**
        - Export as CSV UTF-8 from Numbers/Excel
        - Headers should be in first or second row
        - Tool handles various formats automatically
        - Duplicate column names are automatically numbered
        
        **Note:** Week periods in reports update automatically
        """)
