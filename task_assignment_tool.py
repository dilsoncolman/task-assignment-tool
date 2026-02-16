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
                "task_counter": 1
            }, None
        else:
            st.error(f"GitHub API error: {response.status_code}")
            return None, None
    except Exception as e:
        st.error(f"Error loading data from GitHub: {e}")
        return None, None

def save_data_to_github(data, sha=None):
    """Save data to GitHub"""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        st.error("GitHub configuration missing in secrets")
        return False
    
    try:
        import base64
        content = base64.b64encode(json.dumps(data, indent=2).encode('utf-8')).decode('utf-8')
        
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{DATA_FILE}"
        
        payload = {
            "message": f"Update task data - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
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
@st.cache_data(ttl=30)  # Cache for 30 seconds to reduce API calls
def load_all_data():
    """Load all data from GitHub"""
    data, sha = get_data_from_github()
    if data:
        return data, sha
    return {
        "tasks": {},
        "assignments": {},
        "completed_tasks": [],
        "task_counter": 1
    }, None

def save_all_data(data):
    """Save all data to GitHub"""
    _, current_sha = get_data_from_github()
    success = save_data_to_github(data, current_sha)
    if success:
        st.cache_data.clear()  # Clear cache to force reload
    return success

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
    """Save assignments"""
    data, _ = load_all_data()
    data["assignments"][task_id] = testers
    save_all_data(data)

def load_completed_tasks():
    """Load completed tasks"""
    data, _ = load_all_data()
    return data.get("completed_tasks", [])

def mark_task_completed(task_id, completed_by):
    """Mark a task as completed"""
    data, _ = load_all_data()
    data["completed_tasks"].append({
        'task_id': task_id,
        'completed_by': completed_by,
        'completed_at': datetime.now().isoformat()
    })
    save_all_data(data)

def get_task_counter():
    """Get the next task counter"""
    data, _ = load_all_data()
    counter = data.get("task_counter", 1)
    data["task_counter"] = counter + 1
    save_all_data(data)
    return counter

# Initialize session state
if 'roster_data' not in st.session_state:
    st.session_state.roster_data = None
if 'current_user' not in st.session_state:
    # Try to get from localStorage via query params
    query_params = st.query_params
    st.session_state.current_user = query_params.get('user', None)
if 'show_conflict_message' not in st.session_state:
    st.session_state.show_conflict_message = False
if 'last_conflict_message' not in st.session_state:
    st.session_state.last_conflict_message = None

# Helper Functions (same as before)
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
                'is_available': len(assigned_tasks) == 0
            })
    
    available_testers.sort(key=lambda x: (-len(x['matching_languages']), not x['is_available'], x['name']))
    return available_testers

