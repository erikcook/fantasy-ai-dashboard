import streamlit as st
import requests
import pandas as pd
import google.generativeai as genai
import datetime
import nflreadpy as nfl

if 'data_health' not in st.session_state:
    st.session_state.data_health = {'Sleeper API': 'Pending', 'NFL Play-by-Play': 'Pending', 'Next Gen Stats': 'Pending'}

league_id = st.sidebar.text_input('League ID', '1217902363445043200')

# Secrets Handling for Google API Key
if "GOOGLE_API_KEY" in st.secrets:
    google_api_key = st.secrets["GOOGLE_API_KEY"]
    st.sidebar.success("Google API Key loaded from secrets!")
else:
    google_api_key = st.sidebar.text_input('Google API Key', type='password')

if google_api_key:
    try:
        genai.configure(api_key=google_api_key)
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        st.sidebar.expander("Available Models").write(models)
    except Exception as e:
        st.sidebar.error(f"Key Error: {e}")

# System Status Display - Replaced with Placeholder for Lazy Sidebar Fix
status_placeholder = st.sidebar.empty()

def get_league_users(league_id):
    url = f"https://api.sleeper.app/v1/league/{league_id}/users"
    response = requests.get(url)
    return response.json()

def get_league_rosters(league_id):
    url = f"https://api.sleeper.app/v1/league/{league_id}/rosters"
    response = requests.get(url)
    return response.json()

@st.cache_data
def get_all_players():
    url = "https://api.sleeper.app/v1/players/nfl"
    response = requests.get(url)
    return response.json()

def get_current_week(league_id):
    url = f"https://api.sleeper.app/v1/state/nfl"
    response = requests.get(url)
    return response.json()['week']

def get_matchups(league_id, week):
    url = f"https://api.sleeper.app/v1/league/{league_id}/matchups/{week}"
    response = requests.get(url)
    if response.status_code == 200:
        st.session_state.data_health['Sleeper API'] = '✅ Online'
        return response.json()
    else:
        st.session_state.data_health['Sleeper API'] = '❌ Failed'
        return []

@st.cache_data
def get_player_positions(all_players_data):
    positions = {}
    for player_id, player_data in all_players_data.items():
        positions[player_id] = player_data.get('position', 'UNK')
    return positions

@st.cache_data
def get_ngs_data(season):
    ngs_passing = pd.DataFrame()
    ngs_rushing = pd.DataFrame()
    ngs_receiving = pd.DataFrame()
    try:
        ngs_passing = nfl.load_nextgen_stats(seasons=[season], stat_type='passing').to_pandas()
        ngs_rushing = nfl.load_nextgen_stats(seasons=[season], stat_type='rushing').to_pandas()
        ngs_receiving = nfl.load_nextgen_stats(seasons=[season], stat_type='receiving').to_pandas()

        # Check for critical columns: player_display_name and week
        for df, name in [(ngs_passing, 'passing'), (ngs_rushing, 'rushing'), (ngs_receiving, 'receiving')]:
            if df.empty:
                continue # If dataframe is empty, no need to check columns, it's valid empty
            if not all(col in df.columns for col in ['player_display_name', 'week']):
                # st.session_state.data_health['Next Gen Stats'] = f'❌ Failed (Missing columns in NGS {name} data)'
                st.toast(f'Next Gen Stats {name} data failed to load due to missing columns.')
                # Return empty dataframes for consistency
                return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        # st.session_state.data_health['Next Gen Stats'] = '✅ Online'
        return ngs_passing, ngs_rushing, ngs_receiving
    except Exception as e:
        st.toast(f'Next Gen Stats failed to load: {e}. Using standard stats.')
        # st.session_state.data_health['Next Gen Stats'] = '⚠️ Offline (Using Standard Stats)'
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

