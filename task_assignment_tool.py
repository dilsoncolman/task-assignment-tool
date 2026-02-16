import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import io
from typing import Dict, List, Set, Tuple
import re
import hashlib
import json
from collections import Counter, defaultdict
import time
import statistics

# Page config
st.set_page_config(
    page_title="Team Task Assignment Tool",
    page_icon="📋",
    layout="wide"
)

# Initialize session state - PERSISTENT STORAGE
if 'roster_data' not in st.session_state:
    st.session_state.roster_data = None
if 'tasks' not in st.session_state:
    st.session_state.tasks = {}
if 'assignments' not in st.session_state:
    st.session_state.assignments = {}
if 'completed_tasks' not in st.session_state:
    st.session_state.completed_tasks = []
if 'historical_data' not in st.session_state:
    st.session_state.historical_data = []
if 'current_user' not in st.session_state:
    query_params = st.query_params
    st.session_state.current_user = query_params.get('user', None)
if 'task_locks' not in st.session_state:
    st.session_state.task_locks = {}
if 'task_counter' not in st.session_state:
    st.session_state.task_counter = 1
if 'show_conflict_message' not in st.session_state:
    st.session_state.show_conflict_message = True
if 'last_conflict_message' not in st.session_state:
    st.session_state.last_conflict_message = None
if 'assignment_locks' not in st.session_state:
    st.session_state.assignment_locks = {}
if 'last_update' not in st.session_state:
    st.session_state.last_update = datetime.now()
if 'task_modifications' not in st.session_state:
    st.session_state.task_modifications = []

# Helper Functions
def acquire_assignment_lock(task_id, user):
    """Acquire a lock for editing assignments"""
    current_time = datetime.now()
    
    if task_id in st.session_state.assignment_locks:
        lock_info = st.session_state.assignment_locks[task_id]
        lock_user = lock_info['user']
        lock_time = lock_info['time']
        
        if (current_time - lock_time).seconds > 30:
            del st.session_state.assignment_locks[task_id]
        elif lock_user != user:
            return False, lock_user
    
    st.session_state.assignment_locks[task_id] = {
        'user': user,
        'time': current_time
    }
    return True, user

def release_assignment_lock(task_id, user):
    """Release an assignment lock"""
    if task_id in st.session_state.assignment_locks:
        if st.session_state.assignment_locks[task_id]['user'] == user:
            del st.session_state.assignment_locks[task_id]

def normalize_column_names(df):
    """Normalize column names to match expected format"""
    first_col = df.columns[0]
    if 'unnamed' in str(first_col).lower() or first_col == 0 or pd.isna(first_col):
        df = df.iloc[:, 1:]
    
    new_columns = {}
    
    for col in df.columns:
        if pd.isna(col):
            continue
            
        col_str = str(col).strip().lower().replace(' ', '_')
        
        if col_str == 'first_name':
            new_columns[col] = 'first_name'
        elif col_str == 'last_name':
            new_columns[col] = 'last_name'
        elif col_str == 'language_1':
            new_columns[col] = 'language_1'
        elif col_str == 'language_2':
            new_columns[col] = 'language_2'
        elif col_str == 'language_3':
            new_columns[col] = 'language_3'
        elif col_str == 'language_4':
            new_columns[col] = 'language_4'
        elif col_str in ['firstname', 'first', 'fname', 'given_name']:
            new_columns[col] = 'first_name'
        elif col_str in ['lastname', 'last', 'lname', 'surname', 'family_name']:
            new_columns[col] = 'last_name'
        elif col_str in ['language1', 'lang1', 'lang_1']:
            new_columns[col] = 'language_1'
        elif col_str in ['language2', 'lang2', 'lang_2']:
            new_columns[col] = 'language_2'
        elif col_str in ['language3', 'lang3', 'lang_3']:
            new_columns[col] = 'language_3'
        elif col_str in ['language4', 'lang4', 'lang_4']:
            new_columns[col] = 'language_4'
        else:
            new_columns[col] = col_str
    
    df = df.rename(columns=new_columns)
    df = df.dropna(axis=1, how='all')
    
    return df

def validate_required_columns(df):
    """Check if required columns exist"""
    required_columns = ['first_name', 'last_name']
    missing_columns = []
    
    for col in required_columns:
        if col not in df.columns:
            missing_columns.append(col)
    
    return missing_columns

