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
        return None
    
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

def save_data_to_github(data, sha=None, file_name=DATA_FILE):
    """Save data to GitHub"""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        st.error("GitHub configuration missing in secrets")
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
        else:
            st.error(f"GitHub save error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        st.error(f"Error saving to GitHub: {e}")
        return False

# Data Management Functions
@st.cache_data(ttl=10)  # Short cache to reduce API calls but stay fresh
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
    """Save all data to GitHub"""
    _, current_sha = get_data_from_github()
    success = save_data_to_github(data, current_sha)
    if success:
        st.cache_data.clear()  # Clear cache to force reload
    return success

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
    """Save a task"""
    data, _ = load_all_data()
    data["tasks"][task_id] = task_info
    if save_all_data(data):
        st.success("Task saved!")

def delete_task(task_id):
    """Delete a task"""
    data, _ = load_all_data()
    if task_id in data["tasks"]:
        del data["tasks"][task_id]
    if task_id in data["assignments"]:
        del data["assignments"][task_id]
    save_all_data(data)

def load_assignments():
    """Load assignments"""
    data, _ = load_all_data()
    return data.get("assignments", {})

def save_assignments(task_id, testers):
    """Save assignments and track history"""
    data, _ = load_all_data()
    
    # Track assignment history
    task_info = data["tasks"].get(task_id, {})
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
    save_all_data(data)

def load_completed_tasks():
    """Load completed tasks"""
    data, _ = load_all_data()
    return data.get("completed_tasks", [])

def mark_task_completed(task_id, completed_by):
    """Mark a task as completed"""
    data, _ = load_all_data()
    
    # Get task info before marking complete
    task_info = data["tasks"].get(task_id, {})
    assignees = data["assignments"].get(task_id, [])
    
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

# Helper Functions
def normalize_column_names(df):
    """Normalize column names"""
    first_col = df.columns[0]
    if 'unnamed' in str(first_col).lower() or first_col == 0 or pd.isna(first_col):
        df = df.iloc[:, 1:]
    
    new_columns = {}
    for col in df.columns:
        if pd.isna(col):
            continue
        col_str = str(col).strip().lower().replace(' ', '_')
        
        if col_str in ['first_name', 'firstname', 'first', 'fname', 'given_name']:
            new_columns[col] = 'first_name'
        elif col_str in ['last_name', 'lastname', 'last', 'lname', 'surname', 'family_name']:
            new_columns[col] = 'last_name'
        elif col_str in ['language_1', 'language1', 'lang1', 'lang_1']:
            new_columns[col] = 'language_1'
        elif col_str in ['language_2', 'language2', 'lang2', 'lang_2']:
            new_columns[col] = 'language_2'
        elif col_str in ['language_3', 'language3', 'lang3', 'lang_3']:
            new_columns[col] = 'language_3'
        elif col_str in ['language_4', 'language4', 'lang4', 'lang_4']:
            new_columns[col] = 'language_4'
        elif col_str in ['public_device_name', 'device_name', 'device']:
            new_columns[col] = 'public_device_name'
        elif col_str in ['device_type', 'type']:
            new_columns[col] = 'device_type'
        elif col_str in ['serial_number', 'serial', 'sn']:
            new_columns[col] = 'serial_number'
        elif col_str in ['currently_used_by', 'used_by', 'current_user']:
            new_columns[col] = 'currently_used_by'
        else:
            new_columns[col] = col_str
    
    df = df.rename(columns=new_columns)
    df = df.dropna(axis=1, how='all')
    return df

def validate_required_columns(df):
    """Check required columns"""
    required = ['first_name', 'last_name']
    return [col for col in required if col not in df.columns]

def normalize_language(lang):
    """Normalize language codes"""
    if pd.isna(lang) or lang == '' or str(lang).lower() == 'nan':
        return None
    
    lang = str(lang).strip()
    lang_upper = lang.upper()
    
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
    """Get device information for a tester"""
    device_info = {}
    if 'public_device_name' in row.index and pd.notna(row['public_device_name']):
        device_info['device_name'] = str(row['public_device_name'])
    if 'device_type' in row.index and pd.notna(row['device_type']):
        device_info['device_type'] = str(row['device_type'])
    if 'serial_number' in row.index and pd.notna(row['serial_number']):
        device_info['serial_number'] = str(row['serial_number'])
    if 'currently_used_by' in row.index and pd.notna(row['currently_used_by']):
        device_info['currently_used_by'] = str(row['currently_used_by'])
    return device_info

def get_available_testers(language_requirements, match_all=False):
    """Get available testers"""
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
                'languages': tester_languages,
                'matching_languages': matching_languages,
                'assigned_tasks': assigned_tasks,
                'is_available': len(assigned_tasks) == 0,
                'device_info': device_info
            })
    
    available_testers.sort(key=lambda x: (-len(x['matching_languages']), not x['is_available'], x['name']))
    return available_testers