@st.cache_data
def get_pbp_advanced_stats(season):
    try:
        pbp_df = nfl.load_pbp(seasons=[season]).to_pandas()
        ids_df = nfl.load_ff_playerids().to_pandas()
        # Fix for '0-Stats bug' (Brian Thomas Fix): Clean sleeper_id immediately after loading
        ids_df['sleeper_id'] = ids_df['sleeper_id'].astype(str).str.replace(r'\.0$', '', regex=True)

        # Check for critical columns: epa, air_yards
        if not all(col in pbp_df.columns for col in ['epa', 'passer_player_id']):
            st.session_state.data_health['NFL Play-by-Play'] = '❌ Failed (Missing columns in Play-by-Play data)'
            st.toast("Critical Error: 'epa' or 'air_yards' column not found in Play-by-Play data. Check nflreadpy version.")
            return {}
        
        # Filter for recent weeks in Play-by-Play data
        max_week_pbp = pbp_df['week'].max() if not pbp_df.empty else 0
        pbp_filtered_df = pbp_df[pbp_df['week'] >= max_week_pbp - 2]

        advanced_stats = {}

        # QB Stats (EPA & Air Yards)
        if not pbp_filtered_df.empty:
            qb_stats = pbp_filtered_df.groupby('passer_player_id').agg(
                avg_epa=('epa', 'mean'),
            ).reset_index()
            merged_qb = qb_stats.merge(ids_df[['gsis_id', 'sleeper_id']], left_on='passer_player_id', right_on='gsis_id', how='inner')
            for _, row in merged_qb.iterrows():
                advanced_stats[row['sleeper_id']] = {'epa': row['avg_epa']}

        # Add RB Logic (Red Zone Touches)
        if not pbp_filtered_df.empty:
            rz_pbp_df = pbp_filtered_df[pbp_filtered_df['yardline_100'] <= 20]
            if not rz_pbp_df.empty:
                # Count red zone opportunities
                rz_opportunities = []
                for _, play in rz_pbp_df.iterrows():
                    if play['play_type'] == 'run' and play['rusher_player_id']:
                        rz_opportunities.append({'player_id': play['rusher_player_id'], 'rz_touch': 1})
                    elif play['play_type'] == 'pass' and play['receiver_player_id']:
                        rz_opportunities.append({'player_id': play['receiver_player_id'], 'rz_touch': 1})
                
                if rz_opportunities:
                    rz_df = pd.DataFrame(rz_opportunities)
                    rb_rz_stats = rz_df.groupby('player_id').agg(
                        rz_touches=('rz_touch', 'sum')
                    ).reset_index()
                    merged_rb_rz = rb_rz_stats.merge(ids_df[['gsis_id', 'sleeper_id']], left_on='player_id', right_on='gsis_id', how='inner')
                    for _, row in merged_rb_rz.iterrows():
                        if row['sleeper_id'] in advanced_stats:
                            advanced_stats[row['sleeper_id']]['rz_touches'] = row['rz_touches']
                        else:
                            advanced_stats[row['sleeper_id']] = {'rz_touches': row['rz_touches']}

        # Add WR/TE Logic (WOPR_Proxy)
        if not pbp_filtered_df.empty:
            wr_te_pbp_df = pbp_filtered_df[pbp_filtered_df['play_type'] == 'pass'][['receiver_player_id', 'play_id', 'air_yards', 'epa']].dropna(subset=['receiver_player_id'])
            if not wr_te_pbp_df.empty:
                wr_te_stats_pbp = wr_te_pbp_df.groupby('receiver_player_id').agg(
                    targets=('play_id', 'count'),
                    total_air_yards=('air_yards', 'sum'),
                    avg_epa=('epa', 'mean')
                ).reset_index()

                # Calculate WOPR_Proxy
                wr_te_stats_pbp['wopr_proxy'] = 1.5 * wr_te_stats_pbp['targets'] + 0.7 * (wr_te_stats_pbp['total_air_yards'] / 10)
                wr_te_stats_pbp.rename(columns={'receiver_player_id': 'player_id'}, inplace=True)
                merged_wr_te_pbp = wr_te_stats_pbp.merge(ids_df[['gsis_id', 'sleeper_id']], left_on='player_id', right_on='gsis_id', how='inner')

                for _, row in merged_wr_te_pbp.iterrows():
                    if row['sleeper_id'] in advanced_stats:
                        advanced_stats[row['sleeper_id']].update({
                            'wopr_proxy': row['wopr_proxy'],
                            'pbp_epa': row['avg_epa'] # Store PBP EPA separately for WR/TE if needed
                        })
                    else:
                        advanced_stats[row['sleeper_id']] = {
                            'wopr_proxy': row['wopr_proxy'],
                            'pbp_epa': row['avg_epa']
                        }

        # st.session_state.data_health['NFL Play-by-Play'] = '✅ Online'
        return advanced_stats

    except Exception as e:
        st.toast(f'NFL Play-by-Play data failed to load: {e}. Using standard stats.')
        # st.session_state.data_health['NFL Play-by-Play'] = '❌ Failed'
        return {}


@st.cache_data
def get_volume_stats_v2(current_week):
    stats_df = nfl.load_player_stats(seasons=[2025]).to_pandas()
    ids_df = nfl.load_ff_playerids().to_pandas()

    merged_df = stats_df.merge(ids_df[['gsis_id', 'sleeper_id']], left_on='player_id', right_on='gsis_id', how='inner')

    # Force sleeper_id to be string and clean float-like strings
    merged_df['sleeper_id'] = merged_df['sleeper_id'].astype(str).str.replace(r'\.0$', '', regex=True)

    columns_to_keep = ['sleeper_id', 'week', 'targets', 'carries', 'attempts', 'fantasy_points_ppr']
    
    # Check for critical columns and set status
    missing_cols = [col for col in columns_to_keep if col not in merged_df.columns]
    if missing_cols:
        # st.session_state.data_health['NFL Play-by-Play'] = f'❌ Failed (Missing columns in Volume stats: {", ".join(missing_cols)})'
        return {}

    merged_df = merged_df[columns_to_keep]

    for col in ['targets', 'carries', 'attempts', 'fantasy_points_ppr']:
        merged_df[col] = merged_df[col].fillna(0)

    merged_df['opportunity'] = merged_df['targets'] + merged_df['carries'] + merged_df['attempts']

    max_week = merged_df['week'].max()
    filtered_df = merged_df[merged_df['week'] >= max_week - 2]

    grouped_stats = filtered_df.groupby('sleeper_id').agg(
        avg_vol=('opportunity', 'mean'),
        avg_pts=('fantasy_points_ppr', 'mean'),
        avg_pass_attempts=('attempts', 'mean'),
        avg_rush_targets=('targets', 'mean'),
        avg_carries=('carries', 'mean')
    ).to_dict(orient='index')
    
    # Reformat to {sleeper_id: {'vol': avg_vol, 'avg_pts': avg_pts, 'pass': avg_pass, 'rush': avg_rush}}
    formatted_stats = {}
    for s_id, data in grouped_stats.items():
        formatted_stats[s_id] = {
            'vol': data['avg_vol'],
            'avg_pts': data['avg_pts'],
            'pass': data['avg_pass_attempts'],
            'rush': data['avg_rush_targets'] + data['avg_carries']
        }

    print("Sample Keys:", list(formatted_stats.keys())[:5]) # Debug Helper
    # st.session_state.data_health['NFL Play-by-Play'] = '✅ Online'

    return formatted_stats