def normalize_language(lang):
    """Enhanced language normalization with comprehensive ISO code mapping"""
    if pd.isna(lang) or lang == '' or str(lang).lower() == 'nan':
        return None
    
    lang = str(lang).strip()
    lang_upper = lang.upper()
    lang_lower = lang.lower()
    
    language_map = {
        'EN': 'English', 'EN_US': 'English', 'EN_GB': 'English', 'EN_IE': 'English',
        'EN_AU': 'English', 'EN_CA': 'English', 'EN_NZ': 'English', 'EN_ZA': 'English',
        'ENGLISH': 'English',
        'IT': 'Italian', 'IT_IT': 'Italian', 'ITALIAN': 'Italian',
        'FR': 'French', 'FR_FR': 'French', 'FR_CA': 'French', 'FR_BE': 'French',
        'FR_CH': 'French', 'FRENCH': 'French',
        'NB': 'Norwegian', 'NB_NO': 'Norwegian', 'NO': 'Norwegian', 'NO_NO': 'Norwegian',
        'NN': 'Norwegian', 'NN_NO': 'Norwegian', 'NORWEGIAN': 'Norwegian',
        'RU': 'Russian', 'RU_RU': 'Russian', 'RUSSIAN': 'Russian',
        'ZH': 'Chinese', 'ZH_CN': 'Chinese (Simplified)', 'ZH_XC': 'Chinese (Simplified)',
        'ZH_TW': 'Chinese (Traditional)', 'ZH_HK': 'Chinese (Traditional)',
        'CHINESE': 'Chinese',
        'HE': 'Hebrew', 'HE_IL': 'Hebrew', 'IL_HE': 'Hebrew', 'IW': 'Hebrew',
        'IW_IL': 'Hebrew', 'HEBREW': 'Hebrew',
        'DE': 'German', 'DE_DE': 'German', 'DE_AT': 'German', 'DE_CH': 'German',
        'GERMAN': 'German',
        'ES': 'Spanish', 'ES_ES': 'Spanish', 'ES_MX': 'Spanish', 'ES_AR': 'Spanish',
        'ES_CO': 'Spanish', 'ES_CL': 'Spanish', 'SPANISH': 'Spanish',
        'PT': 'Portuguese', 'PT_PT': 'Portuguese', 'PT_BR': 'Portuguese',
        'PORTUGUESE': 'Portuguese',
        'JA': 'Japanese', 'JA_JP': 'Japanese', 'JAPANESE': 'Japanese',
        'KO': 'Korean', 'KO_KR': 'Korean', 'KOREAN': 'Korean',
        'NL': 'Dutch', 'NL_NL': 'Dutch', 'NL_BE': 'Dutch', 'DUTCH': 'Dutch',
        'SV': 'Swedish', 'SV_SE': 'Swedish', 'SWEDISH': 'Swedish',
        'DA': 'Danish', 'DA_DK': 'Danish', 'DANISH': 'Danish',
        'FI': 'Finnish', 'FI_FI': 'Finnish', 'FINNISH': 'Finnish',
        'PL': 'Polish', 'PL_PL': 'Polish', 'POLISH': 'Polish',
        'TR': 'Turkish', 'TR_TR': 'Turkish', 'TURKISH': 'Turkish',
        'AR': 'Arabic', 'AR_SA': 'Arabic', 'AR_AE': 'Arabic', 'AR_EG': 'Arabic',
        'ARABIC': 'Arabic',
        'TH': 'Thai', 'TH_TH': 'Thai', 'THAI': 'Thai',
        'HI': 'Hindi', 'HI_IN': 'Hindi', 'HINDI': 'Hindi',
    }
    
    if '_' in lang_lower:
        prefix = lang_lower.split('_')[0].upper()
        if prefix in language_map:
            return language_map[prefix]
    
    if lang_upper in language_map:
        return language_map[lang_upper]
    
    for code, full_name in language_map.items():
        if lang_upper.startswith(code + '_') or lang_upper.startswith(code + '-'):
            return full_name
    
    return lang.capitalize()

def validate_roster_data(df):
    """Validate roster data for duplicates and data integrity"""
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
                issues.append(f"⚠️ Duplicate entries found for: {', '.join(duplicate_names)}")
    
    return issues

def get_tester_languages(row):
    """Extract all languages for a tester"""
    languages = set()
    for col in ['language_1', 'language_2', 'language_3', 'language_4']:
        if col in row.index:
            lang = normalize_language(row[col])
            if lang:
                languages.add(lang)
    return languages

def get_available_testers(language_requirements, match_all=False):
    """Get testers who match language requirements"""
    if st.session_state.roster_data is None:
        return []
    
    available_testers = []
    df = st.session_state.roster_data
    
    df = df.fillna('')
    
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
            for task_id, task_info in st.session_state.tasks.items():
                if task_id not in [t['task_id'] for t in st.session_state.completed_tasks]:
                    if full_name in st.session_state.assignments.get(task_id, []):
                        task_name = task_info['name']
                        assigned_task_names[task_name] = task_info['priority']
            
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