def generate_detailed_report():
    """Generate comprehensive analytics report"""
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
        
        assigned_date = datetime.fromisoformat(record['assigned_at'].replace('Z', '+00:00'))
        if assigned_date >= week_ago:
            tester_weekly_count[record['tester']] += 1
        if assigned_date >= month_ago:
            tester_monthly_count[record['tester']] += 1
        
        for lang in record.get('languages', []):
            language_demand[lang] += 1
            if assigned_date >= week_ago:
                language_weekly_demand[lang] += 1
    
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
RESOURCE UTILIZATION
================================================================================
Total Testers: {total_testers}
Currently Assigned: {len(assigned_testers)}
Available (Unassigned): {available_testers_count}
Current Utilization: {utilization_rate:.1f}%

================================================================================
LANGUAGE DEMAND ANALYSIS
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
    
    text_report += """
================================================================================
ACTIVE TASKS DETAILS
================================================================================
"""
    
    for task_id, task_info in active_tasks:
        assignees = assignments.get(task_id, [])
        assignee_count = len(assignees)
        created_date = datetime.fromisoformat(task_info['created_at'].replace('Z', '+00:00')).strftime('%m/%d/%Y') if 'created_at' in task_info else 'N/A'
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
        completion_date = datetime.fromisoformat(ct['completed_at'].replace('Z', '+00:00')).strftime('%m/%d/%Y %I:%M %p')
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
            .language-chart {{
                margin: 20px 0;
                padding: 20px;
                background: #f8f9fa;
                border-radius: 10px;
            }}
            .language-item {{
                margin: 15px 0;
                padding: 15px;
                background: white;
                border-radius: 8px;
                border-left: 4px solid #667eea;
            }}
            .language-name {{
                font-size: 1.1em;
                font-weight: bold;
                color: #333;
                margin-bottom: 8px;
            }}
            .language-bar {{
                background: #e9ecef;
                height: 30px;
                border-radius: 5px;
                position: relative;
                overflow: hidden;
            }}
            .language-bar-fill {{
                background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
                height: 100%;
                display: flex;
                align-items: center;
                justify-content: flex-end;
                padding-right: 10px;
                color: white;
                font-weight: bold;
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
            
            <h2>👥 Resource Utilization</h2>
            <div class="metrics">
                <div class="metric"><div class="value">{total_testers}</div><div class="label">Total Testers</div></div>
                <div class="metric"><div class="value">{len(assigned_testers)}</div><div class="label">Currently Assigned</div></div>
                <div class="metric"><div class="value">{available_testers_count}</div><div class="label">Available (Unassigned)</div></div>
                <div class="metric"><div class="value">{utilization_rate:.1f}%</div><div class="label">Current Utilization</div></div>
            </div>
            
            <h3>📊 Tester Activity (This Week)</h3>
            <table>
                <tr><th>Tester</th><th>Tasks This Week</th><th>Tasks This Month</th><th>Total Tasks</th><th>Completed</th><th>Current Load</th></tr>
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
        html += f'<tr><td><strong>{tester}</strong></td><td>{weekly}</td><td>{monthly}</td><td>{total}</td><td>{completed}</td><td>{current}</td></tr>'
    
    html += """
            </table>
            
            <h2>🌐 Language Demand Analysis</h2>
            <h3>Language Requirements (All Time)</h3>
            <div class="language-chart">
    """
    
    # Improved language demand chart - NO OVERLAPPING
    if language_demand:
        max_demand = max(language_demand.values())
        for lang, count in sorted(language_demand.items(), key=lambda x: x[1], reverse=True):
            width = (count / max_demand * 100) if max_demand > 0 else 0
            weekly = language_weekly_demand.get(lang, 0)
            html += f'''
                <div class="language-item">
                    <div class="language-name">{lang}</div>
                    <div class="language-bar">
                        <div class="language-bar-fill" style="width: {width}%;">
                            {count} total ({weekly} this week)
                        </div>
                    </div>
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
        created_date = datetime.fromisoformat(task_info['created_at'].replace('Z', '+00:00')).strftime('%m/%d/%Y') if 'created_at' in task_info else 'N/A'
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
        completion_date = datetime.fromisoformat(ct['completed_at'].replace('Z', '+00:00')).strftime('%m/%d/%Y %I:%M %p')
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
            <p>Task Assignment Tool v6.3 | Comprehensive Analytics Report | Generated: {now.strftime('%Y-%m-%d %H:%M:%S')}</p>
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

# Add custom JavaScript for persistent user
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
</script>
""", unsafe_allow_html=True)

# Main UI
st.title("📋 Team Task Assignment Tool")

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
    st.warning("""
    ⚠️ **Multiple Users Warning**: This tool supports multiple team leads working simultaneously. 
    To avoid conflicts:
    - **Refresh frequently** using the 🔄 button to see latest changes
    - **Save your work promptly** to prevent overwriting others' changes
    - **Check "Last Modified"** info before making changes
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
    
    # Sidebar
    with st.sidebar:
        st.header("📊 Team Roster")
        st.info("💡 Export from Numbers as CSV (.csv) for best results")
        
        uploaded_file = st.file_uploader("Upload roster", type=['xlsx', 'csv'])
        
        if uploaded_file:
            try:
                if uploaded_file.name.endswith('.csv'):
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file, engine='openpyxl')
                
                df = normalize_column_names(df)
                missing = validate_required_columns(df)
                
                if missing:
                    st.error(f"Missing: {', '.join(missing)}")
                else:
                    df = df[(df['first_name'].notna()) & (df['first_name'] != '') &
                           (df['last_name'].notna()) & (df['last_name'] != '')]
                    st.session_state.roster_data = df
                    st.success(f"✅ Loaded {len(df)} members")
                    
                    # Show device info if available
                    device_columns = ['public_device_name', 'device_type', 'serial_number', 'currently_used_by']
                    available_device_columns = [col for col in device_columns if col in df.columns]
                    if available_device_columns:
                        st.info(f"📱 Device info available: {', '.join(available_device_columns)}")
                    
            except Exception as e:
                st.error(f"Error: {e}")
        
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
                st.metric("Completed Today", len([c for c in completed if datetime.fromisoformat(c['completed_at'].replace('Z', '+00:00')).date() == datetime.now().date()]))
                
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
            
            tab1, tab2, tab3 = st.tabs(["📝 Create Task", "👥 Manage", "✅ Status"])
            
            # Tab 1: Create Task
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
                            col1, col2, col3, col4, col5 = st.columns([3, 1, 2, 3, 2])
                            
                            with col1:
                                key = f"check_{i}"
                                if key not in st.session_state:
                                    st.session_state[key] = tester['is_available']
                                if st.checkbox(tester['name'], key=key):
                                    selected_testers.append(tester['name'])
                            
                            with col2:
                                st.write("🟢" if tester['is_available'] else "🔴")
                            
                            with col3:
                                st.write(", ".join(tester['matching_languages']))
                            
                            with col4:
                                if tester['assigned_tasks']:
                                    task_list = [f"{n}" for n, p in tester['assigned_tasks']]
                                    st.write(", ".join(task_list))
                                else:
                                    st.write("-")
                            
                            with col5:
                                # Show device info if available
                                device_info = tester.get('device_info', {})
                                if device_info.get('device_name'):
                                    st.caption(f"📱 {device_info.get('device_name', '')}")
                        
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
                                    save_task(task_id, task_info)
                                    
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
                                st.error("Select at least one tester")
                    else:
                        st.warning("No testers match criteria")
            
            # Tab 2: Manage
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
                            
                            available = get_available_testers(task_info['languages'], False)
                            new_assignees = st.multiselect(
                                f"Assignees (currently {assignee_count})",
                                [t['name'] for t in available],
                                default=current_assignees,
                                key=f"assign_{task_id}"
                            )
                            
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
            
            # Tab 3: Status
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
                
                # Analytics section
                st.subheader("📊 Quick Analytics")
                
                # Language demand this week
                assignment_history = load_assignment_history()
                week_ago = datetime.now() - timedelta(days=7)
                language_weekly_demand = defaultdict(int)
                
                for record in assignment_history:
                    assigned_date = datetime.fromisoformat(record['assigned_at'].replace('Z', '+00:00'))
                    if assigned_date >= week_ago:
                        for lang in record.get('languages', []):
                            language_weekly_demand[lang] += 1
                
                if language_weekly_demand:
                    st.write("**Most Demanded Languages This Week:**")
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
                    
                    # Add device info columns if available
                    for col in ['public_device_name', 'device_type', 'serial_number']:
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
                        st.caption(f"By {ct['completed_by']} | {assignee_count} assignees | {datetime.fromisoformat(ct['completed_at'].replace('Z', '+00:00')).strftime('%m/%d %I:%M %p')}")
                        st.divider()
        
        except Exception as e:
            st.error(f"Data error: {e}")
            st.info("Click 'Refresh' to retry")

# Footer
st.divider()
st.caption("Team Task Assignment Tool v6.3 | GitHub Storage | Multi-User Support")