if league_id:
    st.write(f"Fetching users for League ID: {league_id}")
    users_data = get_league_users(league_id)
    rosters_data = get_league_rosters(league_id)

    # Create a mapping from user_id to display_name
    user_name_map = {user['user_id']: user['display_name'] for user in users_data}

    # Prepare data for DataFrame
    leaderboard_data = []
    for roster in rosters_data:
        owner_id = roster['owner_id']
        manager_name = user_name_map.get(owner_id, "Unknown Manager")
        wins = roster['settings']['wins']
        losses = roster['settings']['losses']
        total_fpts = roster['settings']['fpts']
        leaderboard_data.append({
            'Manager Name': manager_name,
            'Wins': wins,
            'Losses': losses,
            'Total FPTS': total_fpts
        })

    # Create DataFrame
    df = pd.DataFrame(leaderboard_data)

    # Sort by Total FPTS for leaderboard effect
    df = df.sort_values(by='Total FPTS', ascending=False).reset_index(drop=True)

    st.dataframe(df)

    current_week = get_current_week(league_id)
    st.write(f"## Week {current_week} Matchups")

    all_players = get_all_players()
    player_id_to_name = {player_id: player_data['full_name'] for player_id, player_data in all_players.items() if 'full_name' in player_data}
    player_positions = get_player_positions(all_players)

    # Fetch and update status for Volume Stats
    volume_stats_data = get_volume_stats_v2(current_week)
    if volume_stats_data:
        st.session_state.data_health['NFL Play-by-Play'] = '✅ Online'
    else:
        st.session_state.data_health['NFL Play-by-Play'] = '❌ Failed'

    # Fetch and update status for NGS Data
    ngs_passing_raw, ngs_rushing_raw, ngs_receiving_raw = get_ngs_data(season=2025)
    if not ngs_passing_raw.empty or not ngs_rushing_raw.empty or not ngs_receiving_raw.empty:
        st.session_state.data_health['Next Gen Stats'] = '✅ Online'
    else:
        st.session_state.data_health['Next Gen Stats'] = '⚠️ Offline (Using Standard Stats)'

    # Fetch and update status for Play-by-Play Advanced Stats
    pbp_advanced_stats = get_pbp_advanced_stats(season=2025)
    if pbp_advanced_stats:
        st.session_state.data_health['NFL Play-by-Play'] = '✅ Online'
    else:
        st.session_state.data_health['NFL Play-by-Play'] = '❌ Failed'

    # Calculate NGS stats from raw dataframes and merge them
    ngs_advanced_stats = {}
    ids_df = nfl.load_ff_playerids().to_pandas()
    # Apply ID cleaning to ids_df in the main block too
    ids_df['sleeper_id'] = ids_df['sleeper_id'].astype(str).str.replace(r'\.0$', '', regex=True)
    ids_df['gsis_id'] = ids_df['gsis_id'].astype(str).str.replace(r'\.0$', '', regex=True)

    if not ngs_passing_raw.empty:
        latest_week_passing = ngs_passing_raw['week'].max() if not ngs_passing_raw.empty else 0
        ngs_passing_filtered = ngs_passing_raw[ngs_passing_raw['week'] == latest_week_passing]
        if not ngs_passing_filtered.empty and 'cpoe' in ngs_passing_filtered.columns and 'air_yards' in ngs_passing_filtered.columns:
            qb_stats_ngs = ngs_passing_filtered.groupby('player_gsis_id').agg(
                avg_cpoe=('cpoe', 'mean'),
                sum_air_yards_ngs=('air_yards', 'sum')
            ).reset_index()
            merged_qb_ngs = qb_stats_ngs.merge(ids_df[['gsis_id', 'sleeper_id']], left_on='player_gsis_id', right_on='gsis_id', how='inner')
            for _, row in merged_qb_ngs.iterrows():
                ngs_advanced_stats[row['sleeper_id']] = {'cpoe': row['avg_cpoe'], 'air_yards': row['sum_air_yards_ngs']}

    if not ngs_rushing_raw.empty:
        latest_week_rushing = ngs_rushing_raw['week'].max() if not ngs_rushing_raw.empty else 0
        ngs_rushing_filtered = ngs_rushing_raw[ngs_rushing_raw['week'] == latest_week_rushing]
        if not ngs_rushing_filtered.empty and 'rush_yards_over_expected' in ngs_rushing_filtered.columns:
            rb_stats_ngs = ngs_rushing_filtered.groupby('player_gsis_id').agg(
                avg_ryoe=('rush_yards_over_expected', 'mean'),
            ).reset_index()
            merged_rb_ngs = rb_stats_ngs.merge(ids_df[['gsis_id', 'sleeper_id']], left_on='player_gsis_id', right_on='gsis_id', how='inner')
            for _, row in merged_rb_ngs.iterrows():
                if row['sleeper_id'] in ngs_advanced_stats:
                    ngs_advanced_stats[row['sleeper_id']]['ryoe'] = row['avg_ryoe']
                else:
                    ngs_advanced_stats[row['sleeper_id']] = {'ryoe': row['avg_ryoe']}
    
    if not ngs_receiving_raw.empty:
        latest_week_receiving = ngs_receiving_raw['week'].max() if not ngs_receiving_raw.empty else 0
        ngs_receiving_filtered = ngs_receiving_raw[ngs_receiving_raw['week'] == latest_week_receiving]
        if not ngs_receiving_filtered.empty and 'targets' in ngs_receiving_filtered.columns and 'air_yards' in ngs_receiving_filtered.columns and 'avg_separation' in ngs_receiving_filtered.columns:
            wr_te_stats_ngs = ngs_receiving_filtered.groupby('player_gsis_id').agg(
                avg_separation=('avg_separation', 'mean'),
            ).reset_index()

            merged_wr_te_ngs = wr_te_stats_ngs.merge(ids_df[['gsis_id', 'sleeper_id']], left_on='player_gsis_id', right_on='gsis_id', how='inner')
            for _, row in merged_wr_te_ngs.iterrows():
                if row['sleeper_id'] in ngs_advanced_stats:
                    ngs_advanced_stats[row['sleeper_id']].update({
                        'avg_separation': row['avg_separation']
                    })
                else:
                    ngs_advanced_stats[row['sleeper_id']] = {
                        'avg_separation': row['avg_separation']
                    }

    # Merge all advanced stats
    merged_player_stats = {}
    all_player_ids = set(volume_stats_data.keys()).union(set(pbp_advanced_stats.keys())).union(set(ngs_advanced_stats.keys()))

    for p_id in all_player_ids:
        merged_player_stats[p_id] = {}
        if p_id in volume_stats_data:
            merged_player_stats[p_id].update(volume_stats_data[p_id])
        if p_id in pbp_advanced_stats:
            merged_player_stats[p_id].update(pbp_advanced_stats[p_id]) # pbp_advanced_stats now contains rz_touches
        if p_id in ngs_advanced_stats:
            merged_player_stats[p_id].update(ngs_advanced_stats[p_id]) # ngs_advanced_stats contains wopr, target_share, etc.

    matchups_data = get_matchups(league_id, current_week)

    # Group matchups by matchup_id
    matchup_groups = {}
    for matchup in matchups_data:
        matchup_id = matchup['matchup_id']
        if matchup_id not in matchup_groups:
            matchup_groups[matchup_id] = []
        matchup_groups[matchup_id].append(matchup)

    for matchup_id, teams in matchup_groups.items():
        if len(teams) == 2:
            col1, col2 = st.columns(2)
            team_a = teams[0]
            team_b = teams[1]

            with col1:
                roster_id = team_a['roster_id']
                manager_a_name = "Unknown Manager"
                for user in users_data:
                    for roster in rosters_data:
                        if roster['roster_id'] == roster_id and roster['owner_id'] == user['user_id']:
                            manager_a_name = user['display_name']
                            break
                    if manager_a_name != "Unknown Manager":
                        break
                st.write(f"### {manager_a_name}")
                st.write("**Starters:**")
                for player_id in team_a['starters']:
                    clean_id = str(player_id).replace('.0', '')
                    player_stats = merged_player_stats.get(clean_id, {'vol': 0, 'avg_pts': 0, 'pass': 0, 'rush': 0, 'epa': 0, 'cpoe': 0, 'air_yards': 0, 'ryoe': 0, 'rz_touches': 0, 'wopr_proxy': 0, 'pbp_epa': 0, 'avg_separation': 0})
                    volume_val = player_stats['vol']
                    avg_pts_val = player_stats['avg_pts']
                    actual_pts = team_a['players_points'].get(player_id, 0)
                    position = player_positions.get(clean_id, 'UNK')

                    player_name_display = player_id_to_name.get(player_id, f'Player {player_id}')

                    # 'Pro' View Display Logic (Relaxed Conditions)
                    show_advanced_stats = False
                    if position == 'QB' and ('epa' in player_stats or 'cpoe' in player_stats or 'air_yards' in player_stats):
                        epa_str = f"EPA: {round(player_stats['epa'], 2)}" if 'epa' in player_stats and player_stats['epa'] is not None else ""
                        cpoe_str = f"CPOE: {round(player_stats['cpoe'], 2)}%" if 'cpoe' in player_stats and player_stats['cpoe'] is not None else ""
                        vol_str = f"Vol: {player_stats['vol']:.0f}" if 'vol' in player_stats and player_stats['vol'] is not None else ""
                        display_parts = list(filter(None, [epa_str, cpoe_str, vol_str]))
                        if display_parts:
                            st.write(f"**{player_name_display}** ({" | ".join(display_parts)})")
                            show_advanced_stats = True
                    elif position == 'RB' and ('ryoe' in player_stats or 'rz_touches' in player_stats):
                        ryoe_str = f"RYOE: {round(player_stats['ryoe'], 1)}" if 'ryoe' in player_stats and player_stats['ryoe'] is not None else ""
                        rz_str = f"RZ: {player_stats['rz_touches']:.0f}" if 'rz_touches' in player_stats and player_stats['rz_touches'] is not None else ""
                        vol_str = f"Vol: {player_stats['vol']:.0f}" if 'vol' in player_stats and player_stats['vol'] is not None else ""
                        display_parts = list(filter(None, [ryoe_str, rz_str, vol_str]))
                        if display_parts:
                            st.write(f"**{player_name_display}** ({" | ".join(display_parts)})")
                            show_advanced_stats = True
                    elif position in ['WR', 'TE'] and ('wopr_proxy' in player_stats or 'pbp_epa' in player_stats or 'avg_separation' in player_stats):
                        wopr_str = f"WOPR: {round(player_stats['wopr_proxy'], 2)}" if 'wopr_proxy' in player_stats and player_stats['wopr_proxy'] is not None else ""
                        epa_str = f"EPA: {round(player_stats['pbp_epa'], 2)}" if 'pbp_epa' in player_stats and player_stats['pbp_epa'] is not None else ""
                        vol_str = f"Vol: {player_stats['vol']:.0f}" if 'vol' in player_stats and player_stats['vol'] is not None else ""
                        display_parts = list(filter(None, [wopr_str, epa_str, vol_str]))
                        if display_parts:
                            st.write(f"**{player_name_display}** ({" | ".join(display_parts)})")
                            show_advanced_stats = True
                    
                    if not show_advanced_stats: # Fallback to old format if advanced stats not displayed
                        actual_pts_display = f":green[{actual_pts:.1f}]" if actual_pts > avg_pts_val else f"{actual_pts:.1f}"
                        st.write(f"**{player_name_display}** (Vol: {volume_val:.1f} | Avg: {avg_pts_val:.1f} | Act: {actual_pts_display})")

                # Calculate and display bench players for Team A
                st.markdown("<!-- -->") # Divider
                st.write("**Bench:**")
                team_a_roster = next((r['players'] for r in rosters_data if r['roster_id'] == roster_id), [])
                team_a_bench_players = [p_id for p_id in team_a_roster if p_id not in team_a['starters']]
                for player_id in team_a_bench_players:
                    clean_id = str(player_id).replace('.0', '')
                    player_stats = merged_player_stats.get(clean_id, {'vol': 0, 'avg_pts': 0, 'pass': 0, 'rush': 0, 'epa': 0, 'cpoe': 0, 'air_yards': 0, 'ryoe': 0, 'rz_touches': 0, 'wopr_proxy': 0, 'pbp_epa': 0, 'avg_separation': 0})
                    volume_val = player_stats['vol']
                    avg_pts_val = player_stats['avg_pts']
                    actual_pts = team_a['players_points'].get(player_id, 0)
                    position = player_positions.get(clean_id, 'UNK')

                    player_name_display = player_id_to_name.get(player_id, f'Player {player_id}')

                    show_advanced_stats_bench = False
                    if position == 'QB' and ('epa' in player_stats or 'cpoe' in player_stats or 'air_yards' in player_stats):
                        epa_str = f"EPA: {round(player_stats['epa'], 2)}" if 'epa' in player_stats and player_stats['epa'] is not None else ""
                        cpoe_str = f"CPOE: {round(player_stats['cpoe'], 2)}%" if 'cpoe' in player_stats and player_stats['cpoe'] is not None else ""
                        vol_str = f"Vol: {player_stats['vol']:.0f}" if 'vol' in player_stats and player_stats['vol'] is not None else ""
                        display_parts = list(filter(None, [epa_str, cpoe_str, vol_str]))
                        if display_parts:
                            st.markdown(f"<small>**{player_name_display}** ({" | ".join(display_parts)})</small>", unsafe_allow_html=True)
                            show_advanced_stats_bench = True
                    elif position == 'RB' and ('ryoe' in player_stats or 'rz_touches' in player_stats):
                        ryoe_str = f"RYOE: {round(player_stats['ryoe'], 1)}" if 'ryoe' in player_stats and player_stats['ryoe'] is not None else ""
                        rz_str = f"RZ: {player_stats['rz_touches']:.0f}" if 'rz_touches' in player_stats and player_stats['rz_touches'] is not None else ""
                        vol_str = f"Vol: {player_stats['vol']:.0f}" if 'vol' in player_stats and player_stats['vol'] is not None else ""
                        display_parts = list(filter(None, [ryoe_str, rz_str, vol_str]))
                        if display_parts:
                            st.markdown(f"<small>**{player_name_display}** ({" | ".join(display_parts)})</small>", unsafe_allow_html=True)
                            show_advanced_stats_bench = True
                    elif position in ['WR', 'TE'] and ('wopr_proxy' in player_stats or 'pbp_epa' in player_stats or 'avg_separation' in player_stats):
                        wopr_str = f"WOPR: {round(player_stats['wopr_proxy'], 2)}" if 'wopr_proxy' in player_stats and player_stats['wopr_proxy'] is not None else ""
                        epa_str = f"EPA: {round(player_stats['pbp_epa'], 2)}" if 'pbp_epa' in player_stats and player_stats['pbp_epa'] is not None else ""
                        vol_str = f"Vol: {player_stats['vol']:.0f}" if 'vol' in player_stats and player_stats['vol'] is not None else ""
                        display_parts = list(filter(None, [wopr_str, epa_str, vol_str]))
                        if display_parts:
                            st.markdown(f"<small>**{player_name_display}** ({" | ".join(display_parts)})</small>", unsafe_allow_html=True)
                            show_advanced_stats_bench = True
                    
                    if not show_advanced_stats_bench: # Fallback to old format if advanced stats not displayed
                        st.markdown(f"<small>**{player_id_to_name.get(player_id, f'Player {player_id}')}** (Vol: {volume_val:.1f} | Avg: {avg_pts_val:.1f} | Act: {actual_pts:.1f})</small>", unsafe_allow_html=True)

            with col2:
                roster_b_id = team_b['roster_id']
                manager_b_name = "Unknown Manager"
                for user in users_data:
                    for roster in rosters_data:
                        if roster['roster_id'] == roster_b_id and roster['owner_id'] == user['user_id']:
                            manager_b_name = user['display_name']
                            break
                    if manager_b_name != "Unknown Manager":
                        break
                st.write(f"### {manager_b_name}")
                st.write("**Starters:**")
                for player_id in team_b['starters']:
                    clean_id = str(player_id).replace('.0', '')
                    player_stats = merged_player_stats.get(clean_id, {'vol': 0, 'avg_pts': 0, 'pass': 0, 'rush': 0, 'epa': 0, 'cpoe': 0, 'air_yards': 0, 'ryoe': 0, 'rz_touches': 0, 'wopr_proxy': 0, 'pbp_epa': 0, 'avg_separation': 0})
                    volume_val = player_stats['vol']
                    avg_pts_val = player_stats['avg_pts']
                    actual_pts = team_b['players_points'].get(player_id, 0)
                    position = player_positions.get(clean_id, 'UNK')

                    player_name_display = player_id_to_name.get(player_id, f'Player {player_id}')

                    # 'Pro' View Display Logic (Relaxed Conditions)
                    show_advanced_stats = False
                    if position == 'QB' and ('epa' in player_stats or 'cpoe' in player_stats or 'air_yards' in player_stats):
                        epa_str = f"EPA: {round(player_stats['epa'], 2)}" if 'epa' in player_stats and player_stats['epa'] is not None else ""
                        cpoe_str = f"CPOE: {round(player_stats['cpoe'], 2)}%" if 'cpoe' in player_stats and player_stats['cpoe'] is not None else ""
                        vol_str = f"Vol: {player_stats['vol']:.0f}" if 'vol' in player_stats and player_stats['vol'] is not None else ""
                        display_parts = list(filter(None, [epa_str, cpoe_str, vol_str]))
                        if display_parts:
                            st.write(f"**{player_name_display}** ({" | ".join(display_parts)})")
                            show_advanced_stats = True
                    elif position == 'RB' and ('ryoe' in player_stats or 'rz_touches' in player_stats):
                        ryoe_str = f"RYOE: {round(player_stats['ryoe'], 1)}" if 'ryoe' in player_stats and player_stats['ryoe'] is not None else ""
                        rz_str = f"RZ: {player_stats['rz_touches']:.0f}" if 'rz_touches' in player_stats and player_stats['rz_touches'] is not None else ""
                        vol_str = f"Vol: {player_stats['vol']:.0f}" if 'vol' in player_stats and player_stats['vol'] is not None else ""
                        display_parts = list(filter(None, [ryoe_str, rz_str, vol_str]))
                        if display_parts:
                            st.write(f"**{player_name_display}** ({" | ".join(display_parts)})")
                            show_advanced_stats = True
                    elif position in ['WR', 'TE'] and ('wopr_proxy' in player_stats or 'pbp_epa' in player_stats or 'avg_separation' in player_stats):
                        wopr_str = f"WOPR: {round(player_stats['wopr_proxy'], 2)}" if 'wopr_proxy' in player_stats and player_stats['wopr_proxy'] is not None else ""
                        epa_str = f"EPA: {round(player_stats['pbp_epa'], 2)}" if 'pbp_epa' in player_stats and player_stats['pbp_epa'] is not None else ""
                        vol_str = f"Vol: {player_stats['vol']:.0f}" if 'vol' in player_stats and player_stats['vol'] is not None else ""
                        display_parts = list(filter(None, [wopr_str, epa_str, vol_str]))
                        if display_parts:
                            st.write(f"**{player_name_display}** ({" | ".join(display_parts)})")
                            show_advanced_stats = True
                    
                    if not show_advanced_stats: # Fallback to old format if advanced stats not displayed
                        actual_pts_display = f":green[{actual_pts:.1f}]" if actual_pts > avg_pts_val else f"{actual_pts:.1f}"
                        st.write(f"**{player_name_display}** (Vol: {volume_val:.1f} | Avg: {avg_pts_val:.1f} | Act: {actual_pts_display})")

                # Calculate and display bench players for Team B
                st.markdown("<!-- -->") # Divider
                st.write("**Bench:**")
                team_b_roster = next((r['players'] for r in rosters_data if r['roster_id'] == roster_b_id), [])
                team_b_bench_players = [p_id for p_id in team_b_roster if p_id not in team_b['starters']]
                for player_id in team_b_bench_players:
                    clean_id = str(player_id).replace('.0', '')
                    player_stats = merged_player_stats.get(clean_id, {'vol': 0, 'avg_pts': 0, 'pass': 0, 'rush': 0, 'epa': 0, 'cpoe': 0, 'air_yards': 0, 'ryoe': 0, 'rz_touches': 0, 'wopr_proxy': 0, 'pbp_epa': 0, 'avg_separation': 0})
                    volume_val = player_stats['vol']
                    avg_pts_val = player_stats['avg_pts']
                    actual_pts = team_b['players_points'].get(player_id, 0)
                    position = player_positions.get(clean_id, 'UNK')

                    player_name_display = player_id_to_name.get(player_id, f'Player {player_id}')

                    show_advanced_stats_bench = False
                    if position == 'QB' and ('epa' in player_stats or 'cpoe' in player_stats or 'air_yards' in player_stats):
                        epa_str = f"EPA: {round(player_stats['epa'], 2)}" if 'epa' in player_stats and player_stats['epa'] is not None else ""
                        cpoe_str = f"CPOE: {round(player_stats['cpoe'], 2)}%" if 'cpoe' in player_stats and player_stats['cpoe'] is not None else ""
                        vol_str = f"Vol: {player_stats['vol']:.0f}" if 'vol' in player_stats and player_stats['vol'] is not None else ""
                        display_parts = list(filter(None, [epa_str, cpoe_str, vol_str]))
                        if display_parts:
                            st.markdown(f"<small>**{player_name_display}** ({" | ".join(display_parts)})</small>", unsafe_allow_html=True)
                            show_advanced_stats_bench = True
                    elif position == 'RB' and ('ryoe' in player_stats or 'rz_touches' in player_stats):
                        ryoe_str = f"RYOE: {round(player_stats['ryoe'], 1)}" if 'ryoe' in player_stats and player_stats['ryoe'] is not None else ""
                        rz_str = f"RZ: {player_stats['rz_touches']:.0f}" if 'rz_touches' in player_stats and player_stats['rz_touches'] is not None else ""
                        vol_str = f"Vol: {player_stats['vol']:.0f}" if 'vol' in player_stats and player_stats['vol'] is not None else ""
                        display_parts = list(filter(None, [ryoe_str, rz_str, vol_str]))
                        if display_parts:
                            st.markdown(f"<small>**{player_name_display}** ({" | ".join(display_parts)})</small>", unsafe_allow_html=True)
                            show_advanced_stats_bench = True
                    elif position in ['WR', 'TE'] and ('wopr_proxy' in player_stats or 'pbp_epa' in player_stats or 'avg_separation' in player_stats):
                        wopr_str = f"WOPR: {round(player_stats['wopr_proxy'], 2)}" if 'wopr_proxy' in player_stats and player_stats['wopr_proxy'] is not None else ""
                        epa_str = f"EPA: {round(player_stats['pbp_epa'], 2)}" if 'pbp_epa' in player_stats and player_stats['pbp_epa'] is not None else ""
                        vol_str = f"Vol: {player_stats['vol']:.0f}" if 'vol' in player_stats and player_stats['vol'] is not None else ""
                        display_parts = list(filter(None, [wopr_str, epa_str, vol_str]))
                        if display_parts:
                            st.markdown(f"<small>**{player_name_display}** ({" | ".join(display_parts)})</small>", unsafe_allow_html=True)
                            show_advanced_stats_bench = True
                    
                    if not show_advanced_stats_bench: # Fallback to old format if advanced stats not displayed
                        st.markdown(f"<small>**{player_id_to_name.get(player_id, f'Player {player_id}')}** (Vol: {volume_val:.1f} | Avg: {avg_pts_val:.1f} | Act: {actual_pts:.1f})</small>", unsafe_allow_html=True)

            # AI Analysis Button
            analyze_button_key = f"analyze_button_{matchup_id}"
            if st.button(f"Analyze {manager_a_name} vs {manager_b_name}", key=analyze_button_key):
                if google_api_key:
                    genai.configure(api_key=google_api_key)
                    model = genai.GenerativeModel("gemini-2.5-flash")

                    current_date = datetime.date.today().strftime('%B %d, %Y')

                    team_a_analysis_str = []
                    for player_id in team_a['starters']:
                        clean_id = str(player_id).replace('.0', '')
                        player_stats = merged_player_stats.get(clean_id, {'vol': 0, 'avg_pts': 0, 'pass': 0, 'rush': 0, 'epa': 0, 'cpoe': 0, 'air_yards': 0, 'ryoe': 0, 'rz_touches': 0, 'wopr_proxy': 0, 'pbp_epa': 0, 'avg_separation': 0})
                        volume_val = player_stats['vol']
                        avg_pts_val = player_stats['avg_pts']
                        actual_pts = team_a['players_points'].get(player_id, 0)
                        position = player_positions.get(clean_id, 'UNK')
                        
                        player_analysis_string = f"{player_id_to_name.get(player_id, f'Player {player_id}')} (Vol: {volume_val:.1f}, Avg: {avg_pts_val:.1f}, Act: {actual_pts:.1f})"

                        # Add advanced stats to AI prompt string
                        advanced_stats_parts = []
                        if position == 'QB':
                            if 'epa' in player_stats and player_stats['epa'] is not None: advanced_stats_parts.append(f"EPA: {player_stats['epa']:.2f}")
                            if 'cpoe' in player_stats and player_stats['cpoe'] is not None: advanced_stats_parts.append(f"CPOE: {player_stats['cpoe']:.2f}")
                            if 'air_yards' in player_stats and player_stats['air_yards'] is not None: advanced_stats_parts.append(f"AirYds: {player_stats['air_yards']:.0f}")
                        elif position == 'RB':
                            if 'ryoe' in player_stats and player_stats['ryoe'] is not None: advanced_stats_parts.append(f"RYOE: {player_stats['ryoe']:.1f}")
                            if 'rz_touches' in player_stats and player_stats['rz_touches'] is not None: advanced_stats_parts.append(f"RZ Touches: {player_stats['rz_touches']:.0f}")
                        elif position in ['WR', 'TE']:
                            if 'wopr_proxy' in player_stats and player_stats['wopr_proxy'] is not None: advanced_stats_parts.append(f"WOPR: {player_stats['wopr_proxy']:.2f}")
                            if 'pbp_epa' in player_stats and player_stats['pbp_epa'] is not None: advanced_stats_parts.append(f"EPA: {player_stats['pbp_epa']:.2f}")
                            if 'avg_separation' in player_stats and player_stats['avg_separation'] is not None: advanced_stats_parts.append(f"Avg Sep: {player_stats['avg_separation']:.1f}")

                        if advanced_stats_parts:
                            player_analysis_string += f" ({', '.join(advanced_stats_parts)})"

                        team_a_analysis_str.append(player_analysis_string)

                    team_b_analysis_str = []
                    for player_id in team_b['starters']:
                        clean_id = str(player_id).replace('.0', '')
                        player_stats = merged_player_stats.get(clean_id, {'vol': 0, 'avg_pts': 0, 'pass': 0, 'rush': 0, 'epa': 0, 'cpoe': 0, 'air_yards': 0, 'ryoe': 0, 'rz_touches': 0, 'wopr_proxy': 0, 'pbp_epa': 0, 'avg_separation': 0})
                        volume_val = player_stats['vol']
                        avg_pts_val = player_stats['avg_pts']
                        actual_pts = team_b['players_points'].get(player_id, 0)
                        position = player_positions.get(clean_id, 'UNK')

                        player_analysis_string = f"{player_id_to_name.get(player_id, f'Player {player_id}')} (Vol: {volume_val:.1f}, Avg: {avg_pts_val:.1f}, Act: {actual_pts:.1f})"

                        # Add advanced stats to AI prompt string
                        advanced_stats_parts = []
                        if position == 'QB':
                            if 'epa' in player_stats and player_stats['epa'] is not None: advanced_stats_parts.append(f"EPA: {player_stats['epa']:.2f}")
                            if 'cpoe' in player_stats and player_stats['cpoe'] is not None: advanced_stats_parts.append(f"CPOE: {player_stats['cpoe']:.2f}")
                            if 'air_yards' in player_stats and player_stats['air_yards'] is not None: advanced_stats_parts.append(f"AirYds: {player_stats['air_yards']:.0f}")
                        elif position == 'RB':
                            if 'ryoe' in player_stats and player_stats['ryoe'] is not None: advanced_stats_parts.append(f"RYOE: {player_stats['ryoe']:.1f}")
                            if 'rz_touches' in player_stats and player_stats['rz_touches'] is not None: advanced_stats_parts.append(f"RZ Touches: {player_stats['rz_touches']:.0f}")
                        elif position in ['WR', 'TE']:
                            if 'wopr_proxy' in player_stats and player_stats['wopr_proxy'] is not None: advanced_stats_parts.append(f"WOPR: {player_stats['wopr_proxy']:.2f}")
                            if 'pbp_epa' in player_stats and player_stats['pbp_epa'] is not None: advanced_stats_parts.append(f"EPA: {player_stats['pbp_epa']:.2f}")
                            if 'avg_separation' in player_stats and player_stats['avg_separation'] is not None: advanced_stats_parts.append(f"Avg Sep: {player_stats['avg_separation']:.1f}")

                        if advanced_stats_parts:
                            player_analysis_string += f" ({', '.join(advanced_stats_parts)})"

                        team_b_analysis_str.append(player_analysis_string)

                    # Determine available advanced metrics for the prompt
                    available_advanced_metrics = []
                    if st.session_state.data_health.get('NFL Play-by-Play') == '✅ Online':
                        available_advanced_metrics.append("EPA")
                        available_advanced_metrics.append("RZ Touches") # From PBP
                        available_advanced_metrics.append("WOPR_Proxy") # From PBP
                    if st.session_state.data_health.get('Next Gen Stats') == '✅ Online':
                        if "CPOE" not in available_advanced_metrics: available_advanced_metrics.append("CPOE")
                        if "RYOE" not in available_advanced_metrics: available_advanced_metrics.append("RYOE")
                        if "Avg Separation" not in available_advanced_metrics: available_advanced_metrics.append("Avg Separation")

                    prompt_advanced_metrics_str = ", and advanced metrics like " + ", ".join(available_advanced_metrics) + "." if available_advanced_metrics else "."

                    # Construct prompt advanced logic based on available data
                    prompt_advanced_logic = []
                    if 'WOPR_Proxy' in available_advanced_metrics: prompt_advanced_logic.append("Use WOPR for WRs to judge volume.")
                    if 'EPA' in available_advanced_metrics: prompt_advanced_logic.append("Use EPA for QBs and WR/TEs to judge efficiency.")
                    if 'CPOE' in available_advanced_metrics: prompt_advanced_logic.append("Use CPOE for QBs to judge accuracy.")
                    if 'RYOE' in available_advanced_metrics: prompt_advanced_logic.append("Use RYOE for RBs to judge running back talent independent of blocking.")
                    if 'RZ Touches' in available_advanced_metrics: prompt_advanced_logic.append("Use RZ Touches for RBs to judge touchdown upside.")
                    if 'Avg Separation' in available_advanced_metrics: prompt_advanced_logic.append("Use Avg Separation for WRs to judge route running and ability to get open.")

                    full_prompt_advanced_logic = "\n".join(prompt_advanced_logic)

                    prompt_intro = f"Act as a data-driven fantasy expert. Today is {current_date}. We are in the 2025 NFL Season. I will give you two rosters with their Volume (Vol), 3-Week Average (Avg), and Current Score (Act){prompt_advanced_metrics_str}"

                    prompt_context = """
CRITICAL CONTEXT: If a player has Actual Score (Act) of 0 (or near 0), assume their game has NOT started yet. Do NOT call them "unlucky" or a "bust". Simply ignore them or mention they are yet to play. Only use terms like "unlucky" if Act is low but Vol is high AND the game seems finished. Logic:\nHigh Vol + Low Act = "Unlucky / Buy Low"\nLow Vol + High Act = "Lucky / Sell High"
"""

                    prompt_analysis_rules = f"{full_prompt_advanced_logic}\nCompare the two teams based on these metrics. Keep the analysis punchy and under 100 words."
                    
                    # Fix: Join the lists into variables outside the f-string
                    team_a_text = "\n".join(team_a_analysis_str)
                    team_b_text = "\n".join(team_b_analysis_str)
                    prompt_teams_data = f"Team A (Starters: {team_a_text})\nTeam B (Starters: {team_b_text})"

                    prompt = f"{prompt_intro}\n{prompt_context}\n{prompt_analysis_rules}\n\n{prompt_teams_data}"

                    try:
                        response = model.generate_content(prompt)
                        st.success(response.text)
                    except Exception as e:
                        st.error(f"Error generating analysis: {e}")
                else:
                    st.warning("Please enter your Google API Key in the sidebar to get AI analysis.")

else:
    st.write("Please enter a League ID in the sidebar.")

    # Display the system status in the placeholder at the end of the script for 'Instant Feedback' Fix
    with status_placeholder.container():
        with st.sidebar.expander("🔌 System Status", expanded=True):
            for source, status in st.session_state.data_health.items():
                st.write(f"{source}: {status}")
