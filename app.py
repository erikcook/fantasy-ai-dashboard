import streamlit as st
import requests
import pandas as pd
import google.generativeai as genai
import nflreadpy as nfl
import sqlite3
from scipy.stats import percentileofscore
from datetime import datetime, timedelta

# --- SEASON CONFIGURATION ---
CURRENT_SEASON = 2025  # Updated for 2025 NFL Season
FALLBACK_SEASON = 2024  # Fallback if 2025 data not available

# --- NFL SEASON START DATE (2025) ---
NFL_SEASON_START = datetime(2025, 9, 4)  # Thursday, Sept 4, 2025 (Week 1 kickoff)

# --- TEAM ABBREVIATION MAPPING (Sleeper <-> NFLReadPy) ---
TEAM_MAP = {
    'ARI': 'ARZ', 'ARZ': 'ARI',
    'BAL': 'BLT', 'BLT': 'BAL',
    'CLE': 'CLV', 'CLV': 'CLE',
    'GB': 'GBP', 'GBP': 'GB',
    'HOU': 'HST', 'HST': 'HOU',
    'JAX': 'JAC', 'JAC': 'JAX',
    'KC': 'KCC', 'KCC': 'KC',
    'LA': 'LAR', 'LAR': 'LA',
    'LAC': 'LAC',
    'LV': 'LVR', 'LVR': 'LV',
    'NE': 'NEP', 'NEP': 'NE',
    'NO': 'NOR', 'NOR': 'NO',
    'SF': 'SFO', 'SFO': 'SF',
    'TB': 'TBB', 'TBB': 'TB',
    'TEN': 'TEN',
    'WSH': 'WAS', 'WAS': 'WSH'
}