def generate_comprehensive_report():
    """Generate an ultra-comprehensive analytics report with all suggested metrics"""
    
    # Calculate all base metrics first
    total_tasks = len(st.session_state.tasks)
    active_tasks = [(tid, tinfo) for tid, tinfo in st.session_state.tasks.items()
                    if tid not in [ct['task_id'] for ct in st.session_state.completed_tasks]]
    completed_tasks = st.session_state.completed_tasks
    now = datetime.now()
    
    # Initialize variables with default values
    avg_completion = 0
    median_completion = 0
    fastest = 0
    slowest = 0
    week_velocity = 0
    month_velocity = 0
    utilization_rate = 0
    total_testers = 0
    assigned_testers = set()
    tester_workload = defaultdict(int)
    avg_tasks = 0
    std_dev = 0
    overloaded = []
    underutilized = []
    critical_languages = []
    language_coverage = defaultdict(set)
    resource_gap = 0
    projected_monthly = 0
    projected_need = 0
    
    # Initialize HTML with comprehensive styling
    html = []
    html.append("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Comprehensive Task Assignment Analytics Report</title>
        <meta charset="UTF-8">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 1400px;
                margin: 0 auto;
                background: white;
                border-radius: 20px;
                box-shadow: 0 25px 50px rgba(0,0,0,0.2);
                overflow: hidden;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 50px;
                text-align: center;
            }
            .header h1 {
                font-size: 3em;
                font-weight: 300;
                margin-bottom: 20px;
            }
            .header .subtitle {
                font-size: 1.2em;
                opacity: 0.95;
            }
            .content {
                padding: 50px;
            }
            h2 {
                color: #667eea;
                border-bottom: 3px solid #667eea;
                padding-bottom: 15px;
                margin: 40px 0 30px 0;
                font-size: 2em;
                font-weight: 400;
            }
            h3 {
                color: #764ba2;
                margin: 30px 0 20px 0;
                font-size: 1.5em;
                font-weight: 400;
            }
            .metric-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 25px;
                margin: 30px 0;
            }
            .metric-card {
                background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
                padding: 25px;
                border-radius: 15px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                transition: transform 0.3s ease;
            }
            .metric-card:hover {
                transform: translateY(-5px);
                box-shadow: 0 10px 25px rgba(0,0,0,0.15);
            }
            .metric-card .value {
                font-size: 2.5em;
                font-weight: bold;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: 10px;
            }
            .metric-card .label {
                color: #666;
                font-size: 1em;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            .metric-card .sublabel {
                color: #999;
                font-size: 0.85em;
                margin-top: 5px;
            }
            .alert {
                padding: 20px;
                border-radius: 10px;
                margin: 25px 0;
                position: relative;
                padding-left: 60px;
            }
            .alert::before {
                position: absolute;
                left: 20px;
                top: 50%;
                transform: translateY(-50%);
                font-size: 24px;
            }
            .alert-warning {
                background: #fff3cd;
                border-left: 5px solid #ffc107;
                color: #856404;
            }
            .alert-warning::before { content: "⚠️"; }
            .alert-danger {
                background: #f8d7da;
                border-left: 5px solid #dc3545;
                color: #721c24;
            }
            .alert-danger::before { content: "🔴"; }
            .alert-success {
                background: #d4edda;
                border-left: 5px solid #28a745;
                color: #155724;
            }
            .alert-success::before { content: "✅"; }
            .alert-info {
                background: #d1ecf1;
                border-left: 5px solid #17a2b8;
                color: #0c5460;
            }
            .alert-info::before { content: "ℹ️"; }
            table {
                width: 100%;
                border-collapse: collapse;
                margin: 25px 0;
                box-shadow: 0 5px 15px rgba(0,0,0,0.08);
                border-radius: 10px;
                overflow: hidden;
            }
            th {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 15px;
                text-align: left;
                font-weight: 500;
                text-transform: uppercase;
                letter-spacing: 1px;
                font-size: 0.9em;
            }
            td {
                padding: 15px;
                border-bottom: 1px solid #e0e0e0;
                color: #333;
            }
            tr:hover {
                background: #f8f9fa;
            }
            .progress-bar {
                width: 100%;
                height: 40px;
                background: #e0e0e0;
                border-radius: 20px;
                overflow: hidden;
                margin: 15px 0;
                box-shadow: inset 0 2px 4px rgba(0,0,0,0.1);
            }
            .progress-fill {
                height: 100%;
                background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
                display: flex;
                align-items: center;
                padding-left: 15px;
                color: white;
                font-weight: 500;
            }
            .recommendation {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                border-radius: 15px;
                margin: 30px 0;
                box-shadow: 0 10px 30px rgba(102, 126, 234, 0.3);
            }
            .recommendation h4 {
                color: white;
                margin-top: 0;
                font-size: 1.5em;
                margin-bottom: 20px;
            }
            .recommendation ol {
                margin: 20px 0;
                padding-left: 25px;
            }
            .recommendation li {
                margin: 12px 0;
                line-height: 1.6;
            }
            .tag {
                display: inline-block;
                padding: 5px 12px;
                border-radius: 20px;
                font-size: 0.85em;
                margin: 3px;
                font-weight: 500;
            }
            .tag-critical { background: #dc3545; color: white; }
            .tag-high { background: #fd7e14; color: white; }
            .tag-medium { background: #ffc107; color: #333; }
            .tag-low { background: #28a745; color: white; }
            .executive-summary {
                background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
                padding: 40px;
                border-radius: 15px;
                margin: 30px 0;
            }
            .footer {
                background: #f8f9fa;
                padding: 30px;
                text-align: center;
                color: #666;
                font-size: 0.9em;
                border-top: 1px solid #e0e0e0;
            }
            .chart-container {
                margin: 35px 0;
                padding: 30px;
                background: #f8f9fa;
                border-radius: 15px;
            }
        </style>
    </head>
    <body>
    <div class="container">
    """)
    
    # Header
    html.append(f"""
    <div class="header">
        <h1>📊 Comprehensive Task Assignment Analytics Report</h1>
        <div class="subtitle">
            Generated on {now.strftime('%B %d, %Y at %I:%M %p')}<br>
            Report prepared by: {st.session_state.current_user}<br>
            Report Period: {(now - timedelta(days=30)).strftime('%B %d, %Y')} to {now.strftime('%B %d, %Y')}
        </div>
    </div>
    <div class="content">
    """)
    
    # 1. EXECUTIVE SUMMARY
    completion_rate = (len(completed_tasks) / total_tasks * 100) if total_tasks > 0 else 0
    
    html.append("""
    <div class="executive-summary">
        <h2 style="margin-top: 0;">📈 Executive Summary</h2>
    """)
    
    html.append(f"""
    <div class="metric-grid">
        <div class="metric-card">
            <div class="value">{total_tasks}</div>
            <div class="label">Total Tasks</div>
            <div class="sublabel">All time</div>
        </div>
        <div class="metric-card">
            <div class="value">{len(active_tasks)}</div>
            <div class="label">Active Tasks</div>
            <div class="sublabel">Currently in progress</div>
        </div>
        <div class="metric-card">
            <div class="value">{len(completed_tasks)}</div>
            <div class="label">Completed</div>
            <div class="sublabel">Successfully finished</div>
        </div>
        <div class="metric-card">
            <div class="value">{completion_rate:.1f}%</div>
            <div class="label">Completion Rate</div>
            <div class="sublabel">Overall efficiency</div>
        </div>
    </div>
    </div>
    """)
    
    # 2. PERFORMANCE METRICS
    html.append("<h2>⚡ Performance Metrics & Velocity Analysis</h2>")
    
    completion_times = []
    for comp_task in completed_tasks:
        task_id = comp_task['task_id']
        if task_id in st.session_state.tasks:
            task_info = st.session_state.tasks[task_id]
            try:
                created = datetime.fromisoformat(task_info['created_at'])
                completed = datetime.fromisoformat(comp_task['completed_at'])
                duration = (completed - created).total_seconds() / 3600
                completion_times.append(duration)
            except:
                pass
    
    if completion_times:
        avg_completion = statistics.mean(completion_times)
        median_completion = statistics.median(completion_times)
        fastest = min(completion_times)
        slowest = max(completion_times)
        
        html.append(f"""
        <div class="metric-grid">
            <div class="metric-card">
                <div class="value">{avg_completion:.1f}h</div>
                <div class="label">Average Time</div>
                <div class="sublabel">Mean completion time</div>
            </div>
            <div class="metric-card">
                <div class="value">{median_completion:.1f}h</div>
                <div class="label">Median Time</div>
                <div class="sublabel">Typical duration</div>
            </div>
            <div class="metric-card">
                <div class="value">{fastest:.1f}h</div>
                <div class="label">Fastest</div>
                <div class="sublabel">Best performance</div>
            </div>
            <div class="metric-card">
                <div class="value">{slowest:.1f}h</div>
                <div class="label">Slowest</div>
                <div class="sublabel">Longest duration</div>
            </div>
        </div>
        """)
    
    # 3. RESOURCE UTILIZATION
    html.append("<h2>👥 Resource Utilization & Capacity Analysis</h2>")
    
    if st.session_state.roster_data is not None:
        total_testers = len(st.session_state.roster_data)
        
        for task_id, assignees in st.session_state.assignments.items():
            if task_id not in [t['task_id'] for t in completed_tasks]:
                for tester in assignees:
                    assigned_testers.add(tester)
                    tester_workload[tester] += 1
        
        utilization_rate = (len(assigned_testers) / total_testers * 100) if total_testers > 0 else 0
        
        html.append(f"""
        <div class="metric-grid">
            <div class="metric-card">
                <div class="value">{total_testers}</div>
                <div class="label">Total Capacity</div>
                <div class="sublabel">Available testers</div>
            </div>
            <div class="metric-card">
                <div class="value">{len(assigned_testers)}</div>
                <div class="label">Utilized</div>
                <div class="sublabel">Currently working</div>
            </div>
            <div class="metric-card">
                <div class="value">{utilization_rate:.1f}%</div>
                <div class="label">Utilization Rate</div>
                <div class="sublabel">Resource efficiency</div>
            </div>
            <div class="metric-card">
                <div class="value">{total_testers - len(assigned_testers)}</div>
                <div class="label">Available</div>
                <div class="sublabel">Ready for assignment</div>
            </div>
        </div>
        """)
    
    # 4. WORKLOAD DISTRIBUTION
    html.append("<h2>⚖️ Workload Distribution & Balance Analysis</h2>")
    
    if tester_workload:
        workload_values = list(tester_workload.values())
        avg_tasks = statistics.mean(workload_values)
        std_dev = statistics.stdev(workload_values) if len(workload_values) > 1 else 0
        max_tasks = max(workload_values)
        min_tasks = min(workload_values)
        
        html.append(f"""
        <div class="metric-grid">
            <div class="metric-card">
                <div class="value">{avg_tasks:.1f}</div>
                <div class="label">Average Load</div>
                <div class="sublabel">Tasks per tester</div>
            </div>
            <div class="metric-card">
                <div class="value">{std_dev:.2f}</div>
                <div class="label">Std Deviation</div>
                <div class="sublabel">{"High variance!" if std_dev > avg_tasks * 0.5 else "Good balance"}</div>
            </div>
            <div class="metric-card">
                <div class="value">{max_tasks}</div>
                <div class="label">Maximum Load</div>
                <div class="sublabel">Highest assignment</div>
            </div>
            <div class="metric-card">
                <div class="value">{min_tasks}</div>
                <div class="label">Minimum Load</div>
                <div class="sublabel">Lowest assignment</div>
            </div>
        </div>
        """)
        
        overloaded = [(t, c) for t, c in tester_workload.items() if c > avg_tasks + std_dev]
        underutilized = [(t, c) for t, c in tester_workload.items() if avg_tasks - std_dev > 0 and c < avg_tasks - std_dev]
    
    # 5. LANGUAGE ANALYTICS
    html.append("<h2>🌍 Language Coverage & Demand Analysis</h2>")
    
    language_demand = Counter()
    
    for task_info in st.session_state.tasks.values():
        langs = task_info.get('languages', [])
        for lang in langs:
            language_demand[lang] += 1
    
    if st.session_state.roster_data is not None:
        for _, row in st.session_state.roster_data.iterrows():
            full_name = f"{row['first_name']} {row['last_name']}".strip()
            for lang in get_tester_languages(row):
                if lang:
                    language_coverage[lang].add(full_name)
        
        html.append("<h3>Language Supply vs Demand Matrix</h3>")
        html.append("""
        <table>
            <tr>
                <th>Language</th>
                <th>Tasks Requiring</th>
                <th>Testers Available</th>
                <th>Risk Level</th>
            </tr>
        """)
        
        all_languages = set(list(language_demand.keys()) + list(language_coverage.keys()))
        
        for lang in sorted(all_languages):
            demand = language_demand.get(lang, 0)
            supply = len(language_coverage.get(lang, set()))
            
            if supply == 0:
                risk = '<span class="tag tag-critical">CRITICAL</span>'
            elif supply == 1:
                risk = '<span class="tag tag-high">HIGH</span>'
            elif supply <= 2:
                risk = '<span class="tag tag-medium">MEDIUM</span>'
            else:
                risk = '<span class="tag tag-low">LOW</span>'
            
            html.append(f"""
            <tr>
                <td><strong>{lang}</strong></td>
                <td>{demand}</td>
                <td>{supply}</td>
                <td>{risk}</td>
            </tr>
            """)
        
        html.append("</table>")
        
        critical_languages = [lang for lang, testers in language_coverage.items()
                            if len(testers) <= 1 and language_demand.get(lang, 0) > 0]
    
    # 6. PRIORITY DISTRIBUTION
    html.append("<h2>🎯 Priority Distribution</h2>")
    
    priority_count = Counter()
    for task_info in st.session_state.tasks.values():
        priority_count[task_info['priority']] += 1
    
    html.append("<div class='chart-container'>")
    for priority in ["P0 - Critical", "P1 - High", "P2 - Medium", "P3 - Low"]:
        count = priority_count.get(priority, 0)
        percentage = (count / total_tasks * 100) if total_tasks > 0 else 0
        
        html.append(f"""
        <div style="margin: 20px 0;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                <strong>{priority}</strong>
                <span>{count} tasks ({percentage:.1f}%)</span>
            </div>
            <div class="progress-bar">
                <div class="progress-fill" style="width: {percentage}%;">
                    {count}
                </div>
            </div>
        </div>
        """)
    html.append("</div>")
    
    # 7. RECOMMENDATIONS
    html.append("""
    <div class="recommendation">
        <h4>🎯 Top Actionable Recommendations</h4>
        <ol>
    """)
    
    recommendations = []
    
    if overloaded:
        recommendations.append(f"Redistribute tasks from {overloaded[0][0]} ({overloaded[0][1]} tasks)")
    
    if critical_languages:
        recommendations.append(f"Address language gap for {critical_languages[0]}")
    
    if utilization_rate < 50:
        recommendations.append(f"Improve resource utilization (currently {utilization_rate:.1f}%)")
    
    if completion_rate < 60:
        recommendations.append(f"Focus on task completion - rate is only {completion_rate:.1f}%")
    
    recommendations.extend([
        "Implement weekly task review meetings",
        "Create language skill matrix",
        "Establish SLAs for each priority level"
    ])
    
    for rec in recommendations[:7]:
        html.append(f"<li>{rec}</li>")
    
    html.append("""
        </ol>
    </div>
    """)
    
    # Footer
    html.append("""
    </div>
    <div class="footer">
        <p>
        <strong>Task Assignment Analytics System v3.2</strong><br>
        Report Generated: """ + now.strftime('%Y-%m-%d %H:%M:%S') + """<br>
        This report contains confidential information.
        </p>
    </div>
    </div>
    </body>
    </html>
    """)
    
    return ''.join(html)

def dismiss_conflict_message():
    """Dismiss the conflict message without losing data"""
    st.session_state.show_conflict_message = False
    st.session_state.last_conflict_message = None

# Main UI
st.title("📋 Team Task Assignment Tool")

# User identification with persistence
if st.session_state.current_user is None:
    st.warning("Please enter your name to continue")
    user_name = st.text_input("Your Name (Team Lead)", placeholder="e.g., John Smith")
    if user_name:
        st.session_state.current_user = user_name
        st.query_params['user'] = user_name
        st.rerun()
else:
    st.caption(f"👤 Current User: {st.session_state.current_user}")
    if st.button("Switch User", key="switch_user"):
        st.session_state.current_user = None
        st.query_params.clear()
        st.session_state.last_conflict_message = None
        st.session_state.show_conflict_message = True
        st.rerun()

# Only show main interface if user is identified
if st.session_state.current_user:
    # Show conflict message at the TOP (if exists)
    if st.session_state.last_conflict_message and st.session_state.show_conflict_message:
        with st.container():
            col1, col2 = st.columns([10, 1])
            with col1:
                st.warning("⚠️ **Previous Task Creation - Assignment Conflicts Detected:**")
                for conflict in st.session_state.last_conflict_message['conflicts']:
                    st.write(f"  • {conflict}")
                st.info(f"Task '{st.session_state.last_conflict_message['task_name']}' was created with conflicts. Consider task priority ({st.session_state.last_conflict_message['priority']}) when resolving.")
            with col2:
                if st.button("✖", key="dismiss_conflict_top", help="Dismiss this message"):
                    dismiss_conflict_message()
                    st.rerun()
    
    # Sidebar
    with st.sidebar:
        st.header("📊 Team Roster")
        
        st.info("💡 **Tip:** Export your file from Numbers app as Excel (.xlsx) or CSV for best compatibility")
        
        uploaded_file = st.file_uploader(
            "Upload team roster (Excel/CSV)",
            type=['xlsx', 'csv'],
            help="Upload the Numbers sheet with tester information."
        )
        
        if uploaded_file is not None:
            try:
                if uploaded_file.name.endswith('.csv'):
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file, engine='openpyxl')
                
                df = normalize_column_names(df)
                missing_columns = validate_required_columns(df)
                
                if missing_columns:
                    st.error(f"❌ Missing required columns: {', '.join(missing_columns)}")
                else:
                    df = df[(df['first_name'].notna()) & (df['first_name'] != '') &
                           (df['last_name'].notna()) & (df['last_name'] != '')]
                    
                    st.session_state.roster_data = df
                    issues = validate_roster_data(df)
                    
                    if issues:
                        st.warning("Data Validation Issues:")
                        for issue in issues:
                            st.write(issue)
                    
                    st.success(f"✅ Loaded {len(df)} team members")
                    
                    with st.expander("Team Summary"):
                        all_languages = set()
                        for _, row in df.iterrows():
                            all_languages.update(get_tester_languages(row))
                        
                        all_languages.discard(None)
                        
                        st.write(f"**Total Members:** {len(df)}")
                        if all_languages:
                            st.write(f"**Languages:** {', '.join(sorted(all_languages))}")
                        
            except Exception as e:
                st.error(f"Error loading file: {str(e)}")
        
        # Show current tasks summary
        if st.session_state.tasks:
            st.divider()
            st.header("📋 Active Tasks")
            
            active_task_ids = [tid for tid in st.session_state.tasks
                             if tid not in [t['task_id'] for t in st.session_state.completed_tasks]]
            
            st.metric("Active Tasks", len(active_task_ids))
            st.metric("Total Tasks", len(st.session_state.tasks))
            
            for task_id in active_task_ids:
                task_info = st.session_state.tasks[task_id]
                with st.expander(f"{task_info['name']} ({task_info['priority']})", expanded=False):
                    assignees = st.session_state.assignments.get(task_id, [])
                    st.write(f"**Assigned:** {len(assignees)} testers")
                    if assignees:
                        for assignee in assignees:
                            st.write(f"• {assignee}")
                    
                    if task_id in st.session_state.assignment_locks:
                        lock_info = st.session_state.assignment_locks[task_id]
                        st.warning(f"🔒 Being edited by {lock_info['user']}")
        
        # Analytics Report Generation
        if st.session_state.tasks:
            st.divider()
            st.header("📊 Analytics Report")
            
            if st.button("Generate Report", use_container_width=True, type="primary"):
                report = generate_comprehensive_report()
                
                st.download_button(
                    label="📥 Download Report (HTML)",
                    data=report,
                    file_name=f"task_analytics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
                    mime="text/html",
                    use_container_width=True,
                    help="Open in any web browser"
                )
    
    # Main content area
    if st.session_state.roster_data is None:
        st.info("👈 Please upload the team roster in the sidebar to get started")
    else:
        # Create tabs
        tab1, tab2, tab3 = st.tabs(["📝 Create Task", "👥 Manage Assignments", "✅ Task Status"])
        
        # Tab 1: Create Task
        with tab1:
            st.header("Create New Task")
            
            col1, col2 = st.columns(2)
            
            with col1:
                task_name = st.text_input("Task Name", placeholder="e.g., Siri Validation - iOS 18.3")
                
                priority = st.selectbox(
                    "Priority Level",
                    options=["P0 - Critical", "P1 - High", "P2 - Medium", "P3 - Low"],
                    help="P0 takes precedence over all other tasks. Can be changed later."
                )
            
            with col2:
                all_languages = set()
                for _, row in st.session_state.roster_data.iterrows():
                    all_languages.update(get_tester_languages(row))
                
                all_languages = {lang for lang in all_languages if lang}
                
                if all_languages:
                    language_requirements = st.multiselect(
                        "Required Languages",
                        options=sorted(all_languages),
                        help="Select languages required. Full language names are shown."
                    )
                    
                    match_all_languages = st.checkbox(
                        "Require ALL languages",
                        value=False,
                        help="If checked, only show testers who speak ALL selected languages."
                    )
                else:
                    st.warning("No languages found in roster data")
                    language_requirements = []
            
            if task_name and language_requirements:
                st.subheader("📋 Available Testers")
                
                if match_all_languages:
                    st.info(f"Showing testers who speak ALL of: {', '.join(language_requirements)}")
                else:
                    st.info(f"Showing testers who speak AT LEAST ONE of: {', '.join(language_requirements)}")
                
                available_testers = get_available_testers(language_requirements, match_all=match_all_languages)
                
                if available_testers:
                    st.write(f"Found {len(available_testers)} testers matching criteria:")
                    
                    fully_available = [t for t in available_testers if t['is_available']]
                    if fully_available:
                        st.success(f"✨ {len(fully_available)} testers are fully available (recommended)")
                    
                    selection_container = st.container()
                    
                    col_b1, col_b2, col_b3 = st.columns(3)
                    with col_b1:
                        if st.button("✅ Select All Available", key="btn_select_available", use_container_width=True):
                            for i, t in enumerate(available_testers):
                                if t['is_available']:
                                    st.session_state[f"check_{i}"] = True
                                else:
                                    st.session_state[f"check_{i}"] = False
                            st.rerun()
                    
                    with col_b2:
                        if st.button("☑️ Select All", key="btn_select_all", use_container_width=True):
                            for i in range(len(available_testers)):
                                st.session_state[f"check_{i}"] = True
                            st.rerun()
                    
                    with col_b3:
                        if st.button("❌ Clear Selection", key="btn_clear", use_container_width=True):
                            for i in range(len(available_testers)):
                                st.session_state[f"check_{i}"] = False
                            st.rerun()
                    
                    st.divider()
                    
                    col1, col2, col3, col4 = st.columns([3, 1, 2, 3])
                    with col1:
                        st.write("**Tester**")
                    with col2:
                        st.write("**Status**")
                    with col3:
                        st.write("**Matching Languages**")
                    with col4:
                        st.write("**Current Assignments**")
                    
                    selected_testers = []
                    
                    for i, tester in enumerate(available_testers):
                        col1, col2, col3, col4 = st.columns([3, 1, 2, 3])
                        
                        with col1:
                            checkbox_key = f"check_{i}"
                            if checkbox_key not in st.session_state:
                                st.session_state[checkbox_key] = tester['is_available']
                            
                            if checkbox_key in st.session_state:
                                is_selected = st.checkbox(
                                    tester['name'],
                                    key=checkbox_key
                                )
                            else:
                                is_selected = st.checkbox(
                                    tester['name'],
                                    key=checkbox_key,
                                    value=tester['is_available']
                                )
                            
                            if is_selected:
                                selected_testers.append(tester['name'])
                        
                        with col2:
                            if tester['is_available']:
                                st.write("🟢 Available")
                            else:
                                st.write("🔴 Assigned")
                        
                        with col3:
                            st.write(", ".join(tester['matching_languages']))
                        
                        with col4:
                            if tester['assigned_tasks']:
                                tasks_str = ", ".join([f"{name} ({p})" for name, p in tester['assigned_tasks']])
                                st.write(tasks_str)
                            else:
                                st.write("-")
                    
                    with selection_container:
                        st.metric("Selected Testers", len(selected_testers))
                    
                    st.divider()
                    
                    if st.button("🚀 Create Task", type="primary", use_container_width=True):
                        if selected_testers:
                            existing_task_names = [t['name'] for t in st.session_state.tasks.values()]
                            if task_name in existing_task_names:
                                st.error(f"❌ A task with the name '{task_name}' already exists.")
                            else:
                                task_id = f"TASK_{st.session_state.task_counter:03d}"
                                st.session_state.task_counter += 1
                                
                                st.session_state.tasks[task_id] = {
                                    'name': task_name,
                                    'priority': priority,
                                    'languages': language_requirements,
                                    'created_at': datetime.now().isoformat(),
                                    'created_by': st.session_state.current_user
                                }
                                
                                st.session_state.assignments[task_id] = list(set(selected_testers))
                                
                                conflicts = []
                                for tester_name in selected_testers:
                                    tester_info = next((t for t in available_testers if t['name'] == tester_name), None)
                                    if tester_info and not tester_info['is_available']:
                                        existing_tasks = [f"{name} ({p})" for name, p in tester_info['assigned_tasks']]
                                        conflicts.append(f"{tester_name} is already assigned to: {', '.join(existing_tasks)}")
                                
                                if conflicts:
                                    st.session_state.last_conflict_message = {
                                        'task_name': task_name,
                                        'priority': priority,
                                        'conflicts': conflicts
                                    }
                                    st.session_state.show_conflict_message = True
                                else:
                                    st.session_state.last_conflict_message = None
                                    st.session_state.show_conflict_message = False
                                    st.success(f"✅ Task '{task_name}' created successfully!")
                                
                                for i in range(len(available_testers)):
                                    if f"check_{i}" in st.session_state:
                                        del st.session_state[f"check_{i}"]
                                
                                st.rerun()
                        else:
                            st.error("Please select at least one tester")
                else:
                    if match_all_languages:
                        st.warning(f"No testers found with ALL required languages: {', '.join(language_requirements)}")
                    else:
                        st.warning(f"No testers found with ANY of the required languages: {', '.join(language_requirements)}")
            
            if st.session_state.last_conflict_message and st.session_state.show_conflict_message:
                st.divider()
                conflict_container = st.container()
                with conflict_container:
                    col1, col2 = st.columns([10, 1])
                    with col1:
                        st.warning("⚠️ **Previous Task Creation - Assignment Conflicts Detected:**")
                        for conflict in st.session_state.last_conflict_message['conflicts']:
                            st.write(f"  • {conflict}")
                        st.info(f"Task '{st.session_state.last_conflict_message['task_name']}' was created with conflicts.")
                    with col2:
                        if st.button("✖", key="dismiss_conflict_bottom", help="Dismiss this message"):
                            dismiss_conflict_message()
                            st.rerun()
        
        # Tab 2: Manage Assignments
        with tab2:
            st.header("Manage Task Assignments")
            
            active_tasks = [(tid, tinfo) for tid, tinfo in st.session_state.tasks.items()
                           if tid not in [t['task_id'] for t in st.session_state.completed_tasks]]
            
            if active_tasks:
                priority_order = {"P0 - Critical": 0, "P1 - High": 1, "P2 - Medium": 2, "P3 - Low": 3}
                active_tasks.sort(key=lambda x: priority_order.get(x[1]['priority'], 4))
                
                for task_id, task_info in active_tasks:
                    is_locked = False
                    lock_user = None
                    if task_id in st.session_state.assignment_locks:
                        lock_info = st.session_state.assignment_locks[task_id]
                        if lock_info['user'] != st.session_state.current_user:
                            is_locked = True
                            lock_user = lock_info['user']
                    
                    with st.expander(f"📌 {task_info['name']} - {task_info['priority']}", expanded=False):
                        if is_locked:
                            st.warning(f"🔒 This task is currently being edited by {lock_user}")
                        
                        col1, col2 = st.columns([3, 1])
                        
                        with col1:
                            st.write(f"**Created by:** {task_info.get('created_by', 'Unknown')}")
                            st.write(f"**Created at:** {task_info.get('created_at', 'Unknown')[:10]}")
                            st.write(f"**Required Languages:** {', '.join(task_info['languages'])}")
                            
                            current_assignees = st.session_state.assignments.get(task_id, [])
                            st.write(f"**Currently Assigned ({len(current_assignees)}):** {', '.join(current_assignees) if current_assignees else 'None'}")
                        
                        with col2:
                            if not is_locked:
                                new_priority = st.selectbox(
                                    "Change Priority",
                                    options=["P0 - Critical", "P1 - High", "P2 - Medium", "P3 - Low"],
                                    index=["P0 - Critical", "P1 - High", "P2 - Medium", "P3 - Low"].index(task_info['priority']),
                                    key=f"priority_{task_id}"
                                )
                                if new_priority != task_info['priority']:
                                    if st.button(f"Update", key=f"update_priority_{task_id}"):
                                        st.session_state.tasks[task_id]['priority'] = new_priority
                                        st.success(f"Priority updated!")
                                        st.rerun()
                                
                                if st.button(f"✅ Complete Task", key=f"complete_{task_id}", type="primary"):
                                    st.session_state.completed_tasks.append({
                                        'task_id': task_id,
                                        'completed_by': st.session_state.current_user,
                                        'completed_at': datetime.now().isoformat()
                                    })
                                    release_assignment_lock(task_id, st.session_state.current_user)
                                    st.success(f"Task completed!")
                                    st.rerun()
                        
                        if not is_locked:
                            st.divider()
                            
                            can_edit, lock_holder = acquire_assignment_lock(task_id, st.session_state.current_user)
                            
                            if can_edit:
                                st.subheader("Modify Assignments")
                                
                                available_testers = get_available_testers(task_info['languages'], match_all=False)
                                
                                new_assignees = st.multiselect(
                                    "Select testers for this task",
                                    options=[t['name'] for t in available_testers],
                                    default=current_assignees,
                                    key=f"reassign_{task_id}"
                                )
                                
                                col1, col2, col3 = st.columns(3)
                                with col1:
                                    if st.button(f"💾 Save Changes", key=f"save_{task_id}"):
                                        st.session_state.assignments[task_id] = new_assignees
                                        release_assignment_lock(task_id, st.session_state.current_user)
                                        st.success("Assignments updated!")
                                        st.rerun()
                                
                                with col2:
                                    if st.button(f"Cancel", key=f"cancel_{task_id}"):
                                        release_assignment_lock(task_id, st.session_state.current_user)
                                        st.rerun()
                                
                                with col3:
                                    if st.button(f"🗑️ Delete Task", key=f"delete_{task_id}"):
                                        del st.session_state.tasks[task_id]
                                        if task_id in st.session_state.assignments:
                                            del st.session_state.assignments[task_id]
                                        release_assignment_lock(task_id, st.session_state.current_user)
                                        st.success("Task deleted!")
                                        st.rerun()
                            else:
                                st.info(f"Task is being edited by {lock_holder}")
            else:
                st.info("No active tasks. Create a new task in the 'Create Task' tab.")
        
        # Tab 3: Task Status
        with tab3:
            st.header("Task Status Overview")
            
            col1, col2, col3, col4 = st.columns(4)
            
            active_task_count = len([t for t in st.session_state.tasks
                                    if t not in [ct['task_id'] for ct in st.session_state.completed_tasks]])
            completed_task_count = len(st.session_state.completed_tasks)
            
            with col1:
                st.metric("Active Tasks", active_task_count)
            with col2:
                st.metric("Completed Tasks", completed_task_count)
            with col3:
                st.metric("Total Tasks", active_task_count + completed_task_count)
            with col4:
                if st.session_state.roster_data is not None:
                    st.metric("Total Testers", len(st.session_state.roster_data))
            
            st.divider()
            
            if st.session_state.roster_data is not None:
                all_testers = set()
                assigned_testers = set()
                
                for _, row in st.session_state.roster_data.iterrows():
                    full_name = f"{row['first_name']} {row['last_name']}".strip()
                    if full_name and full_name != ' ':
                        all_testers.add(full_name)
                        
                        for task_id in st.session_state.tasks:
                            if task_id not in [t['task_id'] for t in st.session_state.completed_tasks]:
                                if full_name in st.session_state.assignments.get(task_id, []):
                                    assigned_testers.add(full_name)
                
                unassigned = all_testers - assigned_testers
                
                if unassigned:
                    with st.expander(f"⚠️ Unassigned Testers ({len(unassigned)} testers)", expanded=False):
                        st.info("These testers are currently not assigned to any active task and are available for new assignments:")
                        
                        unassigned_list = sorted(unassigned)
                        cols = st.columns(3)
                        for i, tester in enumerate(unassigned_list):
                            with cols[i % 3]:
                                st.write(f"• {tester}")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("🔴 Active Tasks")
                active_tasks = [(tid, tinfo) for tid, tinfo in st.session_state.tasks.items()
                              if tid not in [t['task_id'] for t in st.session_state.completed_tasks]]
                
                if active_tasks:
                    priority_order = {"P0 - Critical": 0, "P1 - High": 1, "P2 - Medium": 2, "P3 - Low": 3}
                    active_tasks.sort(key=lambda x: priority_order.get(x[1]['priority'], 4))
                    
                    for task_id, task_info in active_tasks:
                        with st.container():
                            assignees = st.session_state.assignments.get(task_id, [])
                            st.write(f"**{task_info['name']}**")
                            st.caption(f"{task_info['priority']} | {len(assignees)} assignees | Created by {task_info.get('created_by', 'Unknown')}")
                            if assignees:
                                with st.expander("View assignees"):
                                    for assignee in assignees:
                                        st.write(f"• {assignee}")
                            st.divider()
                else:
                    st.write("No active tasks")
            
            with col2:
                st.subheader("✅ Completed Tasks")
                if st.session_state.completed_tasks:
                    for task_entry in st.session_state.completed_tasks[-10:]:
                        task_id = task_entry['task_id']
                        if task_id in st.session_state.tasks:
                            task_info = st.session_state.tasks[task_id]
                            st.write(f"**{task_info['name']}**")
                            st.caption(f"Completed by {task_entry['completed_by']} on {task_entry['completed_at'][:10]}")
                            st.divider()
                else:
                    st.write("No completed tasks")

# Footer
st.divider()
st.caption("Team Task Assignment Tool v3.2 | Complete version with comprehensive analytics")