def generate_report():
    """Generate analytics report"""
    tasks = load_tasks()
    assignments = load_assignments()
    completed_tasks = load_completed_tasks()
    completed_task_ids = [ct['task_id'] for ct in completed_tasks]
    
    total_tasks = len(tasks)
    active_tasks = [(tid, tinfo) for tid, tinfo in tasks.items() if tid not in completed_task_ids]
    now = datetime.now()
    
    total_testers = len(st.session_state.roster_data) if st.session_state.roster_data is not None else 0
    assigned_testers = set()
    tester_workload = defaultdict(int)
    
    for task_id, assignees in assignments.items():
        if task_id not in completed_task_ids:
            for tester in assignees:
                assigned_testers.add(tester)
                tester_workload[tester] += 1
    
    utilization_rate = (len(assigned_testers) / total_testers * 100) if total_testers > 0 else 0
    completion_rate = (len(completed_tasks) / total_tasks * 100) if total_tasks > 0 else 0
    
    priority_count = Counter()
    for task_info in tasks.values():
        priority_count[task_info['priority']] += 1
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Task Assignment Report</title>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; margin: 0; }}
            .container {{ max-width: 1200px; margin: 0 auto; background: white; border-radius: 20px; box-shadow: 0 25px 50px rgba(0,0,0,0.2); overflow: hidden; }}
            .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 40px; text-align: center; }}
            .header h1 {{ font-size: 2.5em; margin: 0 0 10px 0; }}
            .content {{ padding: 40px; }}
            h2 {{ color: #667eea; border-bottom: 3px solid #667eea; padding-bottom: 10px; margin-top: 30px; }}
            .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }}
            .metric {{ background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); padding: 25px; border-radius: 15px; text-align: center; }}
            .metric .value {{ font-size: 2.5em; font-weight: bold; color: #667eea; }}
            .metric .label {{ color: #666; margin-top: 5px; }}
            table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
            th {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 12px; text-align: left; }}
            td {{ padding: 12px; border-bottom: 1px solid #eee; }}
            tr:hover {{ background: #f8f9fa; }}
            .tag {{ display: inline-block; padding: 4px 12px; border-radius: 15px; font-size: 0.85em; }}
            .tag-critical {{ background: #dc3545; color: white; }}
            .tag-high {{ background: #fd7e14; color: white; }}
            .tag-medium {{ background: #ffc107; color: #333; }}
            .tag-low {{ background: #28a745; color: white; }}
            .footer {{ background: #f8f9fa; padding: 20px; text-align: center; color: #666; }}
        </style>
    </head>
    <body>
    <div class="container">
        <div class="header">
            <h1>📊 Task Assignment Report</h1>
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
            
            <h2>👥 Resource Utilization</h2>
            <div class="metrics">
                <div class="metric"><div class="value">{total_testers}</div><div class="label">Total Testers</div></div>
                <div class="metric"><div class="value">{len(assigned_testers)}</div><div class="label">Assigned</div></div>
                <div class="metric"><div class="value">{utilization_rate:.1f}%</div><div class="label">Utilization</div></div>
                <div class="metric"><div class="value">{total_testers - len(assigned_testers)}</div><div class="label">Available</div></div>
            </div>
            
            <h2>🎯 Priority Distribution</h2>
            <table>
                <tr><th>Priority</th><th>Count</th><th>Percentage</th></tr>
    """
    
    for priority in ["P0 - Critical", "P1 - High", "P2 - Medium", "P3 - Low"]:
        count = priority_count.get(priority, 0)
        pct = (count / total_tasks * 100) if total_tasks > 0 else 0
        tag_class = {'P0 - Critical': 'tag-critical', 'P1 - High': 'tag-high', 'P2 - Medium': 'tag-medium', 'P3 - Low': 'tag-low'}.get(priority, '')
        html += f'<tr><td><span class="tag {tag_class}">{priority}</span></td><td>{count}</td><td>{pct:.1f}%</td></tr>'
    
    html += """
            </table>
            
            <h2>📋 Active Tasks</h2>
            <table>
                <tr><th>Task</th><th>Priority</th><th>Languages</th><th>Assignees</th><th>Created By</th></tr>
    """
    
    for task_id, task_info in active_tasks:
        assignees = assignments.get(task_id, [])
        tag_class = {'P0 - Critical': 'tag-critical', 'P1 - High': 'tag-high', 'P2 - Medium': 'tag-medium', 'P3 - Low': 'tag-low'}.get(task_info['priority'], '')
        html += f'<tr><td><strong>{task_info["name"]}</strong></td><td><span class="tag {tag_class}">{task_info["priority"]}</span></td><td>{", ".join(task_info["languages"])}</td><td>{len(assignees)}</td><td>{task_info["created_by"]}</td></tr>'
    
    html += f"""
            </table>
        </div>
        <div class="footer">
            <p>Task Assignment Tool v4.0 | Generated: {now.strftime('%Y-%m-%d %H:%M:%S')}</p>
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

# Add custom CSS for persistent user
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
            window.location.reload();
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
            except Exception as e:
                st.error(f"Error: {e}")
        
        # Task summary
        if st.session_state.roster_data is not None:
            try:
                tasks = load_tasks()
                completed = load_completed_tasks()
                completed_ids = [c['task_id'] for c in completed]
                active = [t for t in tasks if t not in completed_ids]
                
                st.divider()
                st.metric("Active Tasks", len(active))
                st.metric("Total Tasks", len(tasks))
                
                if st.button("🔄 Refresh", use_container_width=True):
                    st.cache_data.clear()
                    st.rerun()
            except Exception as e:
                st.error(f"Data loading error: {e}")
        
        # Report
        if st.session_state.roster_data is not None:
            st.divider()
            if st.button("📊 Generate Report", type="primary", use_container_width=True):
                report = generate_report()
                st.download_button(
                    "📥 Download",
                    data=report,
                    file_name=f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
                    mime="text/html",
                    use_container_width=True
                )
    
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
                                st.write(", ".join(tester['matching_languages']))
                            
                            with col4:
                                if tester['assigned_tasks']:
                                    st.write(", ".join([f"{n} ({p})" for n, p in tester['assigned_tasks']]))
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
                                    
                                    save_task(task_id, task_info)
                                    save_assignments(task_id, selected_testers)
                                    
                                    conflicts = []
                                    for name in selected_testers:
                                        tester = next((t for t in available_testers if t['name'] == name), None)
                                        if tester and not tester['is_available']:
                                            conflicts.append(f"{name} already assigned")
                                    
                                    if conflicts:
                                        st.session_state.last_conflict_message = {'task_name': task_name, 'priority': priority, 'conflicts': conflicts}
                                        st.session_state.show_conflict_message = True
                                    
                                    for i in range(len(available_testers)):
                                        if f"check_{i}" in st.session_state:
                                            del st.session_state[f"check_{i}"]
                                    
                                    st.success("✅ Task created!")
                                    st.rerun()
                            else:
                                st.error("Select at least one tester")
                    else:
                        st.warning("No testers match criteria")
            
            # Tab 2: Manage
            with tab2:
                st.header("Manage Assignments")
                
                active_tasks = [(tid, tinfo) for tid, tinfo in tasks.items() if tid not in completed_task_ids]
                
                if active_tasks:
                    priority_order = {"P0 - Critical": 0, "P1 - High": 1, "P2 - Medium": 2, "P3 - Low": 3}
                    active_tasks.sort(key=lambda x: priority_order.get(x[1]['priority'], 4))
                    
                    for task_id, task_info in active_tasks:
                        with st.expander(f"📌 {task_info['name']} - {task_info['priority']}"):
                            current = assignments.get(task_id, [])
                            
                            st.write(f"**Created by:** {task_info['created_by']}")
                            st.write(f"**Languages:** {', '.join(task_info['languages'])}")
                            st.write(f"**Assigned:** {', '.join(current) if current else 'None'}")
                            
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
                                "Assignees",
                                [t['name'] for t in available],
                                default=current,
                                key=f"assign_{task_id}"
                            )
                            
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
                st.header("Task Status")
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Active", len([t for t in tasks if t not in completed_task_ids]))
                with col2:
                    st.metric("Completed", len(completed_tasks))
                with col3:
                    st.metric("Total", len(tasks))
                with col4:
                    st.metric("Testers", len(st.session_state.roster_data))
                
                st.divider()
                
                # Unassigned
                all_testers = set()
                assigned = set()
                
                for _, row in st.session_state.roster_data.iterrows():
                    name = f"{row['first_name']} {row['last_name']}".strip()
                    if name:
                        all_testers.add(name)
                
                for task_id, assignees in assignments.items():
                    if task_id not in completed_task_ids:
                        assigned.update(assignees)
                
                unassigned = all_testers - assigned
                
                if unassigned:
                    with st.expander(f"⚠️ Unassigned ({len(unassigned)})"):
                        cols = st.columns(3)
                        for i, name in enumerate(sorted(unassigned)):
                            with cols[i % 3]:
                                st.write(f"• {name}")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("🔴 Active")
                    for tid in [t for t in tasks if t not in completed_task_ids]:
                        info = tasks[tid]
                        assignees = assignments.get(tid, [])
                        st.write(f"**{info['name']}**")
                        st.caption(f"{info['priority']} | {len(assignees)} assignees")
                        st.divider()
                
                with col2:
                    st.subheader("✅ Completed")
                    for ct in completed_tasks[-10:]:
                        if ct['task_id'] in tasks:
                            info = tasks[ct['task_id']]
                            st.write(f"**{info['name']}**")
                            st.caption(f"By {ct['completed_by']}")
                            st.divider()
        
        except Exception as e:
            st.error(f"Data error: {e}")
            st.info("Click 'Refresh' in the sidebar to retry")

# Footer
st.divider()
st.caption("Team Task Assignment Tool v4.0 | GitHub Storage")
