import streamlit as st
import requests
import pandas as pd
import google.generativeai as genai
import datetime
import nflreadpy as nfl
import sqlite3

# --- 1. Database Setup ---
DATABASE_NAME = "fantasy_predictions.db"

def init_db():
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS predictions")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week INTEGER,
                matchup_id TEXT,
                manager TEXT,
                opponent TEXT,
                ai_analysis TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

def save_prediction(week, matchup_id, manager, opponent, ai_analysis):
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO predictions (week, matchup_id, manager, opponent, ai_analysis)
            VALUES (?, ?, ?, ?, ?)
        ''', (week, matchup_id, manager, opponent, ai_analysis))
        conn.commit()

init_db()

# --- 2. Sidebar & Settings ---
st.sidebar.title("NEXXT Fantasy")
st.sidebar.markdown("### Version: 7.1 (Ordered Fix)")

if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()

if 'data_health' not in st.session_state:
    st.session_state.data_health = {'Sleeper API': 'Pending', 'NFL Play-by-Play': 'Pending', 'Next Gen Stats': 'Pending'}

league_id = st.sidebar.text_input('League ID', '1217902363445043200')

if "GOOGLE_API_KEY" in st.secrets:
    google_api_key = st.secrets["GOOGLE_API_KEY"]
    st.sidebar.success("AI Key Loaded")
else:
    google_api_key = st.sidebar.text_input('Google API Key', type='password')

if google_api_key:
    try:
        genai.configure(api_key=google_api_key)
    except Exception as e:
        st.sidebar.error(f"Key Error: {e}")

status_placeholder = st.sidebar.empty()

# --- 3. Data Functions (Defined BEFORE use) ---

def get_matchups(league_id, week):
    try:
        return requests.get(f"https://api.sleeper.app/v1/league/{league_id}/matchups/{week}").json()
    except: return []

def get_current_week(league_id):
    return requests.get(f"https://api.sleeper.app/v1/state/nfl").json()['week']

def get_league_users(league_id):
    return requests.get(f"https://api.sleeper.app/v1/league/{league_id}/users").json()

def get_league_rosters(league_id):
    return requests.get(f"https://api.sleeper.app/v1/league/{league_id}/rosters").json()

@st.cache_data
def get_all_players_v7():
    """Loads Sleeper Player Database"""
    try:
        players_data = requests.get("https://api.sleeper.app/v1/players/nfl").json()
        # Fix Defense Names
        for p_id, p_data in players_data.items():
            if p_data.get('position') == 'DEF':
                team = p_data.get('team')
                if team: players_data[p_id]['full_name'] = f"{team} Defense"
        return players_data
    except: return {}

@st.cache_data
def get_player_positions(all_players_data):
    """Extracts positions from player data"""
    return {p_id: p_data.get('position', 'UNK') for p_id, p_data in all_players_data.items()}

# --- 4. Advanced Data Functions ---

@st.cache_data
def get_ngs_data_v7(season):
    try:
        ngs_pass = nfl.load_nextgen_stats(seasons=[season], stat_type='passing').to_pandas()
        ngs_rush = nfl.load_nextgen_stats(seasons=[season], stat_type='rushing').to_pandas()
        ngs_rec = nfl.load_nextgen_stats(seasons=[season], stat_type='receiving').to_pandas()
        
        if not ngs_pass.empty:
            if 'completion_percentage_above_expectation' in ngs_pass.columns:
                ngs_pass.rename(columns={'completion_percentage_above_expectation': 'cpoe'}, inplace=True)
            if 'avg_intended_air_yards' in ngs_pass.columns:
                ngs_pass.rename(columns={'avg_intended_air_yards': 'air_yards'}, inplace=True)
        
        if not ngs_rush.empty:
            if 'rush_yards_over_expected' in ngs_rush.columns:
                ngs_rush.rename(columns={'rush_yards_over_expected': 'ryoe'}, inplace=True)
        
        if not ngs_rec.empty:
            if 'avg_separation' in ngs_rec.columns:
                ngs_rec.rename(columns={'avg_separation': 'avg_sep'}, inplace=True)
        
        st.session_state.data_health['Next Gen Stats'] = '✅ Online'
        return ngs_pass, ngs_rush, ngs_rec
    except Exception:
        st.session_state.data_health['Next Gen Stats'] = '⚠️ Offline'
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

@st.cache_data
def get_pbp_advanced_stats_v7(season):
    try:
        pbp_df = nfl.load_pbp(seasons=[season]).to_pandas()
        ids_df = nfl.load_ff_playerids().to_pandas()
        ids_df['sleeper_id'] = ids_df['sleeper_id'].astype(str).str.replace(r'\.0$', '', regex=True)
        
        if pbp_df.empty: return {}

        max_week = pbp_df['week'].max()
        pbp_df = pbp_df[pbp_df['week'] >= max_week - 2]
        
        advanced_stats = {}

        # 1. QB EPA
        if 'epa' in pbp_df.columns:
            qb_stats = pbp_df.groupby('passer_player_id')['epa'].mean().reset_index()
            merged = qb_stats.merge(ids_df[['gsis_id', 'sleeper_id']], left_on='passer_player_id', right_on='gsis_id')
            for _, row in merged.iterrows():
                advanced_stats[row['sleeper_id']] = {'epa': row['epa']}

        # 2. RB Red Zone
        rz_df = pbp_df[(pbp_df['yardline_100'] <= 20) & (pbp_df['play_type'].isin(['run', 'pass']))]
        if not rz_df.empty:
            rz_counts = rz_df.assign(pid=rz_df['rusher_player_id'].fillna(rz_df['receiver_player_id']))
            rz_counts = rz_counts.groupby('pid').size().reset_index(name='rz_touches')
            merged = rz_counts.merge(ids_df[['gsis_id', 'sleeper_id']], left_on='pid', right_on='gsis_id')
            for _, row in merged.iterrows():
                if row['sleeper_id'] not in advanced_stats: advanced_stats[row['sleeper_id']] = {}
                advanced_stats[row['sleeper_id']]['rz_touches'] = row['rz_touches']

        # 3. WR/TE WOPR Proxy
        wr_df = pbp_df[pbp_df['play_type'] == 'pass'].groupby('receiver_player_id').agg(
            targets=('play_id', 'count'),
            air_yards=('air_yards', 'sum'),
            avg_epa=('epa', 'mean')
        ).reset_index()
        wr_df['wopr_proxy'] = 1.5 * wr_df['targets'] + 0.07 * wr_df['air_yards']
        merged = wr_df.merge(ids_df[['gsis_id', 'sleeper_id']], left_on='receiver_player_id', right_on='gsis_id')
        for _, row in merged.iterrows():
             if row['sleeper_id'] not in advanced_stats: advanced_stats[row['sleeper_id']] = {}
             advanced_stats[row['sleeper_id']].update({'wopr_proxy': row['wopr_proxy'], 'pbp_epa': row['avg_epa']})

        # 4. Defense (EPA Allowed)
        if 'defteam' in pbp_df.columns:
            def_df = pbp_df.groupby('defteam').agg(
                epa_allowed=('epa', 'mean'),
                sacks=('sack', 'sum') if 'sack' in pbp_df.columns else ('sack_qb', 'sum'),
                pass_att=('pass_attempt', 'sum')
            ).reset_index()
            
            # Normalize column name
            if 'sack' in def_df.columns: def_df.rename(columns={'sack': 'sacks'}, inplace=True)
            elif 'sack_qb' in def_df.columns: def_df.rename(columns={'sack_qb': 'sacks'}, inplace=True)

            def_df['sack_rate'] = def_df['sacks'] / def_df['pass_att']
            
            for _, row in def_df.iterrows():
                team = row['defteam']
                stats = {'epa_allowed': row['epa_allowed'], 'sack_rate': row['sack_rate'], 'sacks_pbp': row['sacks']}
                advanced_stats[team] = stats
                if team == 'JAX': advanced_stats['JAC'] = stats
                if team == 'WAS': advanced_stats['WSH'] = stats

        # 5. Kicker
        if 'field_goal_attempt' in pbp_df.columns:
            k_df = pbp_df[pbp_df['field_goal_attempt'] == 1].groupby('kicker_player_id').agg(
                made=('field_goal_result', lambda x: (x=='made').sum()),
                atts=('play_id', 'count'),
                long=('kick_distance', lambda x: x[pbp_df['field_goal_result']=='made'].max())
            ).reset_index()
            k_df['fg_pct'] = (k_df['made'] / k_df['atts']) * 100
            merged = k_df.merge(ids_df[['gsis_id', 'sleeper_id']], left_on='kicker_player_id', right_on='gsis_id')
            for _, row in merged.iterrows():
                 if row['sleeper_id'] not in advanced_stats: advanced_stats[row['sleeper_id']] = {}
                 advanced_stats[row['sleeper_id']].update({'fg_percentage': row['fg_pct'], 'longest_fg_made': row['long']})

        st.session_state.data_health['NFL Play-by-Play'] = '✅ Online'
        return advanced_stats
    except Exception as e:
        st.session_state.data_health['NFL Play-by-Play'] = f'❌ Failed: {e}'
        return {}

@st.cache_data
def get_volume_stats_v7(current_week):
    """Fetches Volume and Team Stats"""
    # 1. Load Player Stats
    try:
        stats_df = nfl.load_player_stats(seasons=[2025]).to_pandas()
        ids_df = nfl.load_ff_playerids().to_pandas()
        
        if 'player_position' in stats_df.columns: stats_df.rename(columns={'player_position': 'position'}, inplace=True)
        elif 'position' not in stats_df.columns: stats_df['position'] = 'UNK'

        merged = stats_df.merge(ids_df[['gsis_id', 'sleeper_id']], left_on='player_id', right_on='gsis_id', how='inner')
        merged['sleeper_id'] = merged['sleeper_id'].astype(str).str.replace(r'\.0$', '', regex=True)

        # SAFE COLUMNS ONLY
        cols = ['sleeper_id', 'week', 'targets', 'carries', 'attempts', 'fantasy_points_ppr', 'position']
        valid_cols = [c for c in cols if c in merged.columns]
        merged = merged[valid_cols].copy()
        
        for c in cols:
            if c not in merged.columns: merged[c] = 0
            else: merged[c] = merged[c].fillna(0)

        # Simple Volume Calc (Offense Only)
        merged['vol'] = merged['targets'] + merged['carries'] + merged['attempts']
        
        max_week = merged['week'].max()
        merged = merged[merged['week'] >= max_week - 2]
        
        final_stats = {}
        for sid, group in merged.groupby('sleeper_id'):
            pos = group['position'].iloc[0] if 'position' in group.columns else 'UNK'
            final_stats[sid] = {'vol': group['vol'].mean(), 'avg_pts': group['fantasy_points_ppr'].mean(), 'position': pos}
    except:
        final_stats = {}

    # 2. Load Team Stats (Defenses Backup)
    try:
        team_df = nfl.load_team_stats(seasons=[2025]).to_pandas()
        if not team_df.empty:
            max_t = team_df['week'].max()
            team_df = team_df[team_df['week'] >= max_t - 2].copy()
            
            num_cols = ['sacks', 'interceptions', 'fumbles_recovered', 'fantasy_points_ppr']
            # Ensure exists
            for c in num_cols: 
                if c not in team_df.columns: team_df[c] = 0
            
            grouped = team_df.groupby('team')[num_cols].mean()
            
            for team, row in grouped.iterrows():
                vol = row['sacks'] + row['interceptions'] + row['fumbles_recovered']
                stats = {'vol': vol, 'avg_pts': row['fantasy_points_ppr'], 'position': 'DEF'}
                final_stats[team] = stats
                if team == 'JAX': final_stats['JAC'] = stats
                if team == 'WAS': final_stats['WSH'] = stats
                
        st.session_state.data_health['Volume Stats'] = "✅ Online"
        return final_stats
    except Exception as e:
        st.session_state.data_health['Volume Stats'] = f"❌ Failed: {e}"
        return final_stats

# --- 5. Main App Logic ---
if league_id:
    # Load Data First
    col_a, col_b, col_c = st.columns(3)
    with col_a: 
        vol_stats = get_volume_stats_v7(13)
        st.caption(f"Vol: {st.session_state.data_health.get('Volume Stats', 'Pending')}")
    with col_b: 
        pbp_stats = get_pbp_advanced_stats_v7(2025)
        st.caption(f"PBP: {st.session_state.data_health.get('NFL Play-by-Play', 'Pending')}")
    with col_c: 
        ngs_pass, ngs_rush, ngs_rec = get_ngs_data_v7(2025)
        st.caption(f"NGS: {st.session_state.data_health.get('Next Gen Stats', 'Pending')}")

    # THEN Load Sleeper
    users = get_league_users(league_id)
    rosters = get_league_rosters(league_id)
    user_map = {u['user_id']: u['display_name'] for u in users}
    roster_owner_map = {r['roster_id']: r['owner_id'] for r in rosters}
    
    # FIX: Correct function call
    all_players = get_all_players_v7()
    player_positions = get_player_positions(all_players)
    curr_week = get_current_week(league_id)

    # Process NGS
    ngs_stats = {}
    ids = nfl.load_ff_playerids().to_pandas()
    ids['sleeper_id'] = ids['sleeper_id'].astype(str).str.replace(r'\.0$', '', regex=True)
    ids['gsis_id'] = ids['gsis_id'].astype(str).str.replace(r'\.0$', '', regex=True)

    if not ngs_pass.empty:
        latest = ngs_pass[ngs_pass['week'] == ngs_pass['week'].max()]
        if 'cpoe' in latest.columns:
            merged = latest.merge(ids[['gsis_id', 'sleeper_id']], left_on='player_gsis_id', right_on='gsis_id')
            for _, row in merged.iterrows():
                ngs_stats[row['sleeper_id']] = {'cpoe': row['cpoe'], 'air_yards': row.get('air_yards', 0)}
    
    if not ngs_rush.empty:
        latest = ngs_rush[ngs_rush['week'] == ngs_rush['week'].max()]
        merged = latest.merge(ids[['gsis_id', 'sleeper_id']], left_on='player_gsis_id', right_on='gsis_id')
        for _, row in merged.iterrows():
            if row['sleeper_id'] not in ngs_stats: ngs_stats[row['sleeper_id']] = {}
            if 'ryoe' in row: ngs_stats[row['sleeper_id']]['ryoe'] = row['ryoe']

    if not ngs_rec.empty:
        latest = ngs_rec[ngs_rec['week'] == ngs_rec['week'].max()]
        merged = latest.merge(ids[['gsis_id', 'sleeper_id']], left_on='player_gsis_id', right_on='gsis_id')
        for _, row in merged.iterrows():
             if row['sleeper_id'] not in ngs_stats: ngs_stats[row['sleeper_id']] = {}
             if 'avg_sep' in row: ngs_stats[row['sleeper_id']]['avg_sep'] = row['avg_sep']

    # Master Merge
    master_stats = {}
    all_ids = set(vol_stats.keys()) | set(pbp_stats.keys()) | set(ngs_stats.keys())
    for i in all_ids:
        master_stats[i] = {}
        if i in vol_stats: master_stats[i].update(vol_stats[i])
        if i in pbp_stats: master_stats[i].update(pbp_stats[i])
        if i in ngs_stats: master_stats[i].update(ngs_stats[i])

    st.write(f"### Week {curr_week} Matchups")
    matchups = get_matchups(league_id, curr_week)
    
    games = {}
    for m in matchups:
        if m['matchup_id'] not in games: games[m['matchup_id']] = []
        games[m['matchup_id']].append(m)

    for mid, teams in games.items():
        if len(teams) != 2: continue
        col1, col2 = st.columns(2)
        prompt_data = []
        
        for i, (col, team) in enumerate(zip([col1, col2], teams)):
            with col:
                rid = team['roster_id']
                oid = roster_owner_map.get(rid)
                manager = user_map.get(oid, 'Unknown')
                st.write(f"**{manager}**")
                
                starters = team['starters']
                roster_players = next((r['players'] for r in rosters if r['roster_id'] == rid), [])
                bench = list(set(roster_players) - set(starters))
                team_text = f"Manager: {manager}\n"

                for grp, p_ids in [("Starters", starters), ("Bench", bench)]:
                    if grp == "Bench": 
                        st.markdown("---")
                        st.caption("Bench")
                    
                    for pid in p_ids:
                        pid = str(pid).replace('.0', '')
                        stats = master_stats.get(pid, {})
                        
                        # Defense Lookup
                        if not stats:
                            p_info = all_players.get(pid, {})
                            if p_info.get('position') == 'DEF':
                                abbr = p_info.get('team')
                                stats = master_stats.get(abbr, {})
                                if not stats and abbr == 'JAX': stats = master_stats.get('JAC', {})

                        vol = stats.get('vol', 0)
                        avg = stats.get('avg_pts', 0)
                        act = team['players_points'].get(pid, 0)
                        pos = stats.get('position', all_players.get(pid, {}).get('position', 'UNK'))
                        name = all_players.get(pid, {}).get('full_name', f'Player {pid}')

                        metrics = []
                        if pos == 'QB':
                            if 'epa' in stats: metrics.append(f"EPA: {stats['epa']:.2f}")
                            if 'cpoe' in stats: metrics.append(f"CPOE: {stats['cpoe']:.1f}%")
                        elif pos == 'RB':
                            if 'ryoe' in stats: metrics.append(f"RYOE: {stats['ryoe']:.1f}")
                            if 'rz_touches' in stats: metrics.append(f"RZ: {stats['rz_touches']:.0f}")
                        elif pos in ['WR', 'TE']:
                            if 'wopr_proxy' in stats: metrics.append(f"WOPR: {stats['wopr_proxy']:.1f}")
                            if 'avg_sep' in stats: metrics.append(f"Sep: {stats['avg_sep']:.1f}")
                        elif pos == 'DEF':
                            if 'epa_allowed' in stats: metrics.append(f"EPA All: {stats['epa_allowed']:.2f}")
                            if 'sack_rate' in stats: metrics.append(f"Sack%: {stats['sack_rate']*100:.1f}%")
                        elif pos == 'K':
                            if 'longest_fg_made' in stats: metrics.append(f"Long: {stats['longest_fg_made']:.0f}")
                            if 'fg_percentage' in stats: metrics.append(f"FG%: {stats['fg_percentage']:.0f}%")

                        metrics.append(f"Vol: {vol:.0f}")
                        metric_str = " | ".join(metrics)
                        act_fmt = f":green[{act:.1f}]" if act > avg else f"{act:.1f}"
                        line = f"**{name}** ({metric_str} | Avg: {avg:.1f} | Act: {act_fmt})"
                        
                        if grp == "Bench": st.caption(line)
                        else: 
                            st.write(line)
                            team_text += f"{name} ({pos}): {metric_str}, Act: {act}\n"
                
                prompt_data.append(team_text)

        if st.button("Analyze Matchup", key=mid):
            if google_api_key:
                try:
                    model = genai.GenerativeModel("gemini-2.5-flash")
                    prompt = f"""Analyze this Week {curr_week} fantasy matchup. 
                    
CRITICAL RULES:
1. If a player has 0.0 Actual Points (Act), their game has NOT started yet. Do NOT call them 'unlucky' or a 'bust'. IGNORE their lack of points in your winner prediction.
2. Limit your response to UNDER 150 words. Be punchy and concise.
3. Structure your response with ONLY these two sections:
   - Winner Prediction: (Pick one team and explain why in 2-3 sentences)
   - Key Mismatch: (Identify the biggest advantage one team has in 1-2 sentences)

Focus on volume (Vol) and efficiency stats (EPA, WOPR, CPOE, RYOE).

{prompt_data[0]} 

VS 

{prompt_data[1]}"""
                    resp = model.generate_content(prompt)
                    st.success(resp.text)
                    save_prediction(curr_week, mid, user_map.get(roster_owner_map.get(teams[0]['roster_id'])), user_map.get(roster_owner_map.get(teams[1]['roster_id'])), resp.text)
                    st.toast("Saved to History!")
                except Exception as e:
                    st.error(f"AI Error: {e}")

with st.expander("📜 History"):
    try:
        with sqlite3.connect(DATABASE_NAME) as conn:
            df = pd.read_sql("SELECT * FROM predictions ORDER BY id DESC LIMIT 5", conn)
            st.dataframe(df)
    except: st.write("No history yet.")

with status_placeholder.container():
    with st.sidebar.expander("System Status", expanded=True):
        for k, v in st.session_state.data_health.items():
            st.write(f"{k}: {v}")