def get_current_week():
    """
    Dynamically detects the current NFL week using Sleeper API with smart date-based fallback.
    "Set It and Forget It" - Works for Week 14, 15, 16, etc. automatically.
    """
    # Try Sleeper API first (most accurate)
    try:
        response = requests.get("https://api.sleeper.app/v1/state/nfl", timeout=5)
        nfl_state = response.json()
        current_week = nfl_state.get('week', None)
        
        if current_week is not None:
            return int(current_week)
    except Exception as e:
        print(f"Sleeper API failed: {e}. Using date-based fallback.")
    
    # Smart Fallback: Calculate week based on season start date
    today = datetime.now()
    
    # If we're before the season starts, return Week 1
    if today < NFL_SEASON_START:
        return 1
    
    # Calculate weeks elapsed since season start
    days_elapsed = (today - NFL_SEASON_START).days
    week_number = (days_elapsed // 7) + 1
    
    # Cap at Week 18 (end of regular season)
    return min(max(week_number, 1), 18)

# --- PAGE CONFIG ---
st.set_page_config(page_title="NEXXT Fantasy", layout="wide", page_icon="🏈")

# --- PREMIUM LIGHT THEME (NEXXT GOLD) ---
st.markdown("""
    <style>
    /* Import Clean System Font */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    /* Base Theme - Pure White */
    .stApp { 
        background-color: #FFFFFF; 
        color: #1E1E1E; 
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
    }
    
    /* Sidebar - Subtle Grey */
    [data-testid="stSidebar"] {
        background-color: #F8F9FA;
    }
    
    /* Premium Button Styling */
    .stButton>button { 
        background-color: #F4D03F; 
        color: #000000; 
        border: none; 
        font-weight: 600; 
        border-radius: 8px;
        padding: 0.5rem 1.5rem;
        transition: all 0.3s ease;
        box-shadow: 0 2px 4px rgba(212, 175, 55, 0.2);
    }
    .stButton>button:hover {
        background-color: #C19B2E;
        box-shadow: 0 4px 8px rgba(212, 175, 55, 0.3);
        transform: translateY(-1px);
    }
    
    /* Premium Card - "Front Office Report" Style */
    .metric-card { 
        background-color: #FFFFFF; 
        padding: 20px; 
        border-radius: 12px; 
        border: 1px solid #E0E0E0;
        border-left: 5px solid #F4D03F; 
        margin-bottom: 15px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        transition: box-shadow 0.3s ease;
    }
    .metric-card:hover {
        box-shadow: 0 6px 12px rgba(0, 0, 0, 0.08);
    }
    
    /* Headers - NEXXT Gold */
    h1, h2, h3 { 
        color: #F4D03F !important; 
        font-weight: 700 !important;
        letter-spacing: -0.5px;
    }
    
    /* Stats Display */
    .big-stat { 
        font-size: 2em; 
        font-weight: 700; 
        color: #F4D03F; 
        line-height: 1.2;
    }
    .sub-stat { 
        font-size: 0.85em; 
        color: #6B6B6B; 
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-top: 4px;
    }
    
    /* Opponent Highlight - Gold Emphasis */
    .highlight-opp { 
        color: #F4D03F; 
        font-weight: 700; 
        font-size: 1.15em; 
    }
    
    /* Tabs Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #F8F9FA;
        color: #1E1E1E;
        border-radius: 8px 8px 0 0;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background-color: #F4D03F;
        color: #000000;
    }
    
    /* Select Boxes - Clean Light Style */
    .stSelectbox > div > div {
        background-color: #F8F9FA;
        border: 1px solid #E0E0E0;
        border-radius: 8px;
    }
    
    /* Markdown Text */
    .stMarkdown {
        color: #1E1E1E;
    }
    
    /* Divider */
    hr {
        border-color: #E0E0E0;
    }
    
    /* Trade Verdict Box Styling */
    .verdict-box {
        padding: 20px;
        border-radius: 12px;
        border-left: 8px solid;
        margin-top: 20px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }
    .grade-A { 
        background-color: #C8E6C9; 
        border-color: #2E7D32; 
        color: #1B5E20; 
    }
    .grade-B { 
        background-color: #E8F5E9; 
        border-color: #4CAF50; 
        color: #1B5E20; 
    }
    .grade-C { 
        background-color: #FFF3E0; 
        border-color: #FF9800; 
        color: #E65100; 
    }
    .grade-D { 
        background-color: #FFCDD2; 
        border-color: #C62828; 
        color: #B71C1C; 
    }
    .grade-F { 
        background-color: #FFCDD2; 
        border-color: #C62828; 
        color: #B71C1C; 
    }
    .verdict-title { 
        font-size: 24px; 
        font-weight: 800; 
        margin-bottom: 5px; 
    }
    .verdict-rationale { 
        font-size: 16px; 
        line-height: 1.5; 
    }
    
    /* Player Mini Card */
    .player-mini-card {
        padding: 12px;
        background-color: #F8F9FA;
        border-radius: 8px;
        border-left: 4px solid #F4D03F;
        margin-bottom: 10px;
    }
    .player-name {
        font-size: 16px;
        font-weight: 700;
        color: #1E1E1E;
        margin-bottom: 4px;
    }
    .player-stats {
        font-size: 14px;
        color: #6B6B6B;
        margin-bottom: 4px;
    }
    .player-advanced {
        font-size: 12px;
        color: #9E9E9E;
    }
    </style>
""", unsafe_allow_html=True)

# --- DATABASE ---
DATABASE_NAME = "fantasy_predictions.db"
def init_db():
    with sqlite3.connect(DATABASE_NAME) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS predictions (id INTEGER PRIMARY KEY, analysis TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
init_db()

# --- SIDEBAR ---
st.sidebar.title("NEXXT Fantasy")
st.sidebar.caption("v9.0: Premium Edition")
league_id = st.sidebar.text_input('League ID', '1217902363445043200')
if "GOOGLE_API_KEY" in st.secrets:
    google_api_key = st.secrets["GOOGLE_API_KEY"]
else:
    google_api_key = st.sidebar.text_input('Google API Key', type='password')

if google_api_key: genai.configure(api_key=google_api_key)

# --- DATA ENGINE (THE ULTIMATE SHORTLIST) ---

@st.cache_data
def load_nfl_data(season=CURRENT_SEASON):
    """Loads massive NFL datasets once and caches them with fallback to previous season."""
    try:
        # Attempt to load current season data
        # 1. Play-by-Play (The Gold Mine)
        pbp = nfl.load_pbp([season]).to_pandas()
        
        # 2. Next Gen Stats (The Secret Sauce)
        ngs_pass = nfl.load_nextgen_stats(seasons=[season], stat_type='passing').to_pandas()
        ngs_rush = nfl.load_nextgen_stats(seasons=[season], stat_type='rushing').to_pandas()
        ngs_rec = nfl.load_nextgen_stats(seasons=[season], stat_type='receiving').to_pandas()
        
        # 3. Player IDs - CRITICAL: Convert BOTH to strings for proper matching
        ids = nfl.load_ff_playerids().to_pandas()
        ids['sleeper_id'] = ids['sleeper_id'].astype(str).str.replace(r'\.0$', '', regex=True)
        ids['gsis_id'] = ids['gsis_id'].astype(str)
        
        # Sanitize: Drop rows with null/nan gsis_id to prevent ghost data
        ids = ids.dropna(subset=['gsis_id'])
        ids = ids[ids['gsis_id'] != 'nan']
        ids = ids[ids['gsis_id'] != 'None']
        
        # Check if data is actually populated (2025 might return empty)
        if pbp.empty:
            raise ValueError(f"{season} data not yet available")
        
        return pbp, ngs_pass, ngs_rush, ngs_rec, ids, season
    except Exception as e:
        # Fallback to previous season if current season fails
        if season == CURRENT_SEASON:
            st.warning(f"⚠️ Using {FALLBACK_SEASON} Data ({CURRENT_SEASON} season data not yet available)")
            try:
                pbp = nfl.load_pbp([FALLBACK_SEASON]).to_pandas()
                ngs_pass = nfl.load_nextgen_stats(seasons=[FALLBACK_SEASON], stat_type='passing').to_pandas()
                ngs_rush = nfl.load_nextgen_stats(seasons=[FALLBACK_SEASON], stat_type='rushing').to_pandas()
                ngs_rec = nfl.load_nextgen_stats(seasons=[FALLBACK_SEASON], stat_type='receiving').to_pandas()
                
                ids = nfl.load_ff_playerids().to_pandas()
                ids['sleeper_id'] = ids['sleeper_id'].astype(str).str.replace(r'\.0$', '', regex=True)
                ids['gsis_id'] = ids['gsis_id'].astype(str)
                
                # Sanitize: Drop rows with null/nan gsis_id to prevent ghost data
                ids = ids.dropna(subset=['gsis_id'])
                ids = ids[ids['gsis_id'] != 'nan']
                ids = ids[ids['gsis_id'] != 'None']
                
                return pbp, ngs_pass, ngs_rush, ngs_rec, ids, FALLBACK_SEASON
            except Exception as fallback_error:
                st.error(f"Data Load Error (both seasons): {fallback_error}")
                return None, None, None, None, None, None
        else:
            st.error(f"Data Load Error: {e}")
            return None, None, None, None, None, None

@st.cache_data
def get_predictive_index(season=CURRENT_SEASON):
    """Calculates the 'Ultimate Shortlist' metrics with position-specific advanced stats."""
    pbp, ngs_pass, ngs_rush, ngs_rec, ids, actual_season = load_nfl_data(season)
    
    # Diagnostic checkpoint
    if pbp is None or pbp.empty:
        st.error("❌ FATAL ERROR: PBP DATA DID NOT LOAD. CHECK TEAM MAP/SEASON.")
        return {}, {}, None

    # === THE PREDICTION WINDOW FILTER (Fixes Week 13 "0.0" Bug) ===
    # Get current week dynamically (works for all weeks automatically)
    current_week = get_current_week()
    
    # CRITICAL: Filter to ONLY completed games (week < current_week)
    # This prevents current week (unplayed) from diluting averages with 0.0 stats
    # Automatically adjusts for Week 14, 15, 16, etc.
    if 'week' in pbp.columns:
        pbp = pbp[pbp['week'] < current_week].copy()
        st.info(f"📊 Prediction Window: Using Weeks 1-{current_week-1} (Completed Games Only) | Current Week: {current_week}")
    
    # Verify filtered data is not empty
    if pbp.empty:
        st.error(f"❌ ERROR: No data found for weeks < {current_week}. Check season data.")
        return {}, {}, None
    
    # Convert PBP player IDs to strings (DO NOT filter globally - only convert type)
    if 'passer_player_id' in pbp.columns:
        pbp['passer_player_id'] = pbp['passer_player_id'].astype(str)
    if 'rusher_player_id' in pbp.columns:
        pbp['rusher_player_id'] = pbp['rusher_player_id'].astype(str)
    if 'receiver_player_id' in pbp.columns:
        pbp['receiver_player_id'] = pbp['receiver_player_id'].astype(str)

    # --- A. DEFENSIVE METRICS (EPA Allowed per Play) ---
    def_stats = pbp.groupby('defteam')['epa'].mean().to_dict()
    
    # --- A2. OFFENSIVE TEAM EFFICIENCY (Team EPA) ---
    team_off_epa = pbp.groupby('posteam')['epa'].mean().to_dict()
    
    # --- B. PLAYER METRICS (Position-Specific) ---
    stats = {}
    
    # Get player positions from IDs
    player_positions = ids.set_index('sleeper_id')['position'].to_dict()
    
    # === PREPARE NGS SEASON AVERAGES (Not Single Week) ===
    ngs_qb_season = {}
    ngs_rb_season = {}
    ngs_wr_season = {}
    
    # NGS Passing - Season Average CPOE
    if not ngs_pass.empty and 'player_gsis_id' in ngs_pass.columns:
        ngs_pass['player_gsis_id'] = ngs_pass['player_gsis_id'].astype(str)
        if 'completion_percentage_above_expectation' in ngs_pass.columns:
            ngs_qb_agg = ngs_pass.groupby('player_gsis_id')['completion_percentage_above_expectation'].mean().to_dict()
            # Map to sleeper_id
            for gsis_id, cpoe in ngs_qb_agg.items():
                sleeper_match = ids[ids['gsis_id'] == gsis_id]
                if not sleeper_match.empty:
                    sid = sleeper_match.iloc[0]['sleeper_id']
                    ngs_qb_season[sid] = cpoe
    
    # NGS Rushing - Season Average RYOE
    if not ngs_rush.empty and 'player_gsis_id' in ngs_rush.columns:
        ngs_rush['player_gsis_id'] = ngs_rush['player_gsis_id'].astype(str)
        if 'rush_yards_over_expected_per_att' in ngs_rush.columns:
            ngs_rb_agg = ngs_rush.groupby('player_gsis_id')['rush_yards_over_expected_per_att'].mean().to_dict()
            # Map to sleeper_id
            for gsis_id, ryoe in ngs_rb_agg.items():
                sleeper_match = ids[ids['gsis_id'] == gsis_id]
                if not sleeper_match.empty:
                    sid = sleeper_match.iloc[0]['sleeper_id']
                    ngs_rb_season[sid] = ryoe
    
    # NGS Receiving - Season Average Cushion
    if not ngs_rec.empty and 'player_gsis_id' in ngs_rec.columns:
        ngs_rec['player_gsis_id'] = ngs_rec['player_gsis_id'].astype(str)
        if 'avg_cushion' in ngs_rec.columns:
            ngs_wr_agg = ngs_rec.groupby('player_gsis_id')['avg_cushion'].mean().to_dict()
            # Map to sleeper_id
            for gsis_id, cushion in ngs_wr_agg.items():
                sleeper_match = ids[ids['gsis_id'] == gsis_id]
                if not sleeper_match.empty:
                    sid = sleeper_match.iloc[0]['sleeper_id']
                    ngs_wr_season[sid] = cushion
    
    # === CALCULATE ALL STATS FROM PBP (THE MANUAL ENGINE) ===
    # Build a comprehensive player stat profile directly from play-by-play data
    per_game_dict = {}
    
    # Prepare ID columns for touchdown tracking
    if 'td_player_id' not in pbp.columns:
        pbp['td_player_id'] = None
    
    # Convert td_player_id to string
    pbp['td_player_id'] = pbp['td_player_id'].astype(str)
    
    # === PASSING STATS ===
    pass_df = pbp[pbp['play_type'] == 'pass'].copy()
    # Filter locally for QB stats only
    qb_plays = pass_df[pass_df['passer_player_id'].notna() & (pass_df['passer_player_id'] != 'nan') & (pass_df['passer_player_id'] != 'None')].copy()
    qb_stats = qb_plays.groupby('passer_player_id').agg(
        games_played=('game_id', 'nunique'),
        pass_yards=('passing_yards', lambda x: x.fillna(0).sum()),
        pass_tds=('pass_touchdown', lambda x: x.fillna(0).sum()),
        interceptions=('interception', lambda x: x.fillna(0).sum())
    ).reset_index()
    qb_stats = qb_stats.merge(ids[['gsis_id', 'sleeper_id']], left_on='passer_player_id', right_on='gsis_id', how='inner')
    
    for _, row in qb_stats.iterrows():
        sid = row['sleeper_id']
        games = max(row['games_played'], 1)
        # QB Fantasy Points (4pt passing TD standard)
        fp = (row['pass_yards'] * 0.04) + (row['pass_tds'] * 4) - (row['interceptions'] * 2)
        per_game_dict[sid] = {
            'games_played': games,
            'fppg': fp / games,
            'targets_per_game': 0,
            'carries_per_game': 0,
            'rz_opps_per_game': 0
        }
    
    # === RUSHING STATS ===
    rush_df = pbp[pbp['play_type'] == 'run'].copy()
    # Filter locally for rusher stats only
    rb_plays = rush_df[rush_df['rusher_player_id'].notna() & (rush_df['rusher_player_id'] != 'nan') & (rush_df['rusher_player_id'] != 'None')].copy()
    rusher_stats = rb_plays.groupby('rusher_player_id').agg(
        games_played=('game_id', 'nunique'),
        rush_yards=('rushing_yards', lambda x: x.fillna(0).sum()),
        rush_tds=('rush_touchdown', lambda x: x.fillna(0).sum()),
        total_carries=('play_id', 'count'),
        rz_carries=('yardline_100', lambda x: (x <= 20).sum()),
        fumbles_lost=('fumble_lost', lambda x: x.fillna(0).sum())
    ).reset_index()
    rusher_stats = rusher_stats.merge(ids[['gsis_id', 'sleeper_id']], left_on='rusher_player_id', right_on='gsis_id', how='inner')
    
    for _, row in rusher_stats.iterrows():
        sid = row['sleeper_id']
        games = max(row['games_played'], 1)
        # Rushing Fantasy Points (PPR)
        fp = (row['rush_yards'] * 0.1) + (row['rush_tds'] * 6) - (row['fumbles_lost'] * 2)
        
        if sid in per_game_dict:
            # Add to existing QB stats
            per_game_dict[sid]['fppg'] += fp / games
            per_game_dict[sid]['carries_per_game'] = row['total_carries'] / games
            per_game_dict[sid]['rz_opps_per_game'] = row['rz_carries'] / games
        else:
            per_game_dict[sid] = {
                'games_played': games,
                'fppg': fp / games,
                'targets_per_game': 0,
                'carries_per_game': row['total_carries'] / games,
                'rz_opps_per_game': row['rz_carries'] / games
            }
    
    # === RECEIVING STATS ===
    # Filter locally for receiver stats only
    rec_df = pass_df[pass_df['receiver_player_id'].notna() & (pass_df['receiver_player_id'] != 'nan') & (pass_df['receiver_player_id'] != 'None')].copy()
    receiver_stats = rec_df.groupby('receiver_player_id').agg(
        games_played=('game_id', 'nunique'),
        receptions=('complete_pass', lambda x: x.fillna(0).sum()),
        rec_yards=('receiving_yards', lambda x: x.fillna(0).sum()),
        rec_tds=('pass_touchdown', lambda x: x.fillna(0).sum()),
        total_targets=('play_id', 'count'),
        rz_targets=('yardline_100', lambda x: (x <= 20).sum()),
        fumbles_lost=('fumble_lost', lambda x: x.fillna(0).sum())
    ).reset_index()
    receiver_stats = receiver_stats.merge(ids[['gsis_id', 'sleeper_id']], left_on='receiver_player_id', right_on='gsis_id', how='inner')
    
    for _, row in receiver_stats.iterrows():
        sid = row['sleeper_id']
        games = max(row['games_played'], 1)
        # Receiving Fantasy Points (PPR: 0.1 per yard, 6 per TD, 1 per reception)
        fp = (row['rec_yards'] * 0.1) + (row['rec_tds'] * 6) + (row['receptions'] * 1.0) - (row['fumbles_lost'] * 2)
        
        if sid in per_game_dict:
            # Add to existing RB stats
            per_game_dict[sid]['fppg'] += fp / games
            per_game_dict[sid]['targets_per_game'] = row['total_targets'] / games
            per_game_dict[sid]['rz_opps_per_game'] += row['rz_targets'] / games
            per_game_dict[sid]['games_played'] = max(per_game_dict[sid]['games_played'], games)
        else:
            # Pure receiver (WR/TE)
            per_game_dict[sid] = {
                'games_played': games,
                'fppg': fp / games,
                'targets_per_game': row['total_targets'] / games,
                'carries_per_game': 0,
                'rz_opps_per_game': row['rz_targets'] / games
            }
    
    # === 1. QB METRICS: EPA/Play + CPOE + PBP-Derived Stats ===
    qb_plays = pbp[(pbp['play_type'] == 'pass') & (pbp['passer_player_id'].notna())]
    qb_epa = qb_plays.groupby('passer_player_id').agg(
        epa_per_play=('epa', 'mean'),
        pass_attempts=('play_id', 'count')
    ).reset_index()
    qb_epa = qb_epa.merge(ids[['gsis_id', 'sleeper_id']], left_on='passer_player_id', right_on='gsis_id', how='inner')
    
    for _, row in qb_epa.iterrows():
        sid = row['sleeper_id']
        pg_data = per_game_dict.get(sid, {'games_played': 1, 'fppg': 0})
        
        # Get team EPA for QB context
        qb_gsis = row['passer_player_id']
        qb_team_match = ids[ids['gsis_id'] == qb_gsis]
        qb_team = qb_team_match.iloc[0]['team'] if not qb_team_match.empty else 'UNK'
        team_epa = team_off_epa.get(qb_team, team_off_epa.get(TEAM_MAP.get(qb_team, qb_team), 0))
        
        stats[sid] = {
            'position': 'QB',
            'epa_per_play': row['epa_per_play'],
            'pass_attempts': row['pass_attempts'],
            'cpoe': ngs_qb_season.get(sid),
            'games_played': pg_data['games_played'],
            'fppg': pg_data['fppg'],
            'team_epa': team_epa
        }
    
    # === 2. RB METRICS: RYOE + RZ Touches ===
    rush_plays = pbp[(pbp['play_type'] == 'run') & (pbp['rusher_player_id'].notna())]
    rb_rush = rush_plays.groupby('rusher_player_id').agg(
        carries=('play_id', 'count'),
        rz_carries=('yardline_100', lambda x: (x <= 20).sum())
    ).reset_index()
    rb_rush = rb_rush.merge(ids[['gsis_id', 'sleeper_id']], left_on='rusher_player_id', right_on='gsis_id', how='inner')
    
    # RB Targets (for total RZ touches)
    pass_plays = pbp[pbp['play_type'] == 'pass']
    rb_targets = pass_plays.groupby('receiver_player_id').agg(
        targets=('play_id', 'count'),
        rz_targets=('yardline_100', lambda x: (x <= 20).sum())
    ).reset_index()
    rb_targets = rb_targets.merge(ids[['gsis_id', 'sleeper_id']], left_on='receiver_player_id', right_on='gsis_id', how='inner')
    
    for _, row in rb_rush.iterrows():
        sid = row['sleeper_id']
        pos = player_positions.get(sid, 'RB')
        if pos == 'RB':
            pg_data = per_game_dict.get(sid, {
                'games_played': 1, 'fppg': 0, 'targets_per_game': 0, 
                'carries_per_game': 0, 'rz_opps_per_game': 0
            })
            
            # Get team EPA for RB context
            rb_gsis = row['rusher_player_id']
            rb_team_match = ids[ids['gsis_id'] == rb_gsis]
            rb_team = rb_team_match.iloc[0]['team'] if not rb_team_match.empty else 'UNK'
            team_epa = team_off_epa.get(rb_team, team_off_epa.get(TEAM_MAP.get(rb_team, rb_team), 0))
            
            stats[sid] = {
                'position': 'RB',
                'carries': row['carries'],
                'rz_touches': row['rz_carries'],
                'ryoe': ngs_rb_season.get(sid),
                'games_played': pg_data['games_played'],
                'fppg': pg_data['fppg'],
                'targets_per_game': pg_data['targets_per_game'],
                'rz_opps_per_game': pg_data['rz_opps_per_game'],
                'ppr_usage_per_game': pg_data['carries_per_game'] + pg_data['targets_per_game'],
                'team_epa': team_epa
            }
    
    # === 3. WR/TE METRICS: WOPR + Target Share + YPRR ===
    team_attempts = pass_plays.groupby('posteam')['play_id'].count().to_dict()
    team_air_yards = pass_plays.groupby('posteam')['air_yards'].sum().fillna(0).to_dict()
    
    # Calculate League Averages (Safety Net)
    avg_team_atts = sum(team_attempts.values()) / max(len(team_attempts), 1)
    avg_team_air = sum(team_air_yards.values()) / max(len(team_air_yards), 1)
    
    wr_targets = pass_plays.groupby('receiver_player_id').agg(
        targets=('play_id', 'count'),
        air_yards=('air_yards', lambda x: x.fillna(0).sum()),
        receiving_yards=('yards_gained', lambda x: x.fillna(0).sum()),
        rz_targets=('yardline_100', lambda x: (x <= 20).sum())
    ).reset_index()
    wr_targets = wr_targets.merge(ids[['gsis_id', 'sleeper_id', 'team']], left_on='receiver_player_id', right_on='gsis_id', how='inner')
    
    for _, row in wr_targets.iterrows():
        sid = row['sleeper_id']
        pos = player_positions.get(sid, 'WR')
        
        if pos in ['WR', 'TE']:
            team = row['team']
            
            # Smart lookup: try original, then mapping
            tm_atts = team_attempts.get(team, 0)
            tm_air = team_air_yards.get(team, 0)
            
            if tm_atts == 0:
                team_key = TEAM_MAP.get(team, team)
                tm_atts = team_attempts.get(team_key, 0)
                tm_air = team_air_yards.get(team_key, 0)
            
            # Final fallback: use league average
            if tm_atts == 0:
                print(f"Warning: Team {team} not found. Using league avg ({avg_team_atts:.1f} atts, {avg_team_air:.1f} air).")
                tm_atts = avg_team_atts
                tm_air = avg_team_air
            
            pg_data = per_game_dict.get(sid, {
                'games_played': 1, 'fppg': 0, 'targets_per_game': 0, 'rz_opps_per_game': 0
            })
            
            # Calculate shares with proper validation
            tgt_share = row['targets'] / tm_atts if tm_atts > 0 else 0
            air_share = row['air_yards'] / tm_air if tm_air > 0 else 0
            
            # Constraint: Target/Air shares cannot exceed 100%
            tgt_share = min(tgt_share, 1.0)
            air_share = min(air_share, 1.0)
            
            # WOPR = 1.5 * target_share + 0.7 * air_yards_share (Fixed Formula)
            wopr = (1.5 * tgt_share) + (0.7 * air_share)
            
            # Guardrail: Clamp to 0-2.5 range
            wopr = max(0, min(wopr, 2.5))
            
            # Get team offensive EPA
            team_epa = team_off_epa.get(team, team_off_epa.get(TEAM_MAP.get(team, team), 0))
            
            # YPRR Approximation (Yards / Team Attempts as proxy)
            yprr = row['receiving_yards'] / tm_atts if tm_atts > 0 else 0
            
            stats[sid] = {
                'position': pos,
                'wopr': wopr,
                'tgt_share': tgt_share,
                'yprr': yprr,
                'rz_opps': row['rz_targets'],
                'avg_cushion': ngs_wr_season.get(sid),
                'games_played': pg_data['games_played'],
                'fppg': pg_data['fppg'],
                'targets_per_game': pg_data['targets_per_game'],
                'rz_opps_per_game': pg_data['rz_opps_per_game'],
                'team_epa': team_epa
            }
    
    # Diagnostic output
    st.sidebar.caption(f"✅ Stats Loaded: {len(stats)} players")
    
    return stats, def_stats, actual_season

@st.cache_data
def get_all_players_data():
    try:
        return requests.get("https://api.sleeper.app/v1/players/nfl").json()
    except: return {}

@st.cache_data
def load_nfl_context():
    """Loads active NFL players only (QB, RB, WR, TE) for dropdowns."""
    all_players = get_all_players_data()
    active_players = {}
    
    for player_id, player_data in all_players.items():
        status = player_data.get('status')
        position = player_data.get('position')
        team = player_data.get('team')
        full_name = player_data.get('full_name', '')
        
        # CRITICAL: Only active players in relevant positions with a team
        if status == 'Active' and position in ['QB', 'RB', 'WR', 'TE']:
            # Filter out free agents
            if team is None or team == 'FA' or team == '':
                continue
            # Filter out players with invalid/missing names
            if not full_name or full_name.strip() == '':
                continue
            # Known inactive/deceased player IDs (add as needed)
            if player_id in ['3662', '3663']:  # Example: Known inactive players
                continue
            active_players[player_id] = player_data
    
    return active_players

@st.cache_data
def load_team_logos():
    """Load team logos from nflreadpy."""
    try:
        teams_df = nfl.load_team_desc().to_pandas()
        team_logos = teams_df.set_index('team_abbr')['team_logo_espn'].to_dict()
        return team_logos
    except:
        return {}

@st.cache_data
def load_nfl_schedule(season=CURRENT_SEASON):
    """Loads NFL schedule for opponent lookup with fallback for future seasons."""
    try:
        schedule = nfl.load_schedules([season]).to_pandas()
        if not schedule.empty:
            return schedule, True  # Return schedule and success flag
        else:
            st.warning(f"⚠️ {season} schedule not yet available in nflreadpy. Opponent lookup disabled.")
            return pd.DataFrame(), False
    except Exception as e:
        st.warning(f"⚠️ {season} schedule not yet available. Opponent lookup disabled. ({e})")
        return pd.DataFrame(), False

def get_current_opponent(team, week, schedule_df, schedule_available):
    """Returns the opponent for a given team and week, or None if schedule unavailable."""
    if not schedule_available or schedule_df.empty or not team:
        return None  # Return None instead of "UNK" when schedule unavailable
    
    # Filter for the specific week
    week_games = schedule_df[schedule_df['week'] == week]
    
    # Find the game where the team is playing
    home_game = week_games[week_games['home_team'] == team]
    away_game = week_games[week_games['away_team'] == team]
    
    if not home_game.empty:
        # Team is home, opponent is away team
        return home_game.iloc[0]['away_team']
    elif not away_game.empty:
        # Team is away, opponent is home team
        return away_game.iloc[0]['home_team']
    else:
        return "BYE"

def get_dynamic_weights(all_player_stats, position):
    """Universal correlation engine - learns optimal weights from actual data."""
    position_data = [p for p in all_player_stats.values() if p.get('position') == position and p.get('games_played', 0) >= 3]
    
    # Define position-specific metrics
    if position == 'QB':
        metrics = ['fppg', 'epa_per_play', 'pass_attempts', 'cpoe']
        fallback = {'epa_per_play': 0.4, 'pass_attempts': 0.3, 'cpoe': 0.3}
    elif position == 'RB':
        metrics = ['fppg', 'ppr_usage_per_game', 'ryoe', 'rz_opps_per_game', 'targets_per_game']
        fallback = {'ppr_usage_per_game': 0.4, 'ryoe': 0.3, 'rz_opps_per_game': 0.2, 'targets_per_game': 0.1}
    elif position in ['WR', 'TE']:
        metrics = ['fppg', 'wopr', 'targets_per_game', 'rz_opps_per_game']
        fallback = {'wopr': 0.5, 'targets_per_game': 0.3, 'rz_opps_per_game': 0.2}
    else:
        return None
    
    # Safety net: too few players
    if len(position_data) < 10:
        return fallback
    
    df = pd.DataFrame(position_data)
    available_metrics = [m for m in metrics if m in df.columns]
    
    if 'fppg' not in available_metrics or len(available_metrics) < 2:
        return fallback
    
    df_clean = df[available_metrics].fillna(0)
    
    # Safety net: no variance
    if df_clean['fppg'].std() == 0:
        return fallback
    
    # Calculate correlations
    corr = df_clean.corr()['fppg'].drop('fppg')
    
    # Clip negative correlations to small positive
    corr = corr.clip(lower=0.01)
    
    # Safety net: flat correlations
    if corr.sum() == 0:
        return fallback
    
    # Normalize to sum to 1.0
    weights = (corr / corr.sum()).to_dict()
    
    # Safety net: enforce minimum usage weight for elite players
    if position == 'RB' and 'targets_per_game' in weights:
        if weights['targets_per_game'] < 0.2:
            weights['targets_per_game'] = 0.35
            # Renormalize
            other_sum = sum(weights[k] for k in weights if k != 'targets_per_game')
            if other_sum > 0:
                scale = 0.65 / other_sum
                for k in weights:
                    if k != 'targets_per_game':
                        weights[k] *= scale
    
    if position in ['WR', 'TE'] and 'wopr' in weights:
        if weights['wopr'] < 0.2:
            weights['wopr'] = 0.35
            # Renormalize
            other_sum = sum(weights[k] for k in weights if k != 'wopr')
            if other_sum > 0:
                scale = 0.65 / other_sum
                for k in weights:
                    if k != 'wopr':
                        weights[k] *= scale
    
    return weights

def apply_replacement_level(nexxt_score):
    """
    Applies a tier-based multiplier for trade value calculation.
    Returns: (multiplier, tier_name)
    """
    if nexxt_score >= 90:
        return 1.3, "Elite (1.3x)"
    elif nexxt_score >= 80:
        return 1.0, "High Starter (1.0x)"
    elif nexxt_score >= 70:
        return 0.8, "Low Starter (0.8x)"
    elif nexxt_score >= 60:
        return 0.4, "High Scrub (0.4x)"
    else:
        return 0.2, "Scrub (0.2x)"

def calculate_nexxt_score(player_data, pos, all_player_stats):
    """
    Calculates the NEXXT Score (1-99 Madden-style rating) with POSITION-RELATIVE grading.
    The best WR gets 99, the best RB gets 99, etc.
    """
    if not player_data:
        return 50  # Default
    
    games = player_data.get('games_played', 0)
    
    # SAMPLE SIZE PENALTY: If < 3 games, cap at 90 to prevent skew
    sample_size_penalty = 1.0
    if games < 3:
        sample_size_penalty = 0.91  # Max score = 90
    
    # === POSITION-RELATIVE SCORING ===
    # Extract all players at the same position for percentile ranking
    position_peers = [p for pid, p in all_player_stats.items() if p.get('position') == pos and p.get('games_played', 0) >= 1]
    
    if not position_peers:
        return 50  # No comparison data
    
    # Get dynamic weights (correlation-based)
    dynamic_weights = get_dynamic_weights(all_player_stats, pos)
    
    # === THE RESULTS ANCHOR (50% FPPG Floor) ===
    # Calculate FPPG percentile against position peers
    fppg = player_data.get('fppg', 0)
    fppg_vals = [p.get('fppg', 0) for p in position_peers]
    fppg_percentile = percentileofscore(fppg_vals, fppg, kind='rank') / 100 if len(fppg_vals) > 1 else 0.5
    
    # Calculate stat-based score using dynamic weights
    metrics = {}
    for metric in dynamic_weights.keys():
        val = player_data.get(metric, 0)
        
        # Handle None values for optional metrics
        if metric in ['cpoe', 'ryoe', 'avg_cushion'] and val is None:
            val = 0
        
        vals = []
        for p in position_peers:
            pval = p.get(metric, 0)
            if metric in ['cpoe', 'ryoe', 'avg_cushion'] and pval is None:
                pval = 0
            vals.append(pval)
        
        pct = percentileofscore(vals, val, kind='rank') / 100 if len(vals) > 1 else 0.5
        metrics[metric] = pct
    
    stat_score = sum(metrics.get(m, 0.5) * dynamic_weights.get(m, 0) for m in dynamic_weights)
    
    # Final Score = 50% FPPG + 50% Underlying Stats
    raw_score = ((fppg_percentile * 0.50) + (stat_score * 0.50)) * 100
    
    # Apply sample size penalty
    raw_score = raw_score * sample_size_penalty
    
    # Cap between 10-99 (floor at 10 to avoid single-digit ugliness)
    nexxt_score = max(10, min(99, int(raw_score)))
    
    return nexxt_score

# --- UI LOGIC ---
all_players = get_all_players_data()
active_players = load_nfl_context()  # Only active players
team_logos = load_team_logos()  # Team logos for leaderboard
schedule, schedule_available = load_nfl_schedule(CURRENT_SEASON)  # Use current season
player_stats, def_stats, data_season = get_predictive_index(CURRENT_SEASON)  # Use current season for real data context

# Get current NFL week dynamically (auto-updates every week)
current_week = get_current_week()

# Diagnostic checkpoint: Verify data loaded
if not player_stats:
    st.error("❌ CRITICAL: player_stats is empty. Data pipeline failed.")
    st.info("Debug Info:")
    st.write(f"- Active Players Loaded: {len(active_players)}")
    st.write(f"- All Players Loaded: {len(all_players)}")
    st.write(f"- Data Season: {data_season}")
    st.stop()
else:
    st.sidebar.success(f"✅ {len(player_stats)} players ready")

# Formatting Helper
def get_player_name(sleeper_id):
    return all_players.get(sleeper_id, {}).get('full_name', sleeper_id)

# Filter for Dropdowns (Only Active Offense Players)
searchable_players = {v['full_name']: k for k, v in active_players.items() if v.get('full_name')}

# Generate globally sorted player options (by NEXXT Score descending)
player_scores = []
for name, pid in searchable_players.items():
    pdata = player_stats.get(pid, {})
    pos = active_players.get(pid, {}).get('position', 'UNK')
    score = calculate_nexxt_score(pdata, pos, player_stats) if pdata else 0
    player_scores.append((name, score))

# Sort descending by NEXXT Score, then alphabetically
player_scores.sort(key=lambda x: (-x[1], x[0]))
sorted_player_options = [x[0] for x in player_scores]

def get_leaderboard_data(_player_stats, _active_players, _team_logos):
    """
    Generates NEXXT Score leaderboard for all active players.
    Cached for performance (500+ player calculations).
    """
    leaderboard = []
    
    for player_id, player_info in _active_players.items():
        player_name = player_info.get('full_name', 'Unknown')
        player_team = player_info.get('team', 'FA')
        player_pos = player_info.get('position', 'UNK')
        
        # Get stats
        pdata = _player_stats.get(player_id, {})
        
        # Skip players with no data
        if not pdata or pdata.get('games_played', 0) < 1:
            continue
        
        # Filter garbage data
        if pdata.get('wopr', 0) > 2.0:
            continue
        if pdata.get('games_played', 0) > 20:  # Impossible to play > 20 games in a season
            continue
        if player_team in ['None', 'UNK', 'FA', '', None]:
            continue
        
        # Calculate NEXXT Score (keep as pure int - NO STRING FORMATTING)
        nexxt_score = int(calculate_nexxt_score(pdata, player_pos, _player_stats))
        
        # Get key stats
        fppg = round(pdata.get('fppg', 0), 1)
        
        # Get team logo (with fallback)
        team_logo = _team_logos.get(player_team, 'https://a.espncdn.com/combiner/i?img=/i/teamlogos/nfl/500/scoreboard/nfl.png')
        
        leaderboard.append({
            'Player': player_name,
            'Logo': team_logo,
            'Team': player_team,
            'Pos': player_pos,
            'NEXXT': nexxt_score,
            'FPPG': fppg,
            'RawStats': pdata
        })
    
    # Sort by NEXXT Score, then FPPG, then WOPR (multi-key tie-breaker)
    leaderboard.sort(key=lambda x: (x['NEXXT'], x['FPPG'], x['RawStats'].get('wopr', 0)), reverse=True)
    
    return leaderboard


# --- TABS ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["⚔️ Matchups", "🔮 The Oracle (Start/Sit)", "⚖️ Trade", "🏆 NEXXT Leaders", "📊 Data Lab", "🛠️ Diagnostics"])

with tab1:
    st.write("Matchup view (simplified for now to focus on Tab 2)")

# --- THE ORACLE (TAB 2) - MULTI-PLAYER COMPARISON ---
with tab2:
    st.header("🔮 The Start/Sit Oracle")
    st.markdown("Compare 2+ players with **Rate-Based Analytics** (FPPG, Opps/Game, NEXXT Score). Injury-proof metrics.")
    
    # MULTI-SELECT PLAYER PICKER (Using global sorted list)
    selected_names = st.multiselect(
        "Select Players to Compare (2-5 recommended)",
        options=sorted_player_options,
        default=[]
    )
    
    if len(selected_names) < 2:
        st.warning("⚠️ Please select at least 2 players to compare.")
    else:
        # DYNAMIC COLUMN LAYOUT
        cols = st.columns(len(selected_names))
        
        # DYNAMIC PLAYER CARDS
        player_data_list = []  # Store for AI prompt
        
        for idx, player_name in enumerate(selected_names):
            player_id = searchable_players[player_name]
            player_info = active_players[player_id]
            player_team = player_info.get('team', 'UNK')
            player_pos = player_info.get('position', 'UNK')
            
            # Get opponent
            player_opp = get_current_opponent(player_team, current_week, schedule, schedule_available)
            
            # Get stats
            pdata = player_stats.get(player_id, {})
            nexxt_score = calculate_nexxt_score(pdata, player_pos, player_stats)
            
            # Store for AI
            player_data_list.append({
                'name': player_name,
                'id': player_id,
                'team': player_team,
                'pos': player_pos,
                'opp': player_opp,
                'data': pdata,
                'nexxt': nexxt_score
            })
            
            with cols[idx]:
                st.subheader(f"{player_name}")
                
                # NEXXT SCORE DISPLAY (Top Right)
                st.markdown(f"<div style='text-align: right; color: #D4AF37; font-weight: bold; font-size: 24px;'>NEXXT: {nexxt_score}</div>", unsafe_allow_html=True)
                
                # Opponent Display
                if player_opp:
                    st.markdown(f"**{player_team}** vs <span class='highlight-opp'>{player_opp}</span>", unsafe_allow_html=True)
                else:
                    st.markdown(f"**{player_team}** (Opponent TBD)", unsafe_allow_html=True)
                
                # POSITION-SPECIFIC METRIC CARD
                if player_pos == 'QB':
                    cpoe_val = pdata.get('cpoe')
                    cpoe_display = f"{cpoe_val:.1f}%" if cpoe_val is not None else "N/A"
                    fppg = pdata.get('fppg', 0)
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="big-stat">{fppg:.1f}</div>
                        <div class="sub-stat">FPPG (Fantasy Points Per Game)</div>
                        <div class="big-stat">{pdata.get('epa_per_play', 0):.3f}</div>
                        <div class="sub-stat">EPA/Play</div>
                        <div class="big-stat">{cpoe_display}</div>
                        <div class="sub-stat">CPOE</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                elif player_pos == 'RB':
                    ryoe_val = pdata.get('ryoe')
                    ryoe_display = f"{ryoe_val:.2f}" if ryoe_val is not None else "N/A"
                    fppg = pdata.get('fppg', 0)
                    rz_per_game = pdata.get('rz_opps_per_game', 0)
                    targets_per_game = pdata.get('targets_per_game', 0)
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="big-stat">{fppg:.1f}</div>
                        <div class="sub-stat">FPPG</div>
                        <div class="big-stat">{ryoe_display}</div>
                        <div class="sub-stat">RYOE (Per Attempt)</div>
                        <div class="big-stat">{rz_per_game:.1f}</div>
                        <div class="sub-stat">RZ Opps/Game</div>
                        <div class="big-stat">{targets_per_game:.1f}</div>
                        <div class="sub-stat">Targets/Game (Receiving Upside)</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                else:  # WR/TE
                    fppg = pdata.get('fppg', 0)
                    targets_per_game = pdata.get('targets_per_game', 0)
                    rz_per_game = pdata.get('rz_opps_per_game', 0)
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="big-stat">{fppg:.1f}</div>
                        <div class="sub-stat">FPPG</div>
                        <div class="big-stat">{pdata.get('wopr', 0):.2f}</div>
                        <div class="sub-stat">WOPR</div>
                        <div class="big-stat">{targets_per_game:.1f}</div>
                        <div class="sub-stat">Targets/Game</div>
                        <div class="big-stat">{rz_per_game:.1f}</div>
                        <div class="sub-stat">RZ Opps/Game</div>
                    </div>
                    """, unsafe_allow_html=True)
        
        # --- THE AI BRAIN (PROFESSIONAL TONE) ---
        st.markdown("---")
        if st.button("🔮 Ask the Oracle", type="primary"):
            if not google_api_key:
                st.error("Enter API Key in Sidebar")
            elif any(p['opp'] is None for p in player_data_list):
                st.error("⚠️ Opponent data unavailable for some players. Analysis may be limited.")
            else:
                with st.spinner("Analyzing efficiency metrics and matchup context..."):
                    # Helper to format None values
                    def fmt_stat(val, format_str=".2f", suffix=""):
                        if val is None:
                            return "N/A"
                        return f"{val:{format_str}}{suffix}"
                    
                    # BUILD DYNAMIC PROMPT FOR MULTI-PLAYER COMPARISON
                    player_blocks = []
                    for p in player_data_list:
                        pname = p['name']
                        ppos = p['pos']
                        pteam = p['team']
                        popp = p['opp'] if p['opp'] else "TBD"
                        pdata = p['data']
                        nexxt = p['nexxt']
                        
                        def_epa = def_stats.get(popp, 0) if popp != "TBD" else 0
                        
                        # Position-specific stat formatting
                        if ppos == 'QB':
                            stats_text = f"""
                            - FPPG: {pdata.get('fppg', 0):.1f}
                            - EPA/Play: {pdata.get('epa_per_play', 0):.3f} (Positive = above average efficiency)
                            - CPOE: {fmt_stat(pdata.get('cpoe'), '.1f', '%')}
                            - Games Played: {pdata.get('games_played', 0):.0f}"""
                        elif ppos == 'RB':
                            stats_text = f"""
                            - FPPG: {pdata.get('fppg', 0):.1f}
                            - RYOE: {fmt_stat(pdata.get('ryoe'), '.2f')} (Efficiency per carry)
                            - RZ Opps/Game: {pdata.get('rz_opps_per_game', 0):.1f} (TD upside indicator)
                            - Targets/Game: {pdata.get('targets_per_game', 0):.1f} (Receiving workload)
                            - Games Played: {pdata.get('games_played', 0):.0f}"""
                        else:  # WR/TE
                            stats_text = f"""
                            - FPPG: {pdata.get('fppg', 0):.1f}
                            - WOPR: {pdata.get('wopr', 0):.2f} (Opportunity share)
                            - Targets/Game: {pdata.get('targets_per_game', 0):.1f}
                            - RZ Opps/Game: {pdata.get('rz_opps_per_game', 0):.1f}
                            - Games Played: {pdata.get('games_played', 0):.0f}"""
                        
                        player_blocks.append(f"""
**{pname}** ({ppos}) - {pteam} vs {popp} | NEXXT Score: {nexxt}/99
{stats_text}
- Matchup: {popp} Defense allows {def_epa:.3f} EPA/Play (Lower = tougher matchup)
""")
                    
                    prompt = f"""
Act as a sophisticated Fantasy Football analyst. Be objective, professional, and nuanced.

You are comparing {len(player_data_list)} players for a start/sit decision:

{''.join(player_blocks)}

**ANALYSIS GUIDELINES:**
- **Tone**: Professional and analytical. Avoid hyperbolic language like "abysmal" or "horrendous". Use terms like "limited upside", "volatile floor", "efficiency concerns", or "favorable outlook".
- **Rate-Based Metrics**: Prioritize per-game stats (FPPG, Opps/Game) over season totals. A player with 10 games at 20 FPPG > a player with 17 games at 15 FPPG.
- **NEXXT Score**: Use this as a quick holistic indicator (70+ = elite, 50-69 = solid, <50 = limited role).
- **Zero Points Rule**: If FPPG is low but games_played is also low, do NOT penalize them—they may be injured or new to the role.

**OUTPUT FORMAT** (Under 150 words total):

1. **Winner Prediction**: [Name] - One sentence stating who to start and why.
2. **Key Mismatch**: One sentence highlighting the decisive stat advantage (e.g., "Player A's 2.5 RZ Opps/Game vs a defense allowing top-5 EPA").
"""
                    
                    try:
                        model = genai.GenerativeModel("gemini-2.5-flash")
                        resp = model.generate_content(prompt)
                        st.success("✅ Analysis Complete")
                        st.markdown(f"### 🧠 Oracle Verdict\n{resp.text}")
                    except Exception as e:
                        st.error(f"AI Error: {e}")

with tab3:
    st.header("⚖️ Trade Auditor")
    st.markdown("**AI-powered trade analysis** using NEXXT Scores and advanced metrics.")
    
    # Input sections
    col_give, col_get = st.columns(2)
    
    with col_give:
        st.subheader("📤 You Give")
        give_players = st.multiselect(
            "Select players you're trading away",
            options=sorted_player_options,
            key="give_players"
        )
    
    with col_get:
        st.subheader("📥 You Get")
        get_players = st.multiselect(
            "Select players you're receiving",
            options=sorted_player_options,
            key="get_players"
        )
    
    # Display selected players with stats
    if give_players or get_players:
        st.markdown("---")
        
        col_give_display, col_get_display = st.columns(2)
        
        # Calculate values
        give_value = 0
        give_details = []
        
        with col_give_display:
            st.markdown("### 📤 Giving Away")
            for player_name in give_players:
                player_id = searchable_players[player_name]
                pdata = player_stats.get(player_id, {})
                pos = pdata.get('position', 'UNK')
                nexxt = int(calculate_nexxt_score(pdata, pos, player_stats)) if pdata else 0
                fppg = round(pdata.get('fppg', 0), 1)
                give_value += nexxt
                
                # Build advanced stats based on position
                if pos == 'QB':
                    epa = round(pdata.get('epa_per_play', 0), 3)
                    cpoe = round(pdata.get('cpoe', 0), 1) if pdata.get('cpoe') is not None else 0.0
                    advanced_stats = f"EPA: {epa:+.3f} | CPOE: {cpoe:+.1f}%"
                elif pos == 'RB':
                    ryoe = round(pdata.get('ryoe', 0), 2) if pdata.get('ryoe') is not None else 0.0
                    usage = round(pdata.get('ppr_usage_per_game', 0), 1)
                    advanced_stats = f"RYOE: {ryoe:+.2f} | Usage: {usage}/g"
                else:  # WR/TE
                    wopr = round(pdata.get('wopr', 0), 2)
                    tgt_share = round(pdata.get('tgt_share', 0) * 100, 1)
                    advanced_stats = f"WOPR: {wopr:.2f} | TgtShare: {tgt_share}%"
                
                # Display enhanced player card
                st.markdown(f"""
                <div class="player-mini-card">
                    <div class="player-name">{player_name} ({pos})</div>
                    <div class="player-stats">NEXXT: {nexxt} | FPPG: {fppg}</div>
                    <div class="player-advanced">{advanced_stats}</div>
                </div>
                """, unsafe_allow_html=True)
                
                give_details.append({
                    'name': player_name,
                    'pos': pos,
                    'nexxt': nexxt,
                    'fppg': fppg,
                    'wopr': round(pdata.get('wopr', 0), 2),
                    'ryoe': round(pdata.get('ryoe', 0), 2) if pdata.get('ryoe') is not None else 0.0
                })
        
        get_value = 0
        get_details = []
        
        with col_get_display:
            st.markdown("### 📥 Receiving")
            for player_name in get_players:
                player_id = searchable_players[player_name]
                pdata = player_stats.get(player_id, {})
                pos = pdata.get('position', 'UNK')
                nexxt = int(calculate_nexxt_score(pdata, pos, player_stats)) if pdata else 0
                fppg = round(pdata.get('fppg', 0), 1)
                get_value += nexxt
                
                # Build advanced stats based on position
                if pos == 'QB':
                    epa = round(pdata.get('epa_per_play', 0), 3)
                    cpoe = round(pdata.get('cpoe', 0), 1) if pdata.get('cpoe') is not None else 0.0
                    advanced_stats = f"EPA: {epa:+.3f} | CPOE: {cpoe:+.1f}%"
                elif pos == 'RB':
                    ryoe = round(pdata.get('ryoe', 0), 2) if pdata.get('ryoe') is not None else 0.0
                    usage = round(pdata.get('ppr_usage_per_game', 0), 1)
                    advanced_stats = f"RYOE: {ryoe:+.2f} | Usage: {usage}/g"
                else:  # WR/TE
                    wopr = round(pdata.get('wopr', 0), 2)
                    tgt_share = round(pdata.get('tgt_share', 0) * 100, 1)
                    advanced_stats = f"WOPR: {wopr:.2f} | TgtShare: {tgt_share}%"
                
                # Display enhanced player card
                st.markdown(f"""
                <div class="player-mini-card">
                    <div class="player-name">{player_name} ({pos})</div>
                    <div class="player-stats">NEXXT: {nexxt} | FPPG: {fppg}</div>
                    <div class="player-advanced">{advanced_stats}</div>
                </div>
                """, unsafe_allow_html=True)
                
                get_details.append({
                    'name': player_name,
                    'pos': pos,
                    'nexxt': nexxt,
                    'fppg': fppg,
                    'wopr': round(pdata.get('wopr', 0), 2),
                    'ryoe': round(pdata.get('ryoe', 0), 2) if pdata.get('ryoe') is not None else 0.0
                })
        
        # Summary comparison
        st.markdown("---")
        col_summary_give, col_summary_get = st.columns(2)
        
        # Calculate adjustments for display
        max_give_display = max([p['nexxt'] for p in give_details]) if give_details else 0
        max_get_display = max([p['nexxt'] for p in get_details]) if get_details else 0
        
        with col_summary_give:
            st.metric("📤 Total Give Value", f"{give_value} NEXXT (Raw)", delta=f"{len(give_players)} players")
            st.caption(f"Best Player: {max_give_display} NEXXT")
            
            # Show adjustment preview
            if give_details:
                st.markdown("**Adjusted Calculation:**")
                for p in give_details:
                    _, tier = apply_replacement_level(p['nexxt'])
                    adj_val = p['nexxt'] * (1.3 if p['nexxt'] >= 90 else 1.0 if p['nexxt'] >= 80 else 0.8 if p['nexxt'] >= 70 else 0.4 if p['nexxt'] >= 60 else 0.2)
                    st.caption(f"{p['name']}: {p['nexxt']} × {tier} = {adj_val:.1f}")
        
        with col_summary_get:
            st.metric("📥 Total Get Value", f"{get_value} NEXXT (Raw)", delta=f"{len(get_players)} players")
            st.caption(f"Best Player: {max_get_display} NEXXT")
            
            # Show adjustment preview
            if get_details:
                st.markdown("**Adjusted Calculation:**")
                for p in get_details:
                    _, tier = apply_replacement_level(p['nexxt'])
                    adj_val = p['nexxt'] * (1.3 if p['nexxt'] >= 90 else 1.0 if p['nexxt'] >= 80 else 0.8 if p['nexxt'] >= 70 else 0.4 if p['nexxt'] >= 60 else 0.2)
                    st.caption(f"{p['name']}: {p['nexxt']} × {tier} = {adj_val:.1f}")
        
        # Audit button
        if st.button("⚖️ Audit This Trade", type="primary"):
            if not give_players and not get_players:
                st.warning("⚠️ Please select players on both sides to audit the trade.")
            else:
                with st.spinner("Analyzing trade..."):
                    # Build detailed context
                    give_context = "\n".join([
                        f"- {p['name']} ({p['pos']}): NEXXT {p['nexxt']}, FPPG {p['fppg']}, WOPR {p['wopr']}, RYOE {p['ryoe']}"
                        for p in give_details
                    ])
                    
                    get_context = "\n".join([
                        f"- {p['name']} ({p['pos']}): NEXXT {p['nexxt']}, FPPG {p['fppg']}, WOPR {p['wopr']}, RYOE {p['ryoe']}"
                        for p in get_details
                    ])
                    
                    # Calculate adjusted values with replacement level and track breakdown
                    give_breakdown = []
                    give_adjusted = 0
                    for p in give_details:
                        adj_val, tier = apply_replacement_level(p['nexxt'])
                        give_adjusted += adj_val
                        give_breakdown.append({
                            'name': p['name'],
                            'base': p['nexxt'],
                            'adj': adj_val,
                            'tier': tier
                        })
                    
                    get_breakdown = []
                    get_adjusted = 0
                    for p in get_details:
                        adj_val, tier = apply_replacement_level(p['nexxt'])
                        get_adjusted += adj_val
                        get_breakdown.append({
                            'name': p['name'],
                            'base': p['nexxt'],
                            'adj': adj_val,
                            'tier': tier
                        })
                    
                    # Track best players
                    max_give = max([p['nexxt'] for p in give_details]) if give_details else 0
                    max_get = max([p['nexxt'] for p in get_details]) if get_details else 0
                    
                    value_diff = get_adjusted - give_adjusted
                    
                    # Strict Best Player Rule
                    best_player_penalty = ""
                    if max_give > max_get and abs(value_diff) < (give_adjusted * 0.05):
                        # Giving up best player for depth with < 5% overpay
                        best_player_penalty = "⚠️ WARNING: You are downgrading the best asset for depth. This is risky unless the overpay is massive (>20%)."
                    
                    # Build adjustment explanation
                    adjustments = []
                    for b in give_breakdown:
                        adjustments.append(f"Give: {b['name']} → {b['base']} × {b['tier']} = {b['adj']:.1f}")
                    for b in get_breakdown:
                        adjustments.append(f"Get: {b['name']} → {b['base']} × {b['tier']} = {b['adj']:.1f}")
                    
                    adjustment_text = "\n".join(adjustments)
                    
                    prompt = f"""
**TRADE AUDIT REQUEST**

You are a sophisticated Fantasy Football analyst. Evaluate this trade using NEXXT Scores and advanced metrics.

**PLAYERS GIVEN AWAY:**
{give_context if give_context else "None"}
- Raw Total: {give_value} NEXXT
- Adjusted Total (with Replacement Level): {give_adjusted:.1f} NEXXT
- Best Player: {max_give} NEXXT

**PLAYERS RECEIVED:**
{get_context if get_context else "None"}
- Raw Total: {get_value} NEXXT
- Adjusted Total (with Replacement Level): {get_adjusted:.1f} NEXXT
- Best Player: {max_get} NEXXT

**REPLACEMENT LEVEL CALCULATION (5-Tier System):**
{adjustment_text}

**ADJUSTED VALUE DIFFERENCE:** {value_diff:+.1f} NEXXT (Positive = Win, Negative = Loss)

**BEST PLAYER ANALYSIS:**
- Give Side Best: {max_give} NEXXT
- Get Side Best: {max_get} NEXXT
{best_player_penalty if best_player_penalty else "✓ No best player downgrade concerns."}

**ANALYSIS INSTRUCTIONS:**
1. **Grade:** Assign a letter grade (A+ to F) based on the ADJUSTED value differential:
   - A+/A: Win by 15+ NEXXT (adjusted)
   - B: Win by 5-14 NEXXT
   - C: Neutral (-4 to +4), BUT downgrade to C- or D if Best Player warning is present
   - D: Loss by 5-14 NEXXT
   - F: Loss by 15+ NEXXT

2. **Winner:** State which side wins based on ADJUSTED totals.

3. **Rationale:** In 3 sentences, explain:
   - Why the 5-Tier System matters (Elite 90+ = 1.3x, High Starter 80-89 = 1.0x, Low Starter 70-79 = 0.8x, High Scrub 60-69 = 0.4x, Scrub <60 = 0.2x).
   - If a player has NEXXT 70-79, mention the "Low Starter Penalty" (0.8x) that reduces their impact.
   - If the user is downgrading the best asset for depth, explicitly warn them: "Never trade the best player unless massively overpaid (>20%)."

**CRITICAL:** Use the ADJUSTED totals with 5-Tier multipliers. Elite (90+) = 1.3x, High Starter (80-89) = 1.0x, Low Starter (70-79) = 0.8x, High Scrub (60-69) = 0.4x, Scrub (<60) = 0.2x.

**OUTPUT FORMAT:**
**Verdict:** [🚨 REJECT or ✅ ACCEPT]
**Grade:** [Letter]
**Winner:** [Give/Get]
**Rationale:** [3 sentences]

Keep it professional and concise.
"""
                    
                    try:
                        model = genai.GenerativeModel("gemini-2.5-flash")
                        resp = model.generate_content(prompt)
                        
                        # Parse grade from response
                        verdict_text = resp.text
                        grade_class = "grade-C"  # Default
                        
                        # Extract grade (simple parsing)
                        if "Grade: A+" in verdict_text or "Grade: A" in verdict_text:
                            grade_class = "grade-A"
                        elif "Grade: B" in verdict_text:
                            grade_class = "grade-B"
                        elif "Grade: C" in verdict_text:
                            grade_class = "grade-C"
                        elif "Grade: D" in verdict_text:
                            grade_class = "grade-D"
                        elif "Grade: F" in verdict_text:
                            grade_class = "grade-F"
                        
                        # Extract verdict emoji
                        verdict_emoji = "🎯"
                        if "REJECT" in verdict_text or "Grade: F" in verdict_text or "Grade: D" in verdict_text:
                            verdict_emoji = "🚨"
                        elif "ACCEPT" in verdict_text or "Grade: A" in verdict_text:
                            verdict_emoji = "✅"
                        
                        # Display verdict in styled box
                        st.markdown(f"""
                        <div class="verdict-box {grade_class}">
                            <div class="verdict-title">{verdict_emoji} Trade Verdict</div>
                            <div class="verdict-rationale">{verdict_text}</div>
                        </div>
                        """, unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f"AI Error: {e}")
    else:
        st.info("👆 Select players on both sides to analyze the trade.")

# --- DATA LAB (TAB 5) - DEBUG INTERFACE ---
with tab5:
    st.header("📊 Data Lab")
    st.markdown("**Audit the raw data powering NEXXT scores.** Verify WOPR, correlations, and weight distributions.")
    
    # === CORTEX VIEW (Dynamic Weights Debug) ===
    st.subheader("🧠 Cortex: Active Weights")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**QB Weights**")
        qb_weights = get_dynamic_weights(player_stats, 'QB')
        if qb_weights:
            st.json(qb_weights)
        else:
            st.warning("Insufficient QB data")
    
    with col2:
        st.markdown("**RB Weights**")
        rb_weights = get_dynamic_weights(player_stats, 'RB')
        if rb_weights:
            st.json(rb_weights)
        else:
            st.warning("Insufficient RB data")
    
    with col3:
        st.markdown("**WR/TE Weights**")
        wr_weights = get_dynamic_weights(player_stats, 'WR')
        if wr_weights:
            st.json(wr_weights)
        else:
            st.warning("Insufficient WR data")
    
    st.markdown("---")
    
    # === RAW STATS TABLE ===
    st.subheader("🔬 Raw Player Stats")
    
    # 1. GENERATE FINAL DATASET
    data_for_df = []
    for player_id, pdata in player_stats.items():
        # Strict filtering: Remove ghost data
        if pdata.get('games_played', 0) < 1 or pdata.get('games_played', 0) > 18:
            continue
        if pdata.get('wopr', 0) > 2.0:
            continue
        
        player_info = active_players.get(player_id, {})
        player_name = player_info.get('full_name', all_players.get(player_id, {}).get('full_name', player_id))
        player_team = player_info.get('team', all_players.get(player_id, {}).get('team', 'FA'))
        player_pos = pdata.get('position', 'UNK')
        
        # Skip free agents
        if player_team in [None, 'FA', 'UNK', '']:
            continue
        
        data_for_df.append({
            'Player': player_name,
            'Team': player_team,
            'Pos': player_pos,
            'NEXXT': int(calculate_nexxt_score(pdata, player_pos, player_stats)),
            'FPPG': round(pdata.get('fppg', 0), 2),
            'WOPR': round(pdata.get('wopr', 0), 2),
            'TgtShare': round(pdata.get('tgt_share', 0), 3),
            'RYOE': round(pdata.get('ryoe', 0), 2) if pdata.get('ryoe') is not None else 0.0,
            'EPA': round(pdata.get('epa_per_play', 0), 3),
            'CPOE': round(pdata.get('cpoe', 0), 2) if pdata.get('cpoe') is not None else 0.0,
            'Targets/G': round(pdata.get('targets_per_game', 0), 1),
            'RZ/G': round(pdata.get('rz_opps_per_game', 0), 1),
            'TeamEPA': round(pdata.get('team_epa', 0), 3),
            'Games': pdata.get('games_played', 0)
        })
    
    # 2. CREATE AND SORT DATAFRAME
    df_lab = pd.DataFrame(data_for_df)
    
    if df_lab.empty:
        st.warning("⚠️ No player data available for analysis. This may indicate a data loading issue.")
    else:
        # Filters
        col_a, col_b = st.columns(2)
        with col_a:
            pos_filter = st.multiselect("Filter by Position", options=['QB', 'RB', 'WR', 'TE'], default=[])
        with col_b:
            search_player = st.text_input("Search Player", value="")
        
        # Apply filters
        filtered_lab = df_lab.copy()
        if pos_filter:
            filtered_lab = filtered_lab[filtered_lab['Pos'].isin(pos_filter)]
        if search_player:
            filtered_lab = filtered_lab[filtered_lab['Player'].str.contains(search_player, case=False, na=False)]
        
        # Sort by NEXXT, then FPPG, then WOPR (multi-key tie-breaker)
        sort_cols = ['NEXXT', 'FPPG']
        if 'WOPR' in filtered_lab.columns:
            sort_cols.append('WOPR')
        filtered_lab = filtered_lab.sort_values(sort_cols, ascending=[False, False, False] if len(sort_cols) == 3 else [False, False]).reset_index(drop=True)
        
        # Display table
        st.dataframe(filtered_lab, use_container_width=True, height=500)
        
        # Download button
        csv = filtered_lab.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Stats as CSV",
            data=csv,
            file_name=f"nexxt_stats_week{current_week-1}.csv",
            mime="text/csv"
        )

# --- NEXXT LEADERS (TAB 4) ---
with tab4:
    st.header("🏆 NEXXT Leaders")
    st.markdown("The definitive fantasy rankings powered by **Volume, Production, and Efficiency**.")
    
    # Position Filter
    position_filter = st.selectbox(
        "Filter by Position",
        options=["Overall", "QB", "RB", "WR", "TE", "FLEX (RB/WR/TE)"],
        index=0
    )
    
    # Get leaderboard data (cached)
    with st.spinner("Calculating NEXXT Scores for all players..."):
        leaderboard = get_leaderboard_data(player_stats, active_players, team_logos)
    
    # Apply position filter
    if position_filter == "QB":
        filtered = [p for p in leaderboard if p['Pos'] == 'QB']
    elif position_filter == "RB":
        filtered = [p for p in leaderboard if p['Pos'] == 'RB']
    elif position_filter == "WR":
        filtered = [p for p in leaderboard if p['Pos'] == 'WR']
    elif position_filter == "TE":
        filtered = [p for p in leaderboard if p['Pos'] == 'TE']
    elif position_filter == "FLEX (RB/WR/TE)":
        filtered = [p for p in leaderboard if p['Pos'] in ['RB', 'WR', 'TE']]
    else:  # Overall
        filtered = leaderboard
    
    # Limit to Top 50
    top_50 = filtered[:50]
    
    # Validate data exists
    if not top_50:
        st.warning("⚠️ No players found matching the selected criteria. Try a different position filter.")
    else:
        # Add Rank column
        for idx, player in enumerate(top_50):
            player['Rank'] = idx + 1
        
        # Create DataFrame
        df = pd.DataFrame(top_50)
        
        # Verify required columns exist
        required_cols = ['Rank', 'Logo', 'Player', 'Team', 'Pos', 'NEXXT', 'FPPG']
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        if missing_cols:
            st.error(f"⚠️ Missing required columns: {missing_cols}. Data pipeline error.")
            st.write("Available columns:", df.columns.tolist())
        else:
            # Reorder columns and format
            df = df[required_cols]
            
            # Display with color formatting
            st.markdown(f"### Top {len(top_50)} Players - {position_filter}")
            
            # Apply Premium Gold Styling for Elite Players
            def style_elite_rows(row):
                styles = [''] * len(row)
                
                if row['NEXXT'] >= 90:
                    # Find NEXXT and Player column indices
                    nexxt_idx = list(row.index).index('NEXXT')
                    player_idx = list(row.index).index('Player')
                    
                    styles[nexxt_idx] = 'color: #F4D03F; font-weight: bold;'
                    styles[player_idx] = 'font-weight: bold;'
                
                return styles
            
            # Apply styling
            styled_df = df.style.apply(style_elite_rows, axis=1)
            
            # Interactive selection with enhanced visuals
            event = st.dataframe(
                styled_df,
                use_container_width=True,
                height=600,
                on_select="rerun",
                selection_mode="single-row",
                hide_index=True,
                column_config={
                    "Logo": st.column_config.ImageColumn("", width="small"),
                    "NEXXT": st.column_config.NumberColumn("NEXXT", format="%d"),
                    "FPPG": st.column_config.NumberColumn(format="%.1f"),
                    "RawStats": None
                }
            )
            
            # Handle row selection for AI analysis
            if event.selection.rows:
                selected_idx = event.selection.rows[0]
                selected_player = top_50[selected_idx]
                
                st.markdown("---")
                st.subheader(f"🔍 Deep Dive: {selected_player['Player']}")
                
                with st.spinner("Analyzing player ranking..."):
                    nexxt_value = selected_player['NEXXT']
                    raw_stats = selected_player.get('RawStats', {})
                    
                    # Build stats context
                    pos = selected_player['Pos']
                    if pos == 'QB':
                        stats_context = f"EPA/Play: {raw_stats.get('epa_per_play', 0):.3f}, CPOE: {raw_stats.get('cpoe', 0) if raw_stats.get('cpoe') is not None else 'N/A'}, Team EPA: {raw_stats.get('team_epa', 0):.3f}"
                    elif pos == 'RB':
                        stats_context = f"RYOE: {raw_stats.get('ryoe', 0) if raw_stats.get('ryoe') is not None else 'N/A'}, Targets/G: {raw_stats.get('targets_per_game', 0):.1f}, RZ Opps/G: {raw_stats.get('rz_opps_per_game', 0):.1f}, Team EPA: {raw_stats.get('team_epa', 0):.3f}"
                    else:
                        stats_context = f"WOPR: {raw_stats.get('wopr', 0):.2f}, Targets/G: {raw_stats.get('targets_per_game', 0):.1f}, Team EPA: {raw_stats.get('team_epa', 0):.3f}"
                    
                    prompt = f"""
**SYSTEM CONTEXT:**
- Current Date: December 2025
- Season: 2025-2026 NFL Season
- Current Week: {current_week}
- IMPORTANT: Players drafted in 2024 (Brock Bowers, Caleb Williams, etc.) are now YEAR 2 veterans in 2025. Do NOT call them rookies.

**ANALYSIS REQUEST:**
Explain why {selected_player['Player']} ({pos}, {selected_player['Team']}) is ranked #{selected_player['Rank']} with a NEXXT Score of {nexxt_value}/99.

**EXACT STATS (Week 1-{current_week-1} Data):**
- FPPG: {selected_player['FPPG']}
- {stats_context}

**ANALYSIS GUIDELINES:**
1. If FPPG is high but NEXXT is lower than expected, identify which underlying metric (Low Team EPA, Poor Efficiency, Limited RZ Usage) is dragging them down.
2. If NEXXT is high, cite the SPECIFIC stat driving it (e.g., "Elite 0.68 WOPR" or "99th percentile in Targets/Game").
3. Are they undervalued or overvalued compared to traditional rankings?

Keep it under 100 words. Be precise and analytical.
"""
                    
                    try:
                        model = genai.GenerativeModel("gemini-2.5-flash")
                        resp = model.generate_content(prompt)
                        st.markdown(resp.text)
                    except Exception as e:
                        st.error(f"AI Error: {e}")
            
            # Summary stats (use raw integer values)
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Players Ranked", len(leaderboard))
            with col2:
                avg_nexxt = sum(p['NEXXT'] for p in top_50) / len(top_50) if top_50 else 0
                st.metric(f"Avg NEXXT (Top {len(top_50)})", f"{avg_nexxt:.1f}")
            with col3:
                if top_50:
                    leader_nexxt = top_50[0]['NEXXT']
                    st.metric("Leader", f"{top_50[0]['Player']} ({leader_nexxt})")
    
    # Explanation
    with st.expander("ℹ️ How is NEXXT Score Calculated?"):
        st.markdown("""
        **Position-Relative Grading System (1-99 scale)**
        
        **RB Weights (The CMC Fix):**
        - 40% FPPG (Results matter most)
        - 30% Usage (Carries + Targets per game)
        - 20% RYOE (Efficiency tiebreaker)
        - 10% RZ Opps/Game
        
        **WR/TE Weights (The JSN Fix):**
        - 45% FPPG (Production)
        - 40% WOPR (Weighted Opportunity - King stat)
        - 15% Targets/Game
        
        **QB Weights:**
        - 40% Pass Attempts (Volume)
        - 30% EPA/Play (Efficiency)
        - 30% FPPG
        
        **Key Features:**
        - Position-relative: Best RB gets 99, best WR gets 99
        - Sample size penalty: <3 games capped at 90
        - Percentile-based: Uses scipy.stats for accurate ranking
        """)

# --- DIAGNOSTICS (TAB 6) - TEAM CODE AUDIT ---
with tab6:
    st.header("🛠️ Diagnostics")
    st.markdown("**Audit raw data sources to identify team code mismatches.**")
    
    # Load PBP for team code extraction
    pbp_full = load_nfl_data(season=CURRENT_SEASON)[0]
    
    # Calculate unique teams
    nfl_teams = sorted(pbp_full['posteam'].dropna().unique().tolist())
    sleeper_teams = sorted(list(set(p.get('team', '') for p in active_players.values() if p.get('team'))))
    
    # Display side-by-side
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 NFL PBP Codes")
        st.write(nfl_teams)
        st.caption(f"**{len(nfl_teams)} teams** found in Play-by-Play data")
    
    with col2:
        st.subheader("🏈 Sleeper API Codes")
        st.write(sleeper_teams)
        st.caption(f"**{len(sleeper_teams)} teams** found in Sleeper player data")
    
    st.markdown("---")
    
    # Mismatch Detection
    st.subheader("🔍 Mismatch Analysis")
    
    sleeper_set = set(sleeper_teams)
    nfl_set = set(nfl_teams)
    
    missing_in_nfl = sleeper_set - nfl_set
    missing_in_sleeper = nfl_set - sleeper_set
    
    if missing_in_nfl:
        st.error(f"⚠️ **Sleeper codes missing from NFL PBP:** {sorted(missing_in_nfl)}")
        st.caption("These teams need mappings in `TEAM_MAP`.")
    else:
        st.success("✅ All Sleeper teams found in NFL data.")
    
    if missing_in_sleeper:
        st.warning(f"ℹ️ **NFL codes not in Sleeper:** {sorted(missing_in_sleeper)}")
        st.caption("This is normal if teams are not represented in active Sleeper rosters.")
    
    st.markdown("---")
    
    st.markdown("---")
    
    # Current TEAM_MAP Display
    st.subheader("🗺️ Active TEAM_MAP")
    st.json(TEAM_MAP)

