import streamlit as st
import pandas as pd
import os
import csv
import requests
import random
import re
import datetime
import base64
import shutil
import time
import io
import numpy as np
import urllib.parse
import hashlib
import plotly.express as px
from collections import Counter
import plotly.graph_objects as go
from scipy.integrate import odeint
from scipy.optimize import minimize
from datetime import datetime

# --- 1. 設定・パス関連 ---
LOGIN_FILE = "assets/spread_data/login_data.csv"
USERS_BASE_DIR = "assets/users"
SYSTEM_REQUEST_FILE = "assets/spread_data/system_requests.csv"
ASSETS_DIR = "assets"
IN_DATA_DIR = "assets/spread_data"
OUT_DATA_DIR = "assets/drive_data"
SPREAD_DIR = os.path.join(ASSETS_DIR, "spread_data")
USERS_DIR = os.path.join(ASSETS_DIR, "users")
TASK_CSV = os.path.join(SPREAD_DIR, "task_list.csv")
LOGIN_CSV = os.path.join(SPREAD_DIR, "login_data.csv")
# フォルダが存在しない場合は作成
os.makedirs(USERS_BASE_DIR, exist_ok=True)
if not os.path.exists(LOGIN_FILE):
    with open(LOGIN_FILE, mode="w", encoding="utf_8_sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "password", "role", "level", "exp", "points"])

# ==========================================
#　githubと同期
# ==========================================
def github_sync_engine(local_path, mode="upload"):
    """GitHubリポジトリにないファイルを反映させるための最終回答"""
    try:
        if "GITHUB_TOKEN" not in st.secrets or "GITHUB_REPO" not in st.secrets:
            return False

        token = st.secrets["GITHUB_TOKEN"].strip()
        repo = st.secrets["GITHUB_REPO"].strip()

        # --- [修正の核心] パスの正規化 ---
        # 1. すべて小文字にして比較（GitHubの仕様に合わせる）
        # 2. Windowsの区切り文字をスラッシュに
        github_path = local_path.replace(os.sep, '/').lower().lstrip('/')

        url = f"https://api.github.com/repos/{repo}/contents/{github_path}"

        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }

        if mode == "upload":
            if not os.path.exists(local_path):
                return False

            # 既存ファイルのSHAを取得
            res = requests.get(url, headers=headers)
            sha = None
            if res.status_code == 200:
                sha = res.json().get("sha")

            # ファイルをBase64変換
            with open(local_path, "rb") as f:
                content = base64.b64encode(f.read()).decode("utf-8")

            # データ構築
            data = {
                "message": f"Sync: {github_path}",
                "content": content,
                "branch": "main"
            }
            if sha:
                data["sha"] = sha

            # 書き込み実行
            put_res = requests.put(url, json=data, headers=headers)

            if put_res.status_code in [200, 201]:
                print(f"✅ 反映成功: {github_path}")
                return True
            else:
                # 依然として404が出る場合、GitHub上のURLを直接叩く「強行手段」のログ
                print(f"❌ 失敗({put_res.status_code}): {put_res.text}")
                print(f"🔍 URL: {url}")
                return False

        elif mode == "download":
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                content = base64.b64decode(res.json()["content"])
                os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
                with open(local_path, "wb") as f:
                    f.write(content)
                return True
            return False

    except Exception as e:
        print(f"エンジン例外エラー: {e}")
        return False
# 共通UIヘルパー（中央プログレス表示）
def render_sync_ui(title_text):
    st.markdown("""
        <style>
        .sync-overlay {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.6); z-index: 9998;
        }
        .sync-modal {
            position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
            background: white; padding: 25px; border-radius: 15px;
            z-index: 9999; text-align: center; width: 320px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }
        .sync-modal .stProgress > div > div { background-color: #1E88E5; }
        </style>
        <div class="sync-overlay"></div>
        <div class="sync-modal">
            <h3 style='color: #333; margin-bottom: 20px;'>{title}</h3>
        </div>
    """.replace("{title}", title_text), unsafe_allow_html=True)
    p_bar = st.progress(0)
    p_text = st.empty()
    return p_bar, p_text
# ロード処理
def sync_all_assets_recursive(u_id, mode="download"):
    try:
        token = st.secrets["GITHUB_TOKEN"]
        repo = st.secrets["GITHUB_REPO"]
        headers = {"Authorization": f"token {token}"}
        target_dirs = ["assets/spread_data", f"assets/users/{u_id}"]

        def get_files_recursive(path):
            res = requests.get(f"https://api.github.com/repos/{repo}/contents/{path}", headers=headers)
            if res.status_code != 200: return []
            files = []
            for item in res.json():
                if item["type"] == "file":
                    files.append(item["path"])
                elif item["type"] == "dir":
                    files.extend(get_files_recursive(item["path"]))
            return files

        all_target_files = []
        for directory in target_dirs:
            all_target_files.extend(get_files_recursive(directory))

        if all_target_files:
            placeholder = st.empty()
            with placeholder.container():
                p_bar, p_text = render_sync_ui("📥 データを読込中")
                total = len(all_target_files)
                for i, f_path in enumerate(all_target_files):
                    github_sync_engine(f_path, mode="download")
                    percent = int((i + 1) / total * 100)
                    p_bar.progress(percent)
                    p_text.markdown(f"**{i + 1} / {total}** ({percent}%)")
            placeholder.empty()
    except Exception as e:
        print(f"Recursive Load Error: {e}")
# セーブ処理
def sync_user_assets(u_id, mode="upload", scope="user"):
    """
    GitHub同期：指定された範囲(scope)のみをスキャンして同期する
    scope="user"  : 自分の日誌や成績のみ (高速)
    scope="drive" : 資料ライブラリのみ
    scope="all"   : 全体 (従来通り)
    """
    if not u_id or u_id == 'guest': return

    token = st.secrets["GITHUB_TOKEN"]
    repo = st.secrets["GITHUB_REPO"]
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}

    # --- 修正ポイント：scopeによってスキャンするフォルダを限定する ---
    if scope == "user":
        target_folders = [f"assets/users/{u_id}"]
    elif scope == "drive":
        target_folders = ["assets/drive_data"]
    elif scope == "all":
        target_folders = [f"assets/users/{u_id}", "assets/drive_data"]
    else:
        target_folders = [f"assets/users/{u_id}"]  # デフォルトはユーザーのみ

    files_to_save = []
    for folder in target_folders:
        if os.path.exists(folder):
            for root, _, files in os.walk(folder):
                for file in files:
                    files_to_save.append(os.path.join(root, file))

    if files_to_save:
        placeholder = st.empty()
        with placeholder.container():
            # scopeによって表示文言を変えると分かりやすい
            title_msg = "💾 パーソナルデータを保存中" if scope == "user" else "💾 共有ドライブを保存中"
            p_bar, p_text = render_sync_ui(title_msg)
            total = len(files_to_save)

            for i, f_path in enumerate(files_to_save):
                github_path = f_path.replace(os.sep, '/')
                url = f"https://api.github.com/repos/{repo}/contents/{github_path}"

                res = requests.get(url, headers=headers)
                should_upload = False

                if res.status_code == 404:
                    print(f"💡 GitHub未存在のため新規追加判定: {github_path}")
                    should_upload = True
                elif res.status_code == 200:
                    # 改行コードの揺れを排除するためにstrip()を追加
                    remote_content = res.json().get("content", "").replace("\n", "").strip()
                    with open(f_path, "rb") as f:
                        local_content = base64.b64encode(f.read()).decode("ascii").strip()

                    if remote_content != local_content:
                        print(f"💡 差分検知のため更新判定: {github_path}")
                        should_upload = True

                if should_upload:
                    # エンジンの実行結果を受け取る
                    success = github_sync_engine(f_path, mode="upload")
                    if not success:
                        print(f"⚠️ {github_path} のアップロードに失敗しました。")

                percent = int((i + 1) / total * 100)
                p_bar.progress(percent)
                p_text.markdown(f"**{i + 1} / {total}** ({percent}%)")
        placeholder.empty()
# ==========================================
#　ログイン画面
# ==========================================
st.set_page_config(page_title="P-Quest 浜松医療センター薬剤科", page_icon="💊", layout="wide")
def get_image_base64(path):
    if os.path.exists(path):
        with open(path, "rb") as f:
            data = f.read()
        return base64.b64encode(data).decode()
    return None
def show_staff_confirmation_page():
    hospital_img = get_image_base64("assets/image/img.png")
    logo_img = get_image_base64("assets/image/file.png")

    # CSSの定義
    st.markdown(f"""
        <style>
        .stApp {{
            background: url("data:image/png;base64,{hospital_img}");
            background-size: cover;
            background-position: center;
        }}

        /* ラベル（文字）を読みやすく */
        .stTextInput label, .stCheckbox label {{
            color: #1E293B !important;
            font-weight: bold !important;
        }}

        /* ボタンのカスタマイズ（緑色にする場合） */
        div.stButton > button:first-child {{
            background-color: #005243;
            color: white;
            border-radius: 10px;
        }}

        header, footer {{ visibility: hidden !important; }}
        </style>
    """, unsafe_allow_html=True)

    # 画面の中央に配置するためのレイアウト調整
    _, center_col, _ = st.columns([1, 2, 1])

    with center_col:
        # ここで1つの「箱」を開始
        with st.container():
            st.markdown('<div class="login-card">', unsafe_allow_html=True)

            # 1. ロゴとタイトル
            if logo_img:
                st.markdown(f'<img src="data:image/png;base64,{logo_img}" style="width:70px; margin-bottom:10px;">',
                            unsafe_allow_html=True)
            st.markdown("<h2 style='color:#1E293B; margin-bottom:0;'>P-Quest</h2>", unsafe_allow_html=True)
            st.markdown("<p style='color:#64748B; font-size:14px;'>ver 1.0</p>", unsafe_allow_html=True)
            st.markdown(
                "<span style='background:#005243; color:white; padding:3px 12px; border-radius:10px; font-size:12px; font-weight:bold;'>職員認証・ログイン</span>",
                unsafe_allow_html=True)
            st.markdown("<div style='margin-bottom:25px;'></div>", unsafe_allow_html=True)

            # 2. 入力フォーム（ここも箱の中！）
            u_id = st.text_input("職員番号", placeholder="半角6桁", key="login_id")
            u_pw = st.text_input("パスワード", type="password", placeholder="数字4桁", key="login_pw")

            st.markdown(
                "<p style='font-size:11px; color:#64748B; text-align:left; margin-top:10px;'>【同意】データは研究等に利用される場合があります。</p>",
                unsafe_allow_html=True)
            agreed = st.checkbox("同意してログイン", value=True)

            if st.button("ログイン", use_container_width=True):
                user = check_login(u_id, u_pw)
                if user:
                    st.session_state['logged_in'] = True
                    st.session_state['user'] = user
                    st.session_state['is_staff_confirmed'] = True
                    st.rerun()
                else:
                    st.error("番号またはパスワードが違います")

            # 3. ゲスト・新規登録ボタン
            st.markdown("<hr style='margin: 20px 0; border:0; border-top:1px solid #eee;'>", unsafe_allow_html=True)
            col_g, col_s = st.columns(2)
            with col_g:
                if st.button("👤 ゲスト", use_container_width=True):
                    st.session_state['is_guest'] = True
                    st.rerun()
            with col_s:
                if st.button("📝 新規登録", use_container_width=True):
                    st.session_state['view'] = 'signup'  # 表示をsignupに切り替え
                    st.session_state['is_staff_confirmed'] = True  # 最初のゲートを通過させる
                    st.rerun()

            # 4. 公式HPリンク
            st.markdown(f"""
                <div style="margin-top: 20px;">
                    <a href="https://www.hmedc.or.jp/department/pharmacy/" target="_blank" 
                       style="color:#005243; text-decoration:none; font-weight:bold; font-size:13px;">
                       🏥 薬剤科 公式HP
                    </a>
                </div>
            """, unsafe_allow_html=True)

            st.markdown('</div>', unsafe_allow_html=True)  # ここで箱を閉じる
def check_login(user_id, password):
    """CSVからログイン情報を確認（最新名簿を同期してから照合）"""
    # 管理者は同期なしで即時判定（緊急用）
    if user_id == "000000" and password == "9999":
        return {"id": "admin", "name": "管理者", "role": "管理者", "level": 99, "exp": 0, "points": 0}

    # --- ログイン前に最新の名簿(spread_data)をGitHubから取得 ---
    try:
        # assets/spread_data/login_users.csv を狙い撃ちでDL
        # (github_sync_engineはパスを小文字化して処理するのでそのまま渡してOK)
        github_sync_engine(LOGIN_FILE, mode="download")
    except Exception as e:
        print(f"ログイン時の名簿更新に失敗（オフラインの可能性があります）: {e}")

    # CSVの読み込みと照合
    if not os.path.exists(LOGIN_FILE):
        return None

    with open(LOGIN_FILE, mode="r", encoding="utf_8_sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if str(row['id']) == str(user_id) and str(row['password']) == str(password):
                return row
    return None
def register_user(user_id, user_name, user_pw):
    """新規ユーザー登録（登録後に名簿をGitHubへ即時反映）"""
    # 既存チェック
    df = pd.read_csv(LOGIN_FILE)
    if str(user_id) in df['id'].astype(str).values:
        return False, "この番号は既に登録されています。"

    # ローカルのCSVに追記
    new_data = [user_id, user_name, user_pw, "一般"] # デフォルト役職は「一般」
    with open(LOGIN_FILE, mode="a", encoding="utf_8_sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(new_data)

    # ユーザー専用フォルダを作成
    user_dir = os.path.join(USERS_BASE_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    # --- GitHubへ最新名簿をアップロード ---
    try:
        # 名簿ファイルをピンポイントで同期
        success = github_sync_engine(LOGIN_FILE, mode="upload")
        if not success:
            print("警告: 名簿のGitHub同期に失敗しました（ローカルには保存済み）")
    except Exception as e:
        print(f"同期エラー: {e}")

    return True, "登録が完了しました！"
def show_signup_page():
    """新規登録画面"""
    _, col, _ = st.columns([1, 1.2, 1])
    with col:
        st.markdown("<div class='login-container'><h3>新規ユーザー登録</h3></div>", unsafe_allow_html=True)
        with st.form("signup_form"):
            new_id = st.text_input("職員番号 (6桁)", max_chars=6)
            new_name = st.text_input("お名前")
            new_pw = st.text_input("パスワード (4桁)", type="password", max_chars=4)

            if st.form_submit_button("登録を実行する", use_container_width=True):
                if len(new_id) == 6 and new_name and len(new_pw) == 4:
                    success, msg = register_user(new_id, new_name, new_pw)
                    if success:
                        st.success(msg)
                        st.session_state['is_staff_confirmed'] = False
                        st.rerun()
                    else:
                        st.error(msg)
                else:
                    st.warning("入力を確認してください。")

        if st.button("ログイン画面へ戻る"):
            st.session_state['is_staff_confirmed'] = False
            st.rerun()
def calculate_user_stats(u_id):
    """my_all_results.csv を読み込み、難易度別に経験値、レベル、ポイントを算出する"""
    results_path = f"assets/users/{u_id}/my_all_results.csv"
    questions_path = "assets/spread_data/questions.csv"

    total_exp = 0
    total_points = 0

    if not os.path.exists(results_path):
        return 1, 0, 0

    # 1. 難易度(レベル)のマスターデータを作成 {問題文: レベル}
    q_level_map = {}
    if os.path.exists(questions_path):
        try:
            with open(questions_path, mode="r", encoding="utf_8_sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    q_level_map[row["問題文"].strip()] = row["レベル"].strip()
        except Exception as e:
            print(f"質問マスタ読み込みエラー: {e}")

    # 2. 履歴を走査して計算
    try:
        with open(results_path, mode="r", encoding="utf_8_sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                q_text = row.get("問題文", "").strip()
                result = row.get("判定", "").strip()
                lvl_str = q_level_map.get(q_text, "★")  # デフォルトは星1

                # 難易度ごとの倍率設定
                multiplier = 1.0
                if lvl_str == "★★":
                    multiplier = 1.5
                elif lvl_str == "★★★":
                    multiplier = 2.0
                elif lvl_str == "★★★★":
                    multiplier = 3.0

                if result == "正解":
                    total_exp += int(100 * multiplier)
                    total_points += int(10 * multiplier)
                elif result == "不正解":
                    total_exp += int(20 * multiplier)
    except Exception as e:
        print(f"Stats計算エラー: {e}")

    level = 1 + (total_exp // 1000)
    current_exp = total_exp % 1000

    return level, current_exp, total_points
# ==========================================
#　ゲスト画面
# ==========================================
def show_guest_menu():
    """ゲスト用メイン画面（機能を制限したスリム版）"""

    # --- 1. コンパクト・ヘッダー (ゲスト版) ---
    st.markdown("<div class='header-box'>", unsafe_allow_html=True)

    # カラム比率を調整
    h_col1, h_col2, h_col4 = st.columns([1.5, 2.0, 2.5])

    with h_col1:
        st.markdown(
            f"<div class='user-info'>👤 ゲスト様 <span class='level-label'>閲覧のみ</span></div>",
            unsafe_allow_html=True)

    with h_col2:
        # ゲストは進捗を保存しないので、案内を表示
        st.info("💡 職員登録すると学習履歴が保存されます")

    with h_col4:
        st.markdown('<div class="compact-btn-container">', unsafe_allow_html=True)
        # ゲスト用のボタン：検索と終了のみ
        inner_cols = st.columns(2)

        with inner_cols[1]:
            if st.button("🚪 終了", key="g_logout", type="primary", use_container_width=True):
                st.session_state.clear()
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    # --- 2. メインメニュー（ゲストが閲覧可能なものに限定） ---
    st.markdown("<h3 style='text-align: center; margin-bottom: 25px; color: #475569;'>GUEST MENU</h3>",
                unsafe_allow_html=True)

    # ゲストに見せても良い項目だけを抽出
    m_col1, m_col2 = st.columns(2)
    guest_items = [
        {"title": "📝 問題演習 (体験)", "id": "quiz", "col": m_col2},
    ]

    for item in guest_items:
        with item['col']:
            if st.button(item['title'], key=f"guest_{item['id']}", use_container_width=True):
                # クイズなどの場合は「保存されません」と警告を出してもいいかも
                if item['id'] == 'quiz':
                    st.warning("ゲストモードでは回答結果は保存されません。")
                st.session_state['page'] = item['id']
                st.rerun()
# ==========================================
#　メインメニュー
# ==========================================
def show_main_menu():
    """メイン画面（難易度別の動的ステータス反映版）"""
    user = st.session_state['user']
    u_id = user.get('id', 'default_user')
    role = user.get('role', '一般')

    # 最新のステータスを計算
    level, exp, points = calculate_user_stats(u_id)

    # --- 1. コンパクト・ヘッダー ---
    st.markdown("<div class='header-box'>", unsafe_allow_html=True)
    h_col1, h_col2, h_col3, h_col4 = st.columns([1.5, 1.2, 0.8, 2.5])

    with h_col1:
        badge_icon = "🎓" if role == "教育係" else "🔰"
        st.markdown(
            f"<div class='user-info'>{badge_icon} {user['name']} <span class='level-label'>Lv.{int(level)}</span></div>",
            unsafe_allow_html=True)

    with h_col2:
        st.progress(exp / 1000)
        st.caption(f"EXP: {exp}/1000")

    with h_col3:
        st.markdown(
            f"<div style='margin-top:5px;'><span class='point-label'>🪙 {int(points)}</span></div>",
            unsafe_allow_html=True)

    with h_col4:
        st.markdown('<div class="compact-btn-container">', unsafe_allow_html=True)
        btn_count = 4 if role == "教育係" else 3
        inner_cols = st.columns(btn_count)

        col_idx = 0
        if role == "教育係":
            with inner_cols[col_idx]:
                if st.button("👥 進捗", key="h_mentor", use_container_width=True):
                    st.session_state['page'] = 'mentor_dashboard'
                    st.rerun()
            col_idx += 1

        with inner_cols[col_idx]:
            if st.button("🔍 検索", key="search", type="secondary", use_container_width=True):
                st.session_state['page'] = 'search'
                st.rerun()
        col_idx += 1

        with inner_cols[col_idx]:
            if st.button("📊 履歴", key="h_history", type="secondary", use_container_width=True):
                st.session_state['page'] = 'review'
                st.rerun()
        col_idx += 1

        with inner_cols[col_idx]:
            # --- 修正箇所：終了ボタンの同期処理を削除 ---
            if st.button("🚪 終了", key="h_logout", type="secondary", use_container_width=True):
                # 各アクション時に即時同期済みのため、ここでは保存をスキップ
                st.session_state.clear()
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    # --- 2. メインメニュー（カード） ---
    st.markdown("<h3 style='text-align: center; margin-bottom: 25px; color: #475569;'>MENU</h3>",
                unsafe_allow_html=True)

    m_col1, m_col2, m_col3 = st.columns(3)

    # 資料系が show_study_page に統合されたため、ボタン配置を最適化
    menu_items = [
        {"title": "📚 資料ライブラリ", "id": "study", "col": m_col1},
        {"title": "📝 問題演習", "id": "quiz", "col": m_col2},
        {"title": "❓ 掲示板", "id": "board", "col": m_col3},
        {"title": "💻 シミュレーション", "id": "simulation", "col": m_col1},
        {"title": "📔 業務日誌", "id": "diary", "col": m_col2},
        # 今後追加したいメニューがあればここに m_col3 用を追加可能
    ]

    for item in menu_items:
        with item['col']:
            if st.button(item['title'], key=f"menu_{item['id']}", use_container_width=True):
                st.session_state['page'] = item['id']
                st.rerun()
# ==========================================
#　クイズ関連
# ==========================================
def show_quiz_page():
    # ゲストフラグを取得（mainで初期化されている前提）
    is_guest = st.session_state.get('is_guest', False)

    # --- サイドバーのデザイン調整 ---
    with st.sidebar:
        st.markdown("### 📋 Main Menu")

        # 1. 初期メニューの決定（ゲストはクイズ一択）
        if 'active_menu' not in st.session_state:
            st.session_state.active_menu = "💊 薬剤と疾患" if is_guest else "⚖ 内規"

        # 2. メニューボタンの配置（ゲストはクイズボタンのみ表示）

        # --- A. 【職員のみ】内規ボタン ---
        if not is_guest:
            if st.button("⚖  薬局内規マニュアル", width='stretch',
                         type="primary" if st.session_state.active_menu == "⚖ 内規" else "secondary"):
                st.session_state.active_menu = "⚖ 内規"
                st.rerun()

        # --- B. 【共通】薬剤・疾患クイズ ---
        if st.button("💊  薬剤・疾患クイズ", width='stretch',
                     type="primary" if st.session_state.active_menu == "💊 薬剤と疾患" else "secondary"):
            st.session_state.active_menu = "💊 薬剤と疾患"
            st.rerun()

        # --- C. 【職員のみ】学習履歴ボタン ---
        if not is_guest:
            if st.button("📊  学習履歴・復習", width='stretch',
                         type="primary" if st.session_state.active_menu == "📊 復習" else "secondary"):
                st.session_state.active_menu = "📊 復習"
                st.rerun()

        st.divider()
        st.caption("Pharmacy Learning System v1.2")

    # --- メインコンテンツの表示 ---
    menu = st.session_state.active_menu

    # カテゴリー定義
    sub_categories = {
        "内規": ["調剤室業務", "注射室業務"],
        "薬剤と疾患": ["精神神経・筋疾患", "骨・関節疾患", "免疫疾患", "心臓・血管系疾患", "腎・泌尿器疾患",
                  "産科婦人科疾患", "呼吸器疾患", "消化器疾患", "血液及び造血器疾患",
                  "感覚器疾患", "内分泌・代謝疾患", "皮膚疾患", "感染症", "悪性腫瘍", "その他"]
    }

    # --- 分岐処理（ゲストによるガード付き） ---

    # 1. 内規（ゲストは弾く）
    if menu == "⚖ 内規":
        if is_guest:
            st.error("ゲストモードでは内規マニュアルは閲覧できません。")
            st.session_state.active_menu = "💊 薬剤と疾患"  # 強制戻し
        else:
            display_category_cards("内規", sub_categories["内規"])

    # 2. クイズ（共通）
    elif menu == "💊 薬剤と疾患":
        display_category_cards("薬剤と疾患", sub_categories["薬剤と疾患"])

    # 3. 復習（ゲストは弾く）
    elif menu == "📊 復習":
        if is_guest:
            st.error("ゲストモードでは履歴機能は利用できません。")
            st.session_state.active_menu = "💊 薬剤と疾患"  # 強制戻し
        else:
            st.markdown("### 📊 復習・統計")
            show_review_page()
def display_category_cards(main_cat, subs):
    """カテゴリー内のカード表示ロジック"""
    st.markdown(f"## {main_cat}")

    if main_cat == "内規":
        st.write("各業務の規定と手順を学習します。")
        for name in subs:
            with st.container(border=True):
                col1, col2 = st.columns([2, 3])
                with col1:
                    st.markdown(f"#### {name}")
                with col2:
                    c1, c2, c3 = st.columns(3)
                    if c1.button("✍ 練習", key=f"prac_{name}", use_container_width=True):
                        run_quiz(name, mode="normal")
                    if c2.button("🚀 テスト", key=f"test_{name}", use_container_width=True):
                        open_test_settings(name)
                    if c3.button("📊 進捗", key=f"prog_{name}", use_container_width=True):
                        st.session_state['current_task_view'] = name
                        st.session_state['page'] = 'progress_view'
                        st.rerun()
    else:
        # 薬剤と疾患：グリッドと総合問題
        with st.container(border=True):
            st.markdown("#### 全範囲からランダムに挑戦")
            if st.button(f"🔥 {main_cat} 総合テストを開始", type="primary", use_container_width=True):
                run_quiz(main_cat, mode="normal")

        st.write("分野別に学習する：")
        cols = st.columns(3)
        for i, name in enumerate(subs):
            with cols[i % 3]:
                # カードのようなデザインにするために border=True を使用
                with st.container(border=True):
                    st.write(f"**{name}**")
                    if st.button("開始", key=f"cat_{name}", use_container_width=True):
                        run_quiz(name, mode="normal")
def run_quiz(category, mode="normal"):
    """
    クイズを開始するためのセッション状態をセットアップする関数
    """
    st.session_state.quiz_started = True
    st.session_state.current_index = 0
    st.session_state.correct_count = 0
    st.session_state.test_target = category
    st.session_state.quiz_mode = mode
    # 記述問題などの一時的な状態もリセット
    st.session_state.show_feedback = False
    st.session_state.show_self_check = False
    st.session_state.test_recorded = False
    st.rerun()
@st.dialog("🚀 テスト設定")
def show_test_settings_dialog(category_name):
    st.write(f"**カテゴリー:** {category_name}")
    st.write("合格を目指して頑張りましょう！")

    # 設定項目
    num_q = st.slider("問題数", 5, 20, 10)
    pass_score = st.slider("合格ライン (%)", 50, 100, 80)

    st.divider()

    if st.button("テスト開始！", type="primary", use_container_width=True):
        # テスト用の設定をセッションに格納
        st.session_state.quiz_mode = "test"
        st.session_state.test_target = category_name
        st.session_state.num_questions = num_q
        st.session_state.pass_line = pass_score

        # クイズ開始フラグを立てる
        st.session_state.quiz_started = True
        st.session_state.current_index = 0
        st.session_state.correct_count = 0
        st.session_state.quiz_finished = False

        # 画面をリロードして engine を起動
        st.rerun()
def open_test_settings(name):
    """ボタンが押された時にダイアログを開く"""
    show_test_settings_dialog(name)
def save_test_result(category, total, correct, rate, pass_line):
    """テストの最終結果を保存し、GitHubに同期する"""
    u_id = st.session_state['user'].get('id', 'guest')
    path = f"assets/users/{u_id}/my_test_results.csv"

    # フォルダ作成
    os.makedirs(os.path.dirname(path), exist_ok=True)

    is_passed = "合格" if rate >= pass_line else "不合格"
    file_exists = os.path.exists(path)

    # 1. ローカルCSVへ書き込み
    try:
        with open(path, "a", encoding="utf_8_sig", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["日時", "カテゴリー", "正解数", "全問題数", "正答率", "合格ライン", "判定"])

            # datetime.datetime.now() のエラーを防ぐため安全に呼び出し
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

            writer.writerow([
                now_str,
                category,
                correct,
                total,
                f"{rate}%",
                f"{pass_line}%",
                is_passed
            ])

        # 2. GitHubへ同期（アップロード）
        with st.spinner("テスト結果をクラウドに同期中..."):
            success = github_sync_engine(path, mode="upload")

        if success:
            st.toast(f"✅ クラウド同期完了: {is_passed}")
        else:
            st.warning("⚠️ ローカルに保存しましたが、クラウド同期に失敗しました。")

    except Exception as e:
        st.error(f"保存エラー: {e}")

    print(f"✅ テスト結果を保存しました: {is_passed} ({rate}%)")
def show_progress_page():
    """📊 習得度チェックリスト画面（2026年最新仕様版）"""
    name = st.session_state.get('current_task_view', '不明')
    st.markdown(f"### 📊 {name} の習得度")

    # 1. 共通マスター・パス設定（省略）
    TASK_CSV = "assets/spread_data/task_list.csv"
    u_id = st.session_state['user'].get('id', 'guest')
    PROG_PATH = f"assets/users/{u_id}/my_progress.csv"
    HEADER = ["カテゴリ", "項目", "習得度", "最終更新"]

    # --- 同期・読み込み処理（中身は前回の修正を維持） ---
    if f"prog_synced_{name}" not in st.session_state:
        github_sync_engine(PROG_PATH, mode="download")
        st.session_state[f"prog_synced_{name}"] = True

    current_progress = {}
    if os.path.exists(PROG_PATH):
        try:
            df_existing = pd.read_csv(PROG_PATH, encoding="utf_8_sig")
            target_rows = df_existing[df_existing["カテゴリ"] == name]
            current_progress = dict(zip(target_rows["項目"], target_rows["習得度"]))
        except:
            pass

    # 4. 評価項目
    df_tasks = pd.read_csv(TASK_CSV, encoding="utf_8_sig")
    relevant_tasks = df_tasks[df_tasks["カテゴリ"] == name]["項目"].tolist()

    scores = []
    for task in relevant_tasks:
        col1, col2 = st.columns([3, 2])
        col1.write(f"**{task}**")
        val = col2.select_slider("自信度", options=[1, 2, 3, 4, 5], value=current_progress.get(task, 1), key=f"t_{task}",
                                 label_visibility="collapsed")
        scores.append(val)

    # 5. 進捗計算と表示
    perc = int(((sum(scores) - len(scores)) / (len(scores) * 4)) * 100) if scores else 0
    st.divider()
    st.write(f"現在の習得状況: **{perc}%**")
    st.progress(perc / 100)

    # 6. 【修正箇所】ボタンの width='stretch' 化
    col_btn, _ = st.columns([1, 1])
    with col_btn:
        if st.button("💾 進捗を保存して同期", type="primary", width='stretch'):
            # --- 保存ロジック ---
            new_rows = []
            now_str = datetime.datetime.now().strftime("%Y-%m-%d")
            if os.path.exists(PROG_PATH):
                try:
                    df_old = pd.read_csv(PROG_PATH, encoding="utf_8_sig")
                    new_rows = df_old[df_old["カテゴリ"] != name].values.tolist()
                except:
                    pass

            for task, score in zip(relevant_tasks, scores):
                new_rows.append([name, task, score, now_str])

            df_save = pd.DataFrame(new_rows, columns=HEADER)
            df_save.to_csv(PROG_PATH, index=False, encoding="utf_8_sig")
            github_sync_engine(PROG_PATH, mode="upload")
            st.session_state['page'] = 'quiz'
            st.rerun()

    if st.button("← 戻る (保存しない)", width='stretch'):
        st.session_state['page'] = 'quiz'
        st.rerun()
def show_quiz_engine():
    """クイズの進行管理（表示・判定・リザルトへの振り分け）"""
    # 状態の取得
    started = st.session_state.get('quiz_started', False)
    finished = st.session_state.get('quiz_finished', False)
    q_list = st.session_state.get('questions', [])
    idx = st.session_state.get('current_index', 0)

    # 1. そもそも問題がない、または未開始ならセットアップへ
    if not started or not q_list:
        print("[DEBUG] 🚩 問題が空のためセットアップを呼び出します")
        setup_quiz_data()
        return

    # 2. 終了フラグが立っている、または全問解き終わっていたらリザルトへ
    if finished or idx >= len(q_list):
        print(f"[DEBUG] 🏁 終了判定: finished={finished}, idx={idx}")
        # インデックスが超えていたら終了フラグを強制的に立てる
        st.session_state.quiz_finished = True
        show_result_screen()
        return

    # 3. 通常のクイズ表示
    print(f"[DEBUG] --- Question {idx + 1} / {len(q_list)} 表示中 ---")

    q = q_list[idx]

    # UI表示部分
    col_header1, col_header2 = st.columns([3, 1])
    col_header1.markdown(f"### ❓ Question {idx + 1} / {len(q_list)}")
    if col_header2.button("✕ 中断", key=f"quit_{idx}"):  # indexをkeyに含めて重複エラー防止
        quit_quiz()

    st.progress(idx / len(q_list))

    with st.container(border=True):
        st.caption(f"カテゴリー: {q[0]} > {q[1]} | 難易度: {q[3]}")
        st.markdown(f"#### {q[4]}")

    st.write("")
    # 回答用UIの呼び出し
    display_answer_ui(q)
def get_question_priorities(u_id):
    """
    ユーザーの履歴を読み込み、問題ごとの最新の結果をスコアリングする。
    未出題: 0, 不正解: 1, 正解: 2
    """
    history_path = f"assets/users/{u_id}/my_all_results.csv"
    priorities = {}  # {問題文: 判定スコア}

    if not os.path.exists(history_path):
        return priorities

    try:
        with open(history_path, mode="r", encoding="utf_8_sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                q_text = row["問題文"]
                result = row["判定"]
                # 履歴を上書きしていき、最新の結果を反映させる
                priorities[q_text] = 1 if result == "不正解" else 2
    except Exception as e:
        print(f"履歴読み込みエラー: {e}")

    return priorities
def setup_quiz_data():
    """クイズデータをCSVから読み込み、モードに応じた優先順位でセッションにセットする"""
    print("\n" + "=" * 40)
    print("🚀 setup_quiz_data を実行します")
    print("=" * 40)

    # 1. パスの解決
    current_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(current_dir, "assets", "spread_data", "questions.csv")

    # 2. 検索キーワードの取得とクリーニング
    raw_target = st.session_state.get('test_target', "")
    import re
    clean_target = re.sub(r'[^\w・]', '', raw_target).strip()

    print(f"DEBUG: 検索キーワード -> '{clean_target}'")

    if not os.path.exists(path):
        st.error(f"CSVファイルが見つかりません: {path}")
        return

    all_q = []
    try:
        with open(path, mode="r", encoding="utf_8_sig") as f:
            r = csv.reader(f)
            header = next(r, None)  # ヘッダーをスキップ

            for row in r:
                if len(row) < 2:
                    continue

                csv_major = row[0].strip()
                csv_minor = row[1].strip()

                # カテゴリー一致判定
                if clean_target in csv_major or clean_target in csv_minor:
                    all_q.append(row)

    except Exception as e:
        st.error(f"読み込みエラーが発生しました: {e}")
        return

    # 3. 結果の判定
    if not all_q:
        st.error(f"「{clean_target}」に一致する問題がありませんでした。")
        st.session_state.quiz_started = False
        return

    # --- モードに応じた出題ロジック ---
    mode = st.session_state.get('quiz_mode', 'normal')

    if mode == "test":
        # 【テストモード】完全ランダム
        selected_questions = random.sample(all_q, min(len(all_q), 10))
        print("🎲 モード: テスト (完全ランダム)")
    else:
        # 【通常モード】未出題(0) > 不正解(1) > 正解(2) の優先順
        u_id = st.session_state['user'].get('id', 'guest')
        history_scores = get_question_priorities(u_id)

        scored_questions = []
        for q in all_q:
            q_text = q[4]  # 問題文
            score = history_scores.get(q_text, 0)  # 履歴がなければ0
            scored_questions.append((score, q))

        # 同じスコア内でのランダム性を確保してソート
        random.shuffle(scored_questions)
        scored_questions.sort(key=lambda x: x[0])

        selected_questions = [x[1] for x in scored_questions[:10]]
        print("🧠 モード: 通常 (苦手・未出題優先)")

    # 4. セッション状態の更新
    st.session_state.questions = selected_questions
    st.session_state.quiz_started = True
    st.session_state.quiz_finished = False
    st.session_state.current_index = 0
    st.session_state.correct_count = 0

    print(f"✅ セットアップ完了: {len(selected_questions)}問を抽出")
    st.rerun()
def process_answer(user_ans, correct_data, q, is_written=False, written_text=None, display_ans_text=None):
    """
    正誤判定とステート更新、および履歴保存の実行
    """
    # 1. 正解データの抽出（CSV側の正解：番号またはテキスト）
    # 4択の場合はここが「1」〜「4」になる想定
    display_correct_ans = correct_data.split("|")[0] if "|" in correct_data else correct_data

    # 2. 正誤判定のロジック
    if is_written:
        # 記述式：ユーザーの自己申告(True/False)
        is_ok = user_ans
        actual_save_ans = written_text if written_text else "テキスト入力あり"
    else:
        # 選択式（〇×・4択）
        # user_ans に判定用の値（4択なら番号）、display_ans_text に保存用のテキストが入る
        is_ok = (str(user_ans).strip() == str(display_correct_ans).strip())

        # 保存用テキストが別途指定されていればそれを使う（4択用）
        actual_save_ans = display_ans_text if display_ans_text else user_ans

    # 3. ステート（セッション状態）の更新
    st.session_state.last_result = is_ok
    st.session_state.show_feedback = True
    if is_ok:
        st.session_state.correct_count += 1

    # 4. 履歴の保存
    # 4択の場合、CSVの「正解」列には番号ではなく、選択肢の文章を保存したい場合はここで調整可能
    # 今回は既存のロジックを維持し、CSVの正解列はそのまま correct_data の先頭を出力します
    save_quiz_history(q, actual_save_ans, display_correct_ans, is_ok)

    st.rerun()
def display_answer_ui(q):
    """
    回答用UI（〇×、4択、記述）の表示
    """
    # すでに回答済みで、フィードバック（解説）待機中の場合
    if st.session_state.get('show_feedback'):
        display_feedback(q)
        return

    # --- 以下、通常の回答UI ---
    q_type = q[2]
    correct_data = q[5]
    explanation = q[6] if len(q) > 6 else "なし"
    current_idx = st.session_state.get('current_index', 0)

    # 1. 〇×問題
    if q_type == "〇×問題":
        cols = st.columns(2)
        if cols[0].button("⭕ 〇", use_container_width=True, key=f"btn_true_{current_idx}"):
            process_answer("〇", correct_data, q)
        if cols[1].button("❌ ×", use_container_width=True, key=f"btn_false_{current_idx}"):
            process_answer("×", correct_data, q)

    # 2. 4択問題
    elif "4択問題" in q_type:
        options = correct_data.split("|")
        # 構造想定: options[0]=正解番号(1-4), options[1:5]=選択肢1〜4の文章
        choices = options[1:5]

        for i, choice in enumerate(choices):
            # 修正ポイント：
            # user_ans(第1引数) には判定用の「番号(1-4)」を渡す
            # display_ans_text(追加引数) には保存用の「文章」を渡す
            if st.button(f"{i + 1}. {choice}", use_container_width=True, key=f"btn_choice_{current_idx}_{i}"):
                process_answer(str(i + 1), correct_data, q, display_ans_text=choice)

    # 3. 記述問題
    else:
        user_ans = st.text_input("回答を入力してください", key=f"q_input_{current_idx}")
        if st.button("回答を送信", key=f"btn_submit_{current_idx}"):
            st.session_state.temp_ans = user_ans
            st.session_state.show_self_check = True

        if st.session_state.get('show_self_check'):
            with st.container(border=True):
                st.write(f"あなたの回答: **{st.session_state.temp_ans}**")
                st.write(f"模範解答: **{correct_data}**")
                st.info(f"【解説】\n{explanation}")

                c1, c2 = st.columns(2)
                if c1.button("✅ 正解にする", key=f"btn_ok_{current_idx}"):
                    process_answer(True, correct_data, q, is_written=True, written_text=st.session_state.temp_ans)
                if c2.button("❌ 不正解にする", key=f"btn_ng_{current_idx}"):
                    process_answer(False, correct_data, q, is_written=True, written_text=st.session_state.temp_ans)
def display_feedback(q):
    """解説画面に『関連資料』へのリンクを表示"""
    is_ok = st.session_state.last_result
    explanation = q[6]  # 解説
    ref_title = q[7]  # 資料タイトル
    author = q[8]  # 作成者

    if is_ok:
        st.success("🎉 **正解です！**")
    else:
        st.error("⚡ **不正解...**")

    with st.container(border=True):
        st.markdown(f"**【解説】**\n\n{explanation}")

        # 資料タイトルがある場合、ライブラリへの導線を表示
        if ref_title:
            st.info(f"📚 **関連資料:** {ref_title}")
            if st.button("📖 この資料を確認する"):
                # 資料ページへ飛ぶための準備（実装は後ほど調整可能）
                st.session_state.selected_material_title = ref_title
                st.session_state.page = "study"
                st.rerun()

        st.caption(f"作成者: {author}")

    if st.button("次の問題へ ➔", type="primary", use_container_width=True):
        st.session_state.current_index += 1
        st.session_state.show_feedback = False
        st.session_state.show_self_check = False
        st.rerun()
def check_answer(user_ans, correct_data, explanation, q):
    """選択形式の正誤判定"""
    ans = correct_data.split("|")[0] if "|" in correct_data else correct_data
    is_ok = (str(user_ans).strip() == str(ans).strip())

    # 判定結果を一時保存して解説表示へ
    st.session_state.last_result = is_ok
    st.session_state.last_explanation = explanation
    st.session_state.show_feedback = True

    if is_ok: st.session_state.correct_count += 1

    # 履歴保存（Tkinter版の _save_result 相当）
    save_quiz_history(q, user_ans, ans, is_ok)
    st.rerun()
def show_result_screen():
    total = len(st.session_state.questions)
    correct = st.session_state.correct_count
    rate = int((correct / total) * 100) if total > 0 else 0
    target = st.session_state.get('test_target', '不明')
    mode = st.session_state.get('quiz_mode', 'normal')

    st.markdown(f"## 🏁 {mode.upper()} 終了")

    # --- 修正：終了時にまとめて同期を実行 ---
    if not st.session_state.get('test_recorded', False):
        u_id = st.session_state['user'].get('id', 'guest')

        with st.status("📊 学習データを同期中...") as status:
            # A. テストモードならテスト結果を保存・同期
            if mode == "test":
                pass_line = st.session_state.get('pass_line', 80)
                save_test_result(target, total, correct, rate, pass_line)

            # B. モードに関わらず、蓄積された全回答履歴(my_all_results.csv)を同期
            history_path = f"assets/users/{u_id}/my_all_results.csv"
            if os.path.exists(history_path):
                github_sync_engine(history_path, mode="upload")

            status.update(label="✅ 全データの同期が完了しました", state="complete")
            st.session_state.test_recorded = True

    # --- UI表示 ---
    col1, col2, col3 = st.columns(3)
    col2.metric("正答率", f"{rate}%", f"{correct} / {total}")

    if mode == "test":
        pass_line = st.session_state.get('pass_line', 80)
        if rate >= pass_line:
            st.success(f"🎊 **合格！** おめでとうございます！")
            st.balloons()
        else:
            st.error(f"😭 **不合格...** 合格ラインは {pass_line}% です。")

    st.divider()
    if st.button("メニューへ戻る", type="primary", use_container_width=True):
        st.session_state.test_recorded = False  # フラグをリセット
        quit_quiz()
def quit_quiz():
    """クイズを中断し、データを同期してからメニューに戻る"""
    u_id = st.session_state['user'].get('id', 'guest')

    # 中断時点までの履歴を同期
    history_path = f"assets/users/{u_id}/my_all_results.csv"
    if os.path.exists(history_path):
        with st.spinner("データを同期して戻ります..."):
            github_sync_engine(history_path, mode="upload")

    st.session_state.quiz_started = False
    st.session_state.page = "quiz"
    st.rerun()
def save_quiz_history(q, user_ans, correct_ans, is_ok):
    """ユーザーフォルダにクイズ結果をCSV保存（ローカルのみに限定して高速化）"""
    try:
        u_id = st.session_state['user'].get('id', 'guest')
        path = f"assets/users/{u_id}/my_all_results.csv"

        # 1. フォルダとファイルの準備
        os.makedirs(os.path.dirname(path), exist_ok=True)
        file_exists = os.path.exists(path)

        # 2. ローカルCSVへ書き込み
        with open(path, "a", encoding="utf_8_sig", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["日時", "カテゴリー", "判定", "問題文", "自分の回答", "正解"])

            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            writer.writerow([
                now_str,
                q[1],  # カテゴリー
                "正解" if is_ok else "不正解",
                q[4],  # 問題文
                user_ans,
                correct_ans
            ])

        # 【修正】1問ごとの github_sync_engine 呼び出しを削除しました
        print(f"✅ ローカル保存完了: {path}")

    except Exception as e:
        print(f"❌ 履歴の保存に失敗しました: {e}")
def sync_quiz_results_to_github():
    """クイズの履歴ファイルをGitHubにピンポイント同期する"""
    u_id = st.session_state['user'].get('id', 'guest')
    if u_id == 'guest': return

    path = f"assets/users/{u_id}/my_all_results.csv"
    if os.path.exists(path):
        with st.spinner("📊 学習データを同期中..."):
            success = github_sync_engine(path, mode="upload")
            if success:
                st.toast("✅ 学習履歴をクラウドに同期しました")
def show_review_page():
    """📊 学習履歴・復習・統計画面（最新日時追加・全幅レイアウト版）"""
    # 画面を広く使う設定（個別のページ設定が難しい場合はコンテナで制御）
    st.markdown("# 📊 学習履歴と復習")

    u_id = st.session_state.get('user', {}).get('id', 'default_user')
    user_dir = f"assets/users/{u_id}"

    if not os.path.exists(user_dir):
        os.makedirs(user_dir, exist_ok=True)

    QUESTIONS_CSV = "assets/spread_data/questions.csv"
    RESULTS_CSV = os.path.join(user_dir, "my_all_results.csv")
    TEST_RESULTS_CSV = os.path.join(user_dir, "my_test_results.csv")

    # --- 1. フィルター状態の保持用初期化 ---
    if 'filter_maj' not in st.session_state: st.session_state.filter_maj = "すべて"
    if 'filter_min' not in st.session_state: st.session_state.filter_min = "すべて"
    if 'filter_lvl' not in st.session_state: st.session_state.filter_lvl = "すべて"
    if 'filter_f_res' not in st.session_state: st.session_state.filter_f_res = "すべて"
    if 'filter_l_res' not in st.session_state: st.session_state.filter_l_res = "すべて"

    # --- 2. 成績データの読み込みと集計 ---
    stats = {}
    if os.path.exists(RESULTS_CSV):
        try:
            with open(RESULTS_CSV, "r", encoding="utf_8_sig") as f:
                r = csv.reader(f)
                header = next(r, None)  # ヘッダー飛ばし
                for row in r:
                    if len(row) >= 6:
                        timestamp = row[0].strip()  # 日時
                        res = row[2].strip()  # 判定
                        q_text = row[3].strip()  # 問題文
                        my_ans = row[4].strip()  # 自分の回答

                        if q_text not in stats:
                            stats[q_text] = {"res": [], "ans": [], "dates": []}
                        stats[q_text]["res"].append(res)
                        stats[q_text]["ans"].append(my_ans)
                        stats[q_text]["dates"].append(timestamp)
        except Exception as e:
            st.error(f"成績データの読み込みに失敗しました: {e}")

    # --- 3. フィルター用サイドバー ---
    with st.sidebar:
        st.markdown("### 🔍 フィルター設定")
        sub_categories = {
            "内規": ["すべて", "調剤室業務", "注射室業務"],
            "薬剤と疾患": ["すべて", "精神神経・筋疾患", "骨・関節疾患", "免疫疾患", "心臓・血管系疾患",
                      "腎・泌尿器疾患", "産科婦人科疾患", "呼吸器疾患", "消化器疾患",
                      "血液及び造血器疾患", "感覚器疾患", "内分泌・代謝疾患", "皮膚疾患",
                      "感染症", "悪性腫瘍", "その他"]
        }

        st.session_state.filter_maj = st.selectbox("大カテゴリー", ["すべて"] + list(sub_categories.keys()),
                                                   index=(["すべて"] + list(sub_categories.keys())).index(
                                                       st.session_state.filter_maj))

        min_options = sub_categories.get(st.session_state.filter_maj,
                                         ["すべて"]) if st.session_state.filter_maj != "すべて" else ["すべて"]
        if st.session_state.filter_min not in min_options: st.session_state.filter_min = "すべて"

        st.session_state.filter_min = st.selectbox("小カテゴリー", min_options,
                                                   index=min_options.index(st.session_state.filter_min))

        lvls = ["すべて", "★", "★★", "★★★", "★★★★"]
        st.session_state.filter_lvl = st.selectbox("難易度", lvls, index=lvls.index(st.session_state.filter_lvl))

        results_opts = ["すべて", "正解", "不正解", "未回答"]
        st.session_state.filter_f_res = st.selectbox("初回成績で絞り込み", results_opts,
                                                     index=results_opts.index(st.session_state.filter_f_res))
        st.session_state.filter_l_res = st.selectbox("最新成績で絞り込み", results_opts,
                                                     index=results_opts.index(st.session_state.filter_l_res))

        if st.button("フィルターをリセット", width='stretch'):
            for key in ['filter_maj', 'filter_min', 'filter_lvl', 'filter_f_res', 'filter_l_res']:
                st.session_state[key] = "すべて"
            st.rerun()

    # --- 4. メインコンテンツ ---
    tab1, tab2 = st.tabs(["📖 問題管理・統計", "🏆 テスト履歴"])

    with tab1:
        if not os.path.exists(QUESTIONS_CSV):
            st.error("問題データが見つかりません。")
        else:
            df_q = pd.read_csv(QUESTIONS_CSV, encoding="utf_8_sig")
            total_questions_count = len(df_q)

            display_data = []
            for _, row in df_q.iterrows():
                q_txt = str(row["問題文"]).strip()
                h = stats.get(q_txt, {"res": [], "ans": [], "dates": []})
                results = h["res"]
                answers = h["ans"]
                dates = h["dates"]

                first_res = results[0] if results else "未回答"
                latest_res = results[-1] if results else "未回答"
                first_ans = answers[0] if answers else "-"
                latest_ans = answers[-1] if answers else "-"
                latest_date = dates[-1] if dates else "-"
                total_tries = len(results)
                accuracy_rate = f"{int((results.count('正解') / total_tries) * 100)}%" if total_tries > 0 else "0%"

                # フィルター適用
                if st.session_state.filter_maj != "すべて" and str(row["大項目"]) != st.session_state.filter_maj: continue
                if st.session_state.filter_min != "すべて" and str(row["小項目"]) != st.session_state.filter_min: continue
                if st.session_state.filter_lvl != "すべて" and str(row["レベル"]) != st.session_state.filter_lvl: continue
                if st.session_state.filter_f_res != "すべて" and first_res != st.session_state.filter_f_res: continue
                if st.session_state.filter_l_res != "すべて" and latest_res != st.session_state.filter_l_res: continue

                display_data.append({
                    "最新回答日時": latest_date,
                    "大項目": row["大項目"], "小項目": row["小項目"], "レベル": row["レベル"],
                    "問題文": q_txt, "初回成績": first_res, "初回回答": first_ans,
                    "最新成績": latest_res, "最新回答": latest_ans,
                    "回答回数": total_tries, "正答率": accuracy_rate,
                    "解答": row["解答"], "解説": row["解説"]
                })

            if display_data:
                res_df = pd.DataFrame(display_data)

                # メトリック表示
                col_m1, col_m2, col_m3 = st.columns(3)
                overcome_count = len(res_df[(res_df["初回成績"] == "不正解") & (res_df["最新成績"] == "正解")])
                answered_count = len(res_df[res_df['最新成績'] != '未回答'])
                col_m1.metric("弱点克服数", f"{overcome_count} 問")
                col_m2.metric("既習問題数 / 全問題数", f"{answered_count} / {total_questions_count}")
                progress_percent = int(
                    (answered_count / total_questions_count) * 100) if total_questions_count > 0 else 0
                col_m3.metric("学習進捗率", f"{progress_percent} %")

                st.subheader("📋 問題一覧（最新日時でソート可能）")

                # 表示列の定義（「最新回答日時」を先頭付近に配置）
                view_cols = ["最新回答日時", "大項目", "小項目", "レベル", "問題文", "初回成績", "最新成績", "回答回数", "正答率"]

                # 画面いっぱいに表示するために width='stretch' を適用
                selected_event = st.dataframe(
                    res_df[view_cols],
                    width='stretch',
                    height=500,  # 高さを固定して見やすく
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="multi-row"
                )
                selected_rows = selected_event.selection.rows

                # 復習ボタンエリア
                c_btn1, c_btn2 = st.columns(2)
                with c_btn1:
                    if st.button(f"🔄 選択した {len(selected_rows)} 問を復習", width='stretch', type="primary",
                                 disabled=len(selected_rows) == 0):
                        selected_q_texts = res_df.iloc[selected_rows]["問題文"].tolist()
                        st.session_state.questions = df_q[df_q["問題文"].isin(selected_q_texts)].values.tolist()
                        st.session_state.quiz_started = True
                        st.session_state.quiz_finished = False
                        st.session_state.current_index = 0
                        st.session_state.correct_count = 0
                        st.session_state.page = "quiz"
                        st.rerun()

                with c_btn2:
                    if st.button("📖 表示中の全問題を復習", width='stretch'):
                        st.session_state.questions = df_q[df_q["問題文"].isin(res_df["問題文"])].values.tolist()
                        st.session_state.quiz_started = True
                        st.session_state.quiz_finished = False
                        st.session_state.current_index = 0
                        st.session_state.correct_count = 0
                        st.session_state.page = "quiz"
                        st.rerun()

                # --- 5. プレビューの強化 ---
                if len(selected_rows) == 1:
                    st.divider()
                    q_detail = res_df.iloc[selected_rows[0]]
                    with st.container(border=True):
                        st.markdown(f"### 🔍 詳細プレビュー")
                        st.markdown(f"**【問題文】**\n{q_detail['問題文']}")

                        p_col1, p_col2, p_col3 = st.columns(3)
                        with p_col1:
                            st.write(f"🔹 **初回:** {q_detail['初回成績']} ({q_detail['初回回答']})")
                            st.write(f"🔹 **最新:** {q_detail['最新成績']} ({q_detail['最新回答']})")
                        with p_col2:
                            st.write(f"📈 **正答率:** {q_detail['正答率']}")
                            st.write(f"🔢 **回答回数:** {q_detail['回答回数']} 回")
                        with p_col3:
                            st.write(f"📅 **最終回答:**\n{q_detail['最新回答日時']}")

                        if q_detail['最新成績'] != "未回答":
                            st.success(f"**【模範解答】**\n{q_detail['解答']}")
                            st.info(f"**【解説】**\n{q_detail['解説']}")
            else:
                st.info("条件に一致するデータがありません。")

    with tab2:
        st.markdown("### 🏆 テスト履歴")
        if os.path.exists(TEST_RESULTS_CSV):
            df_test = pd.read_csv(TEST_RESULTS_CSV, encoding="utf_8_sig")
            # 「日時」列が存在することを確認してソート
            if "日時" in df_test.columns:
                df_test = df_test.sort_values(by="日時", ascending=False)
            st.dataframe(df_test, width='stretch', hide_index=True)
        else:
            st.info("テスト履歴がありません。")
# ==========================================
#　メッセージ関連
# ==========================================
def ensure_csv_exists(path, columns):
    """CSVファイルとディレクトリの存在を保証する"""
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        pd.DataFrame(columns=columns).to_csv(path, index=False, encoding="utf_8_sig")
def save_message(title, content, status, is_anon, is_public, u_name, u_id, MASTER_CSV, USER_CSV):
    """新規投稿をマスターと個人ログの両方に保存する"""
    now = datetime.datetime.now()
    new_data = {
        "ID": now.strftime("%Y%m%d%H%M%S"),
        "日時": now.strftime("%Y/%m/%d %H:%M"),
        "ユーザー": "匿名さん" if is_anon else u_name,
        "ユーザーID": u_id,
        "タイトル": title,
        "内容": content,
        "回答": "",
        "ステータス": status,
        "公開フラグ": "公開" if is_public else "非公開"
    }

    # マスターと個人用、両方に書き込み
    for path in [MASTER_CSV, USER_CSV]:
        ensure_csv_exists(path, ["ID", "日時", "ユーザー", "ユーザーID", "タイトル", "内容", "回答", "ステータス", "公開フラグ"])
        df = pd.read_csv(path, encoding="utf_8_sig")
        df = pd.concat([df, pd.DataFrame([new_data])], ignore_index=True)
        df.to_csv(path, index=False, encoding="utf_8_sig")
        # 各ファイルをGitHubへ同期
        github_sync_engine(path, mode="upload")
def submit_answer(m_id, ans_text, is_anon, u_name, u_id, MASTER_CSV):  # 回答者ID(u_id)を追加
    """回答を追記し、投稿者と回答者双方の個人ログにも反映させる"""
    df_master = pd.read_csv(MASTER_CSV, encoding="utf_8_sig")
    m_id = str(m_id)

    if m_id not in df_master['ID'].astype(str).values:
        return False

    idx = df_master[df_master['ID'].astype(str) == m_id].index[0]
    post_user_id = df_master.at[idx, 'ユーザーID']  # 投稿者のID

    # 回答文のフォーマット
    display_name = "匿名さん" if is_anon else u_name
    now_str = datetime.datetime.now().strftime("%m/%d %H:%M")
    new_entry = f"【{display_name}】({now_str})\n{ans_text}\n"

    current_ans = str(df_master.at[idx, '回答']) if pd.notna(df_master.at[idx, '回答']) else ""
    updated_ans = current_ans + "\n" + new_entry if current_ans else new_entry

    # A. マスターCSVの更新と同期
    df_master.at[idx, '回答'] = updated_ans
    df_master.at[idx, 'ステータス'] = "回答あり"
    df_master.to_csv(MASTER_CSV, index=False, encoding="utf_8_sig")
    github_sync_engine(MASTER_CSV, mode="upload")

    # B. 投稿者と回答者、それぞれの個人CSVを更新
    # 自分の投稿への回答、または自分が他人の投稿に回答した場合の両方に対応
    target_user_ids = list(set([str(post_user_id), str(u_id)]))  # 重複排除

    for target_id in target_user_ids:
        user_csv_path = f"assets/users/{target_id}/my_forum.csv"
        if os.path.exists(user_csv_path):
            df_user = pd.read_csv(user_csv_path, encoding="utf_8_sig")
            # その投稿が個人ログに存在すれば更新（回答者のログにはまだ無い場合が多いので適宜処理）
            if m_id in df_user['ID'].astype(str).values:
                u_idx = df_user[df_user['ID'].astype(str) == m_id].index[0]
                df_user.at[u_idx, '回答'] = updated_ans
                df_user.at[u_idx, 'ステータス'] = "回答あり"
                df_user.to_csv(user_csv_path, index=False, encoding="utf_8_sig")
                github_sync_engine(user_csv_path, mode="upload")

    return True
def render_post_form(u_name, u_id, u_role, MASTER_CSV, USER_CSV):
    """新規投稿フォーム：異議申し立て引用機能付き"""
    st.subheader("📝 新しいメッセージを投稿")

    type_options = ["質問", "システムの要望", "問題の異議申し立て"]
    if any(r in str(u_role) for r in ["管理者", "メンター", "教育係"]):
        type_options.insert(0, "お知らせ")

    msg_type = st.selectbox("カテゴリー", type_options)

    # 引用ツール
    if msg_type == "問題の異議申し立て":
        Q_CSV = "assets/spread_data/questions.csv"
        if os.path.exists(Q_CSV):
            df_q = pd.read_csv(Q_CSV, encoding="utf_8_sig")
            c1, c2 = st.columns(2)
            maj = c1.selectbox("大項目で絞り込み", ["すべて"] + sorted(df_q["大項目"].unique().tolist()))
            tmp = df_q if maj == "すべて" else df_q[df_q["大項目"] == maj]
            selected_q = st.selectbox("該当の問題を選択してください", ["-- 未選択 --"] + tmp["問題文"].tolist())
            if selected_q != "-- 未選択 --":
                st.session_state.temp_title = f"【異議】{selected_q}"

    with st.form("post_form_final"):
        title = st.text_input("件名", value=st.session_state.get("temp_title", ""))
        content = st.text_area("内容", height=150, placeholder="具体的な内容を記入してください...")
        c1, c2 = st.columns(2)
        is_anon = c1.checkbox("匿名で投稿する")
        is_public = c2.checkbox("全体に公開する", value=True)

        if st.form_submit_button("🚀 投稿する", use_container_width=True):
            if title and content:
                save_message(title, content, msg_type, is_anon, is_public, u_name, u_id, MASTER_CSV, USER_CSV)
                st.session_state.temp_title = ""
                st.session_state.forum_view = "list"
                st.success("投稿が完了しました！")
                st.rerun()
            else:
                st.error("件名と本文を入力してください。")

    if st.button("← 戻る"):
        st.session_state.forum_view = "list"
        st.rerun()
def show_message_hub():
    """掲示板メイン：閲覧・回答・削除の統合画面（2026年 UI仕様準拠版）"""
    # ユーザー情報の取得
    u_id = st.session_state.get('user', {}).get('id', 'guest')
    u_name = st.session_state.get('user', {}).get('name', 'Unknown')
    u_role = str(st.session_state.get('user', {}).get('role', '一般'))
    is_admin = any(r in u_role for r in ["管理者", "メンター", "教育係"])

    # 1. パスとカラムの定義
    MASTER_CSV = "assets/spread_data/forum_master.csv"
    USER_CSV = f"assets/users/{u_id}/my_forum.csv"
    cols = ["ID", "日時", "ユーザー", "ユーザーID", "タイトル", "内容", "回答", "ステータス", "公開フラグ"]

    # 2. フォルダの存在保証
    os.makedirs(os.path.dirname(MASTER_CSV), exist_ok=True)
    os.makedirs(os.path.dirname(USER_CSV), exist_ok=True)

    # 3. GitHubから最新データを同期
    if "forum_synced" not in st.session_state:
        github_sync_engine(MASTER_CSV, mode="download")
        st.session_state.forum_synced = True

    # 4. ファイル不在時の生成 & カラム補完
    for path in [MASTER_CSV, USER_CSV]:
        if not os.path.exists(path):
            pd.DataFrame(columns=cols).to_csv(path, index=False, encoding="utf_8_sig")
        else:
            df_tmp = pd.read_csv(path, encoding="utf_8_sig")
            missing_cols = [c for c in cols if c not in df_tmp.columns]
            if missing_cols:
                for c in missing_cols:
                    df_tmp[c] = "guest" if c == "ユーザーID" else ""
                df_tmp.to_csv(path, index=False, encoding="utf_8_sig")

    # 5. 投稿フォームへの切り替え
    if st.session_state.get("forum_view") == "post":
        render_post_form(u_name, u_id, u_role, MASTER_CSV, USER_CSV)
        return

    # 6. サイドバー
    with st.sidebar:
        st.markdown("### 📂 表示フィルター")
        f_cat = st.radio("カテゴリー選択", ["すべて", "お知らせ", "質問", "要望", "異議"])
        st.divider()
        # use_container_width -> width='stretch'
        if st.button("➕ 新規メッセージ作成", type="primary", width='stretch'):
            st.session_state.forum_view = "post"
            st.rerun()

    # 7. データの読み込み
    df = pd.read_csv(MASTER_CSV, encoding="utf_8_sig")

    # 8. 権限フィルタリング
    if not is_admin:
        df = df[(df["公開フラグ"] == "公開") | (df["ユーザーID"].astype(str) == str(u_id))]

    cat_map = {"要望": "システムの要望", "異議": "問題の異議申し立て"}
    if f_cat != "すべて":
        target = cat_map.get(f_cat, f_cat)
        df = df[df["ステータス"] == target]

    # 9. 画面レイアウト
    col_list, col_detail = st.columns([1, 1.2])

    with col_list:
        st.markdown("##### 📨 投稿一覧")
        if df.empty:
            st.info("表示できるメッセージはありません。")
            selected_rows = None
        else:
            view_df = df[["日時", "ユーザー", "タイトル"]].sort_values("日時", ascending=False)
            selected_rows = st.dataframe(
                view_df,
                width='stretch',  # 2026年仕様
                height=550,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row"
            )

    with col_detail:
        st.markdown("##### 📖 詳細内容")
        if selected_rows and len(selected_rows.selection.rows) > 0:
            row_idx = selected_rows.selection.rows[0]
            orig_idx = view_df.index[row_idx]
            msg = df.loc[orig_idx]

            with st.container(border=True):
                st.markdown(f"### {msg['タイトル']}")
                st.caption(f"👤 {msg['ユーザー']} | 📅 {msg['日時']}")
                st.write(msg['内容'])

            if pd.notna(msg['回答']) and str(msg['回答']).strip():
                st.markdown("---")
                st.markdown("##### 💬 コメント履歴")
                st.info(msg['回答'])

            st.divider()
            with st.expander("🗨️ 回答を追記する"):
                ans_text = st.text_area("内容", key=f"ans_area_{msg['ID']}")
                ans_anon = st.checkbox("匿名投稿", key=f"ans_anon_{msg['ID']}")
                # width='stretch' へ置換
                if st.button("回答を送信", key=f"ans_btn_{msg['ID']}", width='stretch'):
                    if ans_text:
                        if submit_answer(msg['ID'], ans_text, ans_anon, u_name, MASTER_CSV):
                            st.success("回答を送信しました！")
                            st.rerun()

            if is_admin or str(msg['ユーザーID']) == str(u_id):
                st.write("")
                # width='stretch' へ置換
                if st.button("🗑️ 投稿を削除", type="secondary", width='stretch'):
                    new_df = df[df['ID'].astype(str) != str(msg['ID'])]
                    new_df.to_csv(MASTER_CSV, index=False, encoding="utf_8_sig")
                    github_sync_engine(MASTER_CSV, mode="upload")
                    st.toast("投稿を削除しました")
                    st.rerun()
        else:
            st.info("左側から選択してください。")
# ==========================================
#　勉強会資料
# ==========================================
def display_pdf(file_path):
    """PDF表示用HTML"""
    try:
        with open(file_path, "rb") as f:
            base64_pdf = base64.b64encode(f.read()).decode('utf-8')
        pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800px" type="application/pdf"></iframe>'
        st.markdown(pdf_display, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"エラー: {e}")
def show_study_page():
    """📚 統合資料ライブラリ：階層フォルダ表示・マルチタイプ対応・即時同期版"""
    st.markdown("## 📚 資料ライブラリ")

    # --- 1. パス・権限・データ読み込み ---
    BASE_DIR = "assets"
    STORAGE_DIR = os.path.join(BASE_DIR, "drive_data", "materials")
    CSV_FILE = os.path.join(BASE_DIR, "spread_data", "integrated_materials.csv")
    os.makedirs(STORAGE_DIR, exist_ok=True)

    if os.path.exists(CSV_FILE):
        df = pd.read_csv(CSV_FILE, encoding="utf_8_sig").fillna("")
    else:
        df = pd.DataFrame(columns=["大カテゴリー", "小カテゴリー", "タイトル", "タイプ", "ファイル名", "URL", "登録者"])

    user = st.session_state.get('user', {})
    u_id = user.get('id', 'default_user')
    u_name = user.get('name', 'Unknown')
    u_role = str(user.get('role', '一般'))
    # 管理者・メンター権限の確認
    is_admin = any(r in u_role for r in ["管理者", "教育係", "メンター"])

    # --- 2. フィルター設定 ---
    sub_cats = {
        "内規": ["調剤室業務", "注射室業務"],
        "薬剤と疾患": ["精神神経・筋疾患", "骨・関節疾患", "免疫疾患", "心臓・血管系疾患", "腎・泌尿器疾患",
                  "産科婦人科疾患", "呼吸器疾患", "消化器疾患", "血液及び造血器疾患",
                  "感覚器疾患", "内分泌・代謝疾患", "皮膚疾患", "感染症", "悪性腫瘍", "その他"],
        "チーム": ["感染(ICT)", "栄養(NST)", "緩和(PCT)"],
        "その他": ["その他"]
    }

    col_f1, col_f2, col_f3 = st.columns([1, 1, 1])
    with col_f1:
        p_filter = st.selectbox("📁 大カテゴリ絞り込み", ["すべて"] + list(sub_cats.keys()))
    with col_f2:
        min_opts = ["すべて"] + sub_cats[p_filter] if p_filter != "すべて" else ["すべて"]
        c_filter = st.selectbox("📂 小カテゴリ絞り込み", min_opts)
    with col_f3:
        st.write("")
        if st.button("➕ 新規資料を登録", width='stretch', type="primary"):
            st.session_state.adding_material = True
            st.session_state.selected_material_idx = None  # 追加時は選択解除
            st.rerun()

    st.divider()

    # --- 3. メインレイアウト ---
    col_tree, col_view = st.columns([1.2, 1.8])

    with col_tree:
        st.markdown(f"#### 📂 フォルダ一覧 ({len(df)}個)")
        target_majors = [p_filter] if p_filter != "すべて" else list(sub_cats.keys())

        for major in target_majors:
            major_df = df[df["大カテゴリー"] == major]
            major_count = len(major_df)

            with st.expander(f"📁 {major} ({major_count}個)", expanded=(p_filter != "すべて")):
                target_minors = [c_filter] if c_filter != "すべて" else sub_cats.get(major, ["その他"])

                for minor in target_minors:
                    minor_df = major_df[major_df["小カテゴリー"] == minor]
                    minor_count = len(minor_df)

                    if minor_count > 0 or c_filter != "すべて":
                        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;**📂 {minor} ({minor_count}個)**")
                        for idx, row in minor_df.iterrows():
                            # タイプと拡張子に応じたラベル
                            if row["タイプ"] == "URL":
                                type_label = "(URL)"
                            else:
                                ext = os.path.splitext(row["ファイル名"])[1].lower()
                                type_label = f"({ext.replace('.', '').upper()})"

                            if st.button(f"📄 {row['タイトル']} {type_label}", key=f"mat_{idx}", width='stretch'):
                                st.session_state.selected_material_idx = idx
                                st.session_state.adding_material = False
                                st.rerun()

    with col_view:
        # --- A. 新規登録画面 ---
        if st.session_state.get('adding_material'):
            with st.container(border=True):
                st.subheader("🆕 新規資料の登録")
                n_p = st.selectbox("大カテゴリ", list(sub_cats.keys()))
                n_c = st.selectbox("小カテゴリ", sub_cats[n_p])
                n_title = st.text_input("タイトル", placeholder="例：2024年度 感染対策マニュアル")
                n_type = st.radio("資料の形式", ["URL(リンク)", "ファイル(PDF/PPT/Word)"], horizontal=True)

                n_url, n_fname = "", ""
                n_up = None
                if n_type == "URL(リンク)":
                    n_url = st.text_input("🌐 URLを入力")
                else:
                    n_up = st.file_uploader("ファイルを選択", type=["pdf", "pptx", "ppt", "docx", "doc"])
                    if n_up: n_fname = n_up.name

                st.divider()
                if st.button("💾 登録して同期", type="primary", width='stretch'):
                    if n_title and (n_url or n_fname):
                        with st.spinner("保存中..."):
                            # ファイル保存
                            if n_type != "URL(リンク)" and n_up:
                                with open(os.path.join(STORAGE_DIR, n_fname), "wb") as f:
                                    f.write(n_up.getbuffer())

                            # CSV更新
                            new_row = {
                                "大カテゴリー": n_p, "小カテゴリー": n_c, "タイトル": n_title,
                                "タイプ": "URL" if n_type == "URL(リンク)" else "FILE",
                                "ファイル名": n_fname, "URL": n_url, "登録者": u_name
                            }
                            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                            df.to_csv(CSV_FILE, index=False, encoding="utf_8_sig")

                        # GitHub同期 (GitHubSyncEngineまたはsync_user_assetsを想定)
                        with st.status("📥 GitHubへ同期中...") as status:
                            try:
                                # integrated_materials.csvの同期を明示的に行う
                                if "github_sync_engine" in globals():
                                    github_sync_engine(CSV_FILE, mode="upload")
                                elif "sync_user_assets" in globals():
                                    sync_user_assets(u_id, mode="upload", scope="drive")

                                status.update(label="✅ 同期完了", state="complete")
                                st.success(f"『{n_title}』を登録・同期しました！")
                                time.sleep(1)
                                st.session_state.adding_material = False
                                st.rerun()
                            except Exception as e:
                                status.update(label="❌ 同期失敗", state="error")
                                st.error(f"同期に失敗しました: {e}")
                    else:
                        st.error("タイトルと、URLまたはファイルは必須です。")

                if st.button("キャンセル", width='stretch'):
                    st.session_state.adding_material = False
                    st.rerun()

        # --- B. 詳細表示画面 ---
        elif st.session_state.get('selected_material_idx') is not None:
            idx = st.session_state.selected_material_idx
            if idx in df.index:
                data = df.loc[idx]
                st.subheader(data["タイトル"])
                st.caption(f"📍 {data['大カテゴリー']} > {data['小カテゴリー']} | 👤 登録: {data['登録者']}")

                with st.container(border=True):
                    if data["タイプ"] == "URL":
                        st.success(f"🔗 URL: {data['URL']}")
                        st.link_button("🌐 リンク先を開く", data["URL"], width='stretch')
                    else:
                        f_path = os.path.join(STORAGE_DIR, data["ファイル名"])
                        if os.path.exists(f_path):
                            ext = os.path.splitext(data["ファイル名"])[1].lower()
                            if ext == ".pdf":
                                display_pdf(f_path)
                            elif ext in [".docx", ".doc", ".pptx", ".ppt"]:
                                st.info(f"{ext.replace('.', '').upper()}ファイルはプレビュー非対応です。ダウンロードしてください。")
                                with open(f_path, "rb") as f:
                                    st.download_button(f"📥 ダウンロード ({ext.replace('.', '').upper()})",
                                                       f, file_name=data["ファイル名"], width='stretch')
                        else:
                            st.error("ファイルが見つかりません。")

                # 管理権限または本人のみ削除可能
                if is_admin or data["登録者"] == u_name:
                    st.divider()
                    if st.button("🗑️ この資料を削除して同期", type="secondary", width='stretch'):
                        with st.spinner("削除・同期中..."):
                            # 実ファイルの削除
                            if data["タイプ"] == "FILE":
                                f_real_path = os.path.join(STORAGE_DIR, data["ファイル名"])
                                if os.path.exists(f_real_path):
                                    os.remove(f_real_path)

                            # CSVから削除して保存
                            df = df.drop(idx)
                            df.to_csv(CSV_FILE, index=False, encoding="utf_8_sig")

                            # 削除後の同期実行
                            try:
                                if "github_sync_engine" in globals():
                                    github_sync_engine(CSV_FILE, mode="upload")
                                elif "sync_user_assets" in globals():
                                    sync_user_assets(u_id, mode="upload", scope="drive")
                                st.success("資料を削除し、クラウドと同期しました。")
                                time.sleep(1)
                            except Exception as e:
                                st.error(f"削除後の同期に失敗しました: {e}")

                            st.session_state.selected_material_idx = None
                            st.rerun()
        else:
            st.info("📂 左のフォルダから資料を選択してください。")
# ==========================================
#　日誌関連
# ==========================================
def show_diary_page():
    """📔 業務・学習日誌ページ"""
    st.markdown("## 📔 業務・学習日誌ポートフォリオ")

    # --- 1. ユーザー情報とパス設定 ---
    user = st.session_state.get('user', {})
    u_id = user.get('id', 'guest')
    u_name = user.get('name', 'Unknown')
    u_role = str(user.get('role', '一般'))

    # ユーザー専用ディレクトリ
    USER_DIR = os.path.join("assets", "users", str(u_id))
    os.makedirs(USER_DIR, exist_ok=True)
    DIARY_CSV = os.path.join(USER_DIR, "diary.csv")

    # CSVの初期化
    cols = ["日付", "内容", "コメント"]
    if not os.path.exists(DIARY_CSV):
        pd.DataFrame(columns=cols).to_csv(DIARY_CSV, index=False, encoding="utf_8_sig")

    # データの読み込み
    df = pd.read_csv(DIARY_CSV, encoding="utf_8_sig")
    df = df.sort_values("日付", ascending=False)

    # --- 2. サイドバー：履歴リスト ---
    with st.sidebar:
        st.markdown("### 📅 過去の記録")

        # 選択用のリスト（日付 + コメントありならアイコン表示）
        if not df.empty:
            df_display = df.copy()
            df_display["表示名"] = df_display.apply(
                lambda x: f"📅 {x['日付']} {'💬' if pd.notna(x['コメント']) and x['コメント'].strip() else ''}", axis=1
            )

            # リストから選択
            list_options = ["🆕 新規作成"] + df_display["日付"].tolist()
            selected_date = st.radio("記録を選択", list_options)
        else:
            st.info("記録がありません。")
            selected_date = "🆕 新規作成"

    # --- 3. メインエリア：編集・閲覧 ---
    is_new = (selected_date == "🆕 新規作成")

    if is_new:
        st.subheader("📝 本日の学びを記録する")
        current_date = datetime.now().date().strftime("%Y-%m-%d")
        default_content = ""
        current_comment = ""
        badge_text = "新規作成"
        badge_color = "blue"
    else:
        # 既存データの取得
        target_row = df[df["日付"] == selected_date].iloc[0]
        current_date = selected_date
        default_content = target_row["内容"]
        current_comment = target_row["コメント"] if pd.notna(target_row["コメント"]) else ""
        badge_text = "編集モード"
        badge_color = "orange"

    # ステータス表示
    st.markdown(f"**ステータス:** :{badge_color}[{badge_text}] 　 **日付:** `{current_date}`")

    # 本文入力
    content = st.text_area("今日の学び・振り返り", value=default_content, height=250, placeholder="今日学んだことや、気づいたことを自由に書きましょう。")

    # フィードバック表示（既存データがある場合のみ）
    if not is_new:
        with st.expander("💬 指導者からのフィードバック", expanded=True):
            if current_comment.strip():
                st.info(current_comment)
            else:
                st.caption("まだフィードバックはありません。保存して指導者の確認を待ちましょう。")

    # アクションボタン
    col_save, col_del, col_space = st.columns([1, 1, 2])

    with col_save:
        if st.button("💾 日誌を保存して同期", type="primary", use_container_width=True):
            if not content.strip():
                st.error("内容を入力してください。")
            else:
                # 更新処理
                new_row = {"日付": current_date, "内容": content, "コメント": current_comment}

                if is_new:
                    if current_date in df["日付"].values:
                        df.loc[df["日付"] == current_date, ["内容", "コメント"]] = [content, current_comment]
                    else:
                        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                        st.toast("経験値を獲得しました！(+10 EXP)")
                else:
                    df.loc[df["日付"] == current_date, ["内容", "コメント"]] = [content, current_comment]

                # ローカル保存
                df.to_csv(DIARY_CSV, index=False, encoding="utf_8_sig")

                # --- GitHub同期実行 ---
                with st.status("📥 クラウドへ同期中...") as status:
                    try:
                        sync_user_assets(u_id, mode="upload", scope="user")
                        status.update(label="✅ 保存・同期完了", state="complete")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        status.update(label="❌ 同期失敗", state="error")
                        st.error(f"保存はされましたが同期に失敗しました: {e}")

    with col_del:
        if not is_new:
            if st.button("🗑 記録を削除", use_container_width=True):
                df = df[df["日付"] != current_date]
                df.to_csv(DIARY_CSV, index=False, encoding="utf_8_sig")
                # 削除時も同期
                sync_user_assets(u_id, mode="upload", scope="user")
                st.warning("記録を削除し、同期しました。")
                time.sleep(1)
                st.rerun()

    # --- 4. 管理者用：フィードバック入力機能 ---
    is_mentor = any(r in u_role for r in ["管理者", "教育係", "メンター"])

    if is_mentor and not is_new:
        st.divider()
        st.subheader("👨‍🏫 指導者用フィードバック入力")
        new_comment = st.text_area("アドバイス・返信", value=current_comment, key="mentor_comment")
        if st.button("コメントを登録・同期", use_container_width=True):
            with st.spinner("反映中..."):
                df.loc[df["日付"] == current_date, "コメント"] = new_comment
                df.to_csv(DIARY_CSV, index=False, encoding="utf_8_sig")

                # 指導者側の操作も即座に同期
                try:
                    sync_user_assets(u_id, mode="upload", scope="user")
                    st.success("フィードバックを登録・同期しました。")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"同期に失敗しました: {e}")
# ==========================================
#　教育者画面
# ==========================================
def show_mentor_page():
    """教育者用コンソールのメインエントリポイント"""
    st.sidebar.markdown("### 🛠️ Mentor Console")

    # メニュー選択
    menu = st.sidebar.radio(
        "メニューを選択",
        ["👥 新人進捗ダッシュボード", "📊 全員比較マトリックス", "⚙️ マスターデータ管理"],
        key="mentor_menu_v3"
    )

    st.sidebar.divider()
    if st.sidebar.button("🏠 メインメニューへ戻る", width='stretch'):
        # 画面を戻る際にモードをリセット
        st.session_state.master_mode = "list"
        st.session_state.page = "main"
        st.rerun()

    # 各画面の呼び出し
    if menu == "👥 新人進捗ダッシュボード":
        render_dashboard_view()
    elif menu == "📊 全員比較マトリックス":
        render_matrix_view()
    elif menu == "⚙️ マスターデータ管理":
        # ここでフォームモードか一覧モードかを判定
        if st.session_state.get("master_mode") == "form":
            render_questions_form_editor()
        else:
            render_master_editor()
def render_dashboard_view():
    st.title("新人薬剤師 育成進捗一覧")

    # マスター読み込み
    if not os.path.exists(LOGIN_CSV) or not os.path.exists(TASK_CSV):
        st.error("マスターデータが見つかりません。")
        return

    df_users = pd.read_csv(LOGIN_CSV, encoding="utf_8_sig")
    newcomers = df_users[df_users['role'].isin(["新人薬剤師", "新人"])]
    df_tasks_master = pd.read_csv(TASK_CSV, encoding="utf_8_sig")

    summary_list = []
    for _, user in newcomers.iterrows():
        u_id = str(user['id'])
        p_path = os.path.join(USERS_DIR, u_id, "my_progress.csv")

        row_data = {"新人氏名": user['name'], "ID": u_id}

        # ユーザー進捗読み込み
        df_user_p = pd.read_csv(p_path, encoding="utf_8_sig") if os.path.exists(p_path) else pd.DataFrame(
            columns=['カテゴリ', '項目', '習得度'])

        # カテゴリ別に進捗率を計算
        for cat_name in ["調剤室業務", "注射室業務"]:
            # マスターからそのカテゴリの全項目を抽出
            m_sub = df_tasks_master[df_tasks_master['カテゴリ'] == cat_name]
            total_items = len(m_sub)

            if total_items > 0:
                # ユーザーデータとマスターをマージして未着手分(1)を補完
                merged = pd.merge(m_sub[['項目']], df_user_p[df_user_p['カテゴリ'] == cat_name][['項目', '習得度']], on='項目',
                                  how='left')
                merged['習得度'] = merged['習得度'].fillna(1).astype(int)

                # 進捗計算: (合計スコア - 項目数*1) / (項目数*4) ※習得度1=0%, 5=100%
                current_sum = merged['習得度'].sum()
                perc = int(((current_sum - total_items) / (total_items * 4)) * 100)
                row_data[f"{cat_name} 進捗"] = max(0, min(100, perc))
            else:
                row_data[f"{cat_name} 進捗"] = 0

        summary_list.append(row_data)

    # 進捗一覧の表示
    if summary_list:
        df_summary = pd.DataFrame(summary_list)
        st.dataframe(
            df_summary.drop(columns=["ID"]),
            column_config={
                "調剤室業務 進捗": st.column_config.ProgressColumn("調剤室", format="%d%%", min_value=0, max_value=100),
                "注射室業務 進捗": st.column_config.ProgressColumn("注射室", format="%d%%", min_value=0, max_value=100),
            },
            hide_index=True, width='stretch'
        )

    st.divider()
    selected_name = st.selectbox("詳細を確認する新人を選択", [s["新人氏名"] for s in summary_list])
    if st.button(f"👤 {selected_name} さんの個別詳細を表示", width='stretch'):
        st.session_state.target_user = next(item for item in summary_list if item["新人氏名"] == selected_name)
        st.session_state.show_detail = True

    if st.session_state.get('show_detail'):
        render_individual_detail(st.session_state.target_user, df_tasks_master)
def render_individual_detail(user, df_tasks_master):
    u_id = str(user['ID'])
    user_path = os.path.join(USERS_DIR, u_id)

    # 外部マスターと個人ファイルのパス
    QUESTIONS_CSV = "assets/spread_data/questions.csv"
    RESULTS_CSV = os.path.join(user_path, "my_all_results.csv")
    DIARY_CSV = os.path.join(user_path, "diary.csv")
    PROGRESS_CSV = os.path.join(user_path, "my_progress.csv")
    TEST_RESULTS_CSV = os.path.join(user_path, "my_test_results.csv")

    t1, t2, t3, t4 = st.tabs(["📔 日誌指導", "📋 実務進捗", "📝 テスト結果", "⚖️ 内規成績"])

    # --- T1: 日誌指導 ---
    with t1:
        if os.path.exists(DIARY_CSV):
            df_d = pd.read_csv(DIARY_CSV, encoding="utf_8_sig").fillna('')
            if not df_d.empty:
                # 文字列クレンジング
                df_d['日付'] = df_d['日付'].astype(str).str.strip()
                dates = sorted(df_d['日付'].unique().tolist(), reverse=True)
                sel_date = st.selectbox("指導日を選択", dates, key=f"d_sel_{u_id}")
                day = df_d[df_d['日付'] == sel_date].iloc[0]

                st.markdown("**【本人の記入内容】**")
                st.info(str(day['内容']).strip() if str(day['内容']).strip() != "" else "（未記入）")

                comment = st.text_area("✍ メンターコメント", value=str(day.get('コメント', '')).replace('nan', ''),
                                       key=f"cmt_{u_id}_{sel_date}")
                if st.button("指導内容を保存", width='stretch'):
                    df_d.loc[df_d['日付'] == sel_date, 'コメント'] = comment
                    df_d.to_csv(DIARY_CSV, index=False, encoding="utf_8_sig")
                    if "github_sync_engine" in globals():
                        github_sync_engine(DIARY_CSV, mode="upload")
                    st.success("保存と同期が完了しました。")
        else:
            st.info("日誌データがありません。")

    # --- T2: 実務進捗 (マスター補完ロジック) ---
    with t2:
        df_user_p = pd.read_csv(PROGRESS_CSV, encoding="utf_8_sig") if os.path.exists(PROGRESS_CSV) else pd.DataFrame(
            columns=['カテゴリ', '項目', '習得度'])
        # 警告対策: mapを使用
        df_user_p = df_user_p.map(lambda x: x.strip() if isinstance(x, str) else x)

        c1, c2 = st.columns(2)
        for i, cat in enumerate(["調剤室業務", "注射室業務"]):
            with [c1, c2][i]:
                st.markdown(f"**【{cat}】**")
                m_sub = df_tasks_master[df_tasks_master['カテゴリ'] == cat][['項目']]
                u_sub = df_user_p[df_user_p['カテゴリ'] == cat][['項目', '習得度']]
                # 未着手項目を1で補完
                display_df = pd.merge(m_sub, u_sub, on='項目', how='left').fillna(1)
                display_df['習得度'] = display_df['習得度'].astype(int)
                st.dataframe(display_df, hide_index=True, width='stretch')

    # --- T3: テスト結果 ---
    with t3:
        if os.path.exists(TEST_RESULTS_CSV):
            st.dataframe(pd.read_csv(TEST_RESULTS_CSV, encoding="utf_8_sig"), hide_index=True, width='stretch')
        else:
            st.info("テスト履歴なし")

    # --- T4: 内規成績 (review関数のロジックを完全移植) ---
    with t4:
        if not os.path.exists(QUESTIONS_CSV):
            st.error("問題マスターが見つかりません。")
        else:
            # 1. マスターから「内規」だけを抽出
            df_q_rules = pd.read_csv(QUESTIONS_CSV, encoding="utf_8_sig")
            df_q_rules = df_q_rules[df_q_rules["大項目"] == "内規"].copy()

            # 2. 個人の成績を辞書化 (最新の判定・回答を保持)
            stats = {}
            if os.path.exists(RESULTS_CSV):
                df_results = pd.read_csv(RESULTS_CSV, encoding="utf_8_sig").fillna('')
                for _, row in df_results.iterrows():
                    q_text = str(row.iloc[3]).strip()
                    stats[q_text] = {
                        "date": row.iloc[0],
                        "res": row.iloc[2],
                        "ans": row.iloc[4]
                    }

            # 3. マスター基準で表示用データを作成 (未回答も含める)
            display_data = []
            for _, row in df_q_rules.iterrows():
                q_txt = str(row["問題文"]).strip()
                h = stats.get(q_txt)

                display_data.append({
                    "最新回答日時": h["date"] if h else "-",
                    "小項目": row["小項目"],
                    "レベル": row["レベル"],
                    "問題文": q_txt,
                    "最新成績": h["res"] if h else "未回答",
                    "最新回答": h["ans"] if h else "-",
                    "解答": row["解答"],
                    "解説": row["解説"]
                })

            res_df = pd.DataFrame(display_data)

            # 4. 統計表示
            ans_count = len(res_df[res_df['最新成績'] != '未回答'])
            total_count = len(res_df)
            st.metric("内規既習率", f"{int(ans_count / total_count * 100) if total_count > 0 else 0}%",
                      f"{ans_count}/{total_count} 問")

            # 5. 成績フィルタ
            sel_res = st.selectbox("成績で絞り込み", ["すべて", "正解", "不正解", "未回答"], key=f"f_res_{u_id}")
            if sel_res != "すべて":
                res_df = res_df[res_df["最新成績"] == sel_res]

            # 6. メインテーブル (reviewページと同様)
            view_cols = ["最新回答日時", "小項目", "レベル", "問題文", "最新成績"]
            selected_event = st.dataframe(
                res_df[view_cols],
                use_container_width=True,
                height=350,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row"
            )

            # 7. 詳細プレビュー (reviewページのUIを継承)
            selected_rows = selected_event.selection.rows
            if selected_rows:
                st.divider()
                q_detail = res_df.iloc[selected_rows[0]]
                with st.container(border=True):
                    st.markdown(f"### 🔍 解答詳細プレビュー")
                    st.markdown(f"**【問題文】**\n{q_detail['問題文']}")

                    p_col1, p_col2, p_col3 = st.columns(3)
                    with p_col1:
                        st.write(f"🔹 **成績:** {q_detail['最新成績']}")
                    with p_col2:
                        st.write(f"👤 **本人の回答:** {q_detail['最新回答']}")
                    with p_col3:
                        st.write(f"📅 **最終回答日:** {q_detail['最新回答日時']}")

                    if q_detail['最新成績'] != "未回答":
                        st.success(f"**【模範解答】**\n{q_detail['解答']}")
                        st.info(f"**【解説】**\n{q_detail['解説']}")
                    else:
                        st.warning("この問題はまだ解答されていません。")

    if st.button("× 詳細を閉じる", width='stretch'):
        st.session_state.show_detail = False
        st.rerun()
def render_matrix_view():
    st.title("📊 全員比較マトリックス")

    if not os.path.exists(LOGIN_CSV) or not os.path.exists(TASK_CSV):
        st.error("マスターデータが見つかりません。")
        return

    df_users = pd.read_csv(LOGIN_CSV, encoding="utf_8_sig")
    newcomers = df_users[df_users['role'].isin(["新人薬剤師", "新人"])]
    df_tasks = pd.read_csv(TASK_CSV, encoding="utf_8_sig")

    selected_names = st.multiselect("表示する新人を選択", newcomers['name'].tolist(), default=newcomers['name'].tolist())

    if not selected_names:
        st.warning("表示対象を選択してください。")
        return

    # 全員分のスコアを辞書に格納 (読み込み回数を減らす)
    all_scores = {}
    for _, user in newcomers.iterrows():
        if user['name'] not in selected_names: continue
        p_path = f"assets/users/{user['id']}/my_progress.csv"
        if os.path.exists(p_path):
            try:
                df_p = pd.read_csv(p_path, encoding="utf_8_sig")
                # 文字列クレンジング
                df_p = df_p.map(lambda x: x.strip() if isinstance(x, str) else x)
                all_scores[user['name']] = dict(zip(df_p['項目'], df_p['習得度']))
            except:
                all_scores[user['name']] = {}
        else:
            all_scores[user['name']] = {}

    def get_score(item_name, user_name):
        v = all_scores.get(user_name, {}).get(item_name, 1)  # デフォルトは習得度1
        v_str = str(v)
        return v_str.count("★") if "★" in v_str else (int(v_str) if v_str.isdigit() else 1)

    # 業務カテゴリごとに分割表示
    categories = ["調剤室業務", "注射室業務"]
    matrix_dfs = {}

    for cat in categories:
        st.subheader(f"📍 {cat}")
        # カテゴリでフィルタリング
        df_cat = df_tasks[df_tasks['カテゴリ'] == cat].copy()

        if df_cat.empty:
            st.info(f"{cat}の項目は定義されていません。")
            continue

        # 各ユーザーの列を追加
        for name in selected_names:
            df_cat[name] = df_cat['項目'].apply(lambda x: get_score(x, name))

        # 画面表示 (1～5の数値で表示される)
        st.dataframe(df_cat, width='stretch', hide_index=True)
        matrix_dfs[cat] = df_cat

    st.divider()

    # Excelダウンロード (複数シート対応)
    if matrix_dfs:
        try:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                for cat, df_to_save in matrix_dfs.items():
                    # シート名に不適切な文字を除去して保存
                    sheet_name = cat[:31]
                    df_to_save.to_excel(writer, index=False, sheet_name=sheet_name)

                # スタイル調整（オプション：1番目のシートを選択状態に）
                writer.book.worksheets()[0].activate()

            st.download_button(
                label="📗 Excelレポートをダウンロード (全部門)",
                data=output.getvalue(),
                file_name=f"進捗比較マトリックス_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width='stretch'
            )
        except Exception as e:
            st.error(f"Excel作成エラー: {e}")
def render_master_editor():
    st.title("🛠️ マスターデータ管理GUI")

    MASTER_FILES = {
        "📖 問題マスター (questions.csv)": "assets/spread_data/questions.csv",
        "📋 実務項目 (task_list.csv)": "assets/spread_data/task_list.csv",
        "要指導・症例 (regimen_cases.csv)": "assets/spread_data/regimen_cases.csv",
        "要指導・鑑別 (kanbetsu_cases.csv)": "assets/spread_data/kanbetsu_cases.csv"
    }

    selected_label = st.selectbox("管理するデータを選択してください", list(MASTER_FILES.keys()))
    file_path = MASTER_FILES[selected_label]

    # 【重要】問題マスターの場合のみ、専用フォームへの切替ボタンを出す
    if "questions.csv" in file_path:
        with st.container(border=True):
            st.markdown("##### 📝 問題の作成・編集を効率化しませんか？")
            st.caption("大項目・小項目での絞り込みや、長文の解説入力がしやすい専用画面に切り替えます。")
            if st.button("🚀 問題作成・編集専用フォームを起動", use_container_width=True, type="primary"):
                st.session_state.master_mode = "form"
                st.rerun()
        st.divider()

    try:
        df = pd.read_csv(file_path, encoding="utf_8_sig").fillna('')
        st.subheader(f"{selected_label} の一括編集")

        edited_df = st.data_editor(
            df,
            use_container_width=True,
            num_rows="dynamic",
            hide_index=False,
            key=f"editor_{selected_label}",
            height=500
        )

        if st.button("💾 変更を確定して保存", type="secondary"):
            edited_df.to_csv(file_path, index=False, encoding="utf_8_sig")
            if "github_sync_engine" in globals():
                github_sync_engine(file_path, mode="upload")
            st.success("保存完了！")
            st.balloons()
    except Exception as e:
        st.error(f"読み込みエラー: {e}")
def render_questions_form_editor():
    st.title("📝 問題マスター：作成・修正コンソール")

    # セッション状態のリセット用
    if "edit_target_index" not in st.session_state:
        st.session_state.edit_target_index = None

    # 戻るボタン
    if st.button("⬅️ マスター管理一覧へ戻る"):
        st.session_state.master_mode = "list"
        st.session_state.edit_target_index = None
        st.rerun()

    # パス設定
    QUESTIONS_CSV = "assets/spread_data/questions.csv"
    LIB_CSV = "assets/spread_data/integrated_materials.csv"
    LIB_STORAGE_DIR = "assets/drive_data/materials"

    # データ読み込み
    if os.path.exists(QUESTIONS_CSV):
        df_q = pd.read_csv(QUESTIONS_CSV, encoding="utf_8_sig").fillna("")
    else:
        df_q = pd.DataFrame(columns=["大項目", "小項目", "形式", "レベル", "問題文", "解答", "解説", "資料タイトル", "作成者"])

    # カテゴリー定義（共通利用）
    sub_categories = {
        "内規": ["調剤室業務", "注射室業務"],
        "薬剤": ["精神神経・筋疾患", "骨・関節疾患", "免疫疾患", "心臓・血管系疾患", "腎・泌尿器疾患", "産科婦人科疾患", "呼吸器疾患", "消化器疾患", "血液及び造血器疾患",
               "感覚器疾患", "内分泌・代謝疾患", "皮膚疾患", "感染症", "悪性腫瘍", "その他"],
        "チーム": ["感染", "栄養", "緩和"],
        "その他": ["その他"]
    }

    # --- 0. モード選択と既存データの読み込み ---
    with st.container(border=True):
        mode = st.radio("作業モード", ["🆕 新規作成", "✏️ 既存問題の修正"], horizontal=True)

        target_row = None
        if mode == "✏️ 既存問題の修正":
            # 🔍 問題検索フィルタ（大項目・小項目の2段階）
            c_search1, c_search2, c_search3 = st.columns([1, 1, 2])
            with c_search1:
                search_maj = st.selectbox("大項目で絞り込み", ["すべて"] + list(sub_categories.keys()), key="edit_search_maj")
            with c_search2:
                search_min_opts = ["すべて"] + sub_categories.get(search_maj, []) if search_maj != "すべて" else ["すべて"]
                search_min = st.selectbox("小項目で絞り込み", search_min_opts, key="edit_search_min")

            # フィルタリング実行
            filtered_df = df_q.copy()
            if search_maj != "すべて":
                filtered_df = filtered_df[filtered_df["大項目"] == search_maj]
            if search_min != "すべて":
                filtered_df = filtered_df[filtered_df["小項目"] == search_min]

            with c_search3:
                selected_q_text = st.selectbox("修正する問題を選択", filtered_df["問題文"].tolist(), key="edit_select_q")

            if selected_q_text:
                target_row = df_q[df_q["問題文"] == selected_q_text].iloc[0]
                st.session_state.edit_target_index = df_q[df_q["問題文"] == selected_q_text].index[0]
                st.info(f"💡 編集モード：{selected_q_text[:40]}...")

    # --- 1. 基本設定 ---
    with st.container(border=True):
        st.markdown("##### 1. カテゴリー・形式・レベル設定")
        c1, c2, c3, c4 = st.columns(4)

        def get_val(key, default):
            return target_row[key] if target_row is not None and key in target_row else default

        with c1:
            major = st.selectbox("親カテゴリー", list(sub_categories.keys()),
                                 index=list(sub_categories.keys()).index(get_val("大項目", "内規")) if get_val("大項目",
                                                                                                          "内規") in sub_categories else 0)
        with c2:
            current_subs = sub_categories.get(major, ["その他"])
            minor = st.selectbox("小カテゴリー", current_subs,
                                 index=current_subs.index(get_val("小項目", "")) if get_val("小項目",
                                                                                         "") in current_subs else 0)
        with c3:
            q_types = ["〇×問題", "4択問題 (単一選択)", "4択問題 (複数選択可)", "記述問題"]
            q_type = st.selectbox("問題形式", q_types,
                                  index=q_types.index(get_val("形式", "〇×問題")) if get_val("形式", "〇×問題") in q_types else 0)
        with c4:
            level = st.select_slider("難易度レベル", options=["★", "★★", "★★★", "★★★★"], value=get_val("レベル", "★"))

    # --- 2. 問題・解答 ---
    with st.container(border=True):
        st.markdown("##### 2. 問題文と解答")
        question_text = st.text_area("問題文を入力してください", value=get_val("問題文", ""), height=100)

        raw_ans = get_val("解答", "")
        answer_data = ""

        if q_type == "〇×問題":
            ans_val = st.radio("正解を選択", ["〇", "×"], index=0 if raw_ans != "×" else 1, horizontal=True)
            answer_data = ans_val
        elif "4択問題" in q_type:
            cols = st.columns(2)
            choices = ["", "", "", ""]
            correct_indices = []
            if "|" in raw_ans:
                parts = raw_ans.split("|")
                correct_indices = parts[0].split(",")
                choices = (parts[1:] + ["", "", "", ""])[:4]

            final_choices, final_corrects = [], []
            for i in range(4):
                with cols[i % 2]:
                    is_correct = st.checkbox(f"正解設定 {i + 1}", value=str(i + 1) in correct_indices, key=f"ans_chk_{i}")
                    choice_text = st.text_input(f"選択肢 {i + 1}", value=choices[i], key=f"choice_{i}")
                    final_choices.append(choice_text)
                    if is_correct: final_corrects.append(str(i + 1))
            answer_data = f"{','.join(final_corrects)}|{'|'.join(final_choices)}"
        else:
            answer_data = st.text_input("正解（模範解答）を入力", value=raw_ans)

    # --- 3. 解説・資料連携 (★資料検索フィルタ機能付) ---
    with st.container(border=True):
        st.markdown(f"##### 3. 解説と参考資料")
        explanation = st.text_area("解説文", value=get_val("解説", ""), height=150)

        st.divider()
        ref_mode = st.radio("資料設定方法", ["既存のライブラリから選択", "新しく資料を登録", "資料なし"], horizontal=True)

        final_ref_title = get_val("資料タイトル", "")
        final_file_name = ""

        if ref_mode == "既存のライブラリから選択":
            if os.path.exists(LIB_CSV):
                df_lib = pd.read_csv(LIB_CSV, encoding="utf_8_sig").fillna("")

                st.info("💡 初期設定で現在の小カテゴリが選択されています。必要に応じて変更してください。")
                col_lib_f1, col_lib_f2 = st.columns(2)
                with col_lib_f1:
                    lib_p_filter = st.selectbox("資料：大カテゴリで絞り込み", ["すべて"] + list(sub_categories.keys()),
                                                index=list(sub_categories.keys()).index(major) + 1,
                                                key="lib_filter_maj")
                with col_lib_f2:
                    lib_min_opts = ["すべて"] + sub_categories.get(lib_p_filter, []) if lib_p_filter != "すべて" else ["すべて"]
                    initial_idx = lib_min_opts.index(minor) if minor in lib_min_opts else 0
                    lib_c_filter = st.selectbox("資料：小カテゴリで絞り込み", lib_min_opts, index=initial_idx, key="lib_filter_min")

                temp_lib = df_lib.copy()
                if lib_p_filter != "すべて":
                    temp_lib = temp_lib[temp_lib["大カテゴリー"] == lib_p_filter]
                if lib_c_filter != "すべて":
                    temp_lib = temp_lib[temp_lib["小カテゴリー"] == lib_c_filter]

                if not temp_lib.empty:
                    selected_display = st.selectbox("資料を選択", temp_lib["タイトル"].tolist(), key="lib_select_final")
                    lib_row = temp_lib[temp_lib["タイトル"] == selected_display].iloc[0]
                    final_ref_title = lib_row["タイトル"]
                else:
                    st.warning("条件に一致する資料が見つかりません。")
            else:
                st.error("資料ライブラリ(CSV)が見つかりません。")

        elif ref_mode == "新しく資料を登録":
            c_r1, c_r2 = st.columns(2)
            with c_r1:
                final_ref_title = st.text_input("資料タイトル")
            with c_r2:
                new_ref_type = st.radio("形式", ["FILE", "URL"], horizontal=True)

            if new_ref_type == "FILE":
                new_file = st.file_uploader("ファイルをアップロード", type=["pdf", "pptx", "docx"])
                if new_file: final_file_name = new_file.name
            else:
                final_url = st.text_input("参照URLを入力")

            ref_detail = st.text_area("資料の説明（ライブラリ用）", height=70)

    # --- 4. 登録・上書き実行 ---
    st.divider()
    btn_label = "💾 修正内容を保存（上書き）" if mode == "✏️ 既存問題の修正" else "🚀 新規問題を登録"

    if st.button(btn_label, type="primary", width='stretch'):
        if not question_text:
            st.error("問題文は必須です。")
            return

        try:
            # 資料ライブラリへの追加
            if ref_mode == "新しく資料を登録" and final_ref_title:
                if 'new_file' in locals() and new_file:
                    os.makedirs(LIB_STORAGE_DIR, exist_ok=True)
                    with open(os.path.join(LIB_STORAGE_DIR, final_file_name), "wb") as f:
                        f.write(new_file.getbuffer())

                df_lib_all = pd.read_csv(LIB_CSV, encoding="utf_8_sig") if os.path.exists(LIB_CSV) else pd.DataFrame(
                    columns=["大カテゴリー", "小カテゴリー", "タイトル", "タイプ", "ファイル名", "URL", "登録者"])
                new_lib_row = {
                    "大カテゴリー": major, "小カテゴリー": minor, "タイトル": final_ref_title,
                    "タイプ": "URL" if 'final_url' in locals() and final_url else "FILE",
                    "ファイル名": final_file_name, "URL": final_url if 'final_url' in locals() else "",
                    "登録者": st.session_state.user.get('name', 'admin')
                }
                df_lib_all = pd.concat([df_lib_all, pd.DataFrame([new_lib_row])], ignore_index=True)
                df_lib_all.to_csv(LIB_CSV, index=False, encoding="utf_8_sig")

            # 問題データの登録・更新
            new_data = {
                "大項目": major, "小項目": minor, "形式": q_type, "レベル": level,
                "問題文": question_text, "解答": answer_data, "解説": explanation,
                "資料タイトル": final_ref_title, "作成者": st.session_state.user.get('name', 'admin')
            }

            if mode == "✏️ 既存問題の修正":
                df_q.iloc[st.session_state.edit_target_index] = new_data
            else:
                df_q = pd.concat([df_q, pd.DataFrame([new_data])], ignore_index=True)

            df_q.to_csv(QUESTIONS_CSV, index=False, encoding="utf_8_sig")

            # 同期処理
            if "github_sync_engine" in globals():
                github_sync_engine(QUESTIONS_CSV, mode="upload")
                if ref_mode == "新しく資料を登録":
                    github_sync_engine(LIB_CSV, mode="upload")

            st.success("✅ 保存が完了しました。")
            st.balloons()
            time.sleep(1)
            st.rerun()

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
# ==========================================
#　検索関連
# ==========================================
def show_search_page():
    st.title("🔍 P-QUEST 統合検索システム")

    # 検索対象ファイルの設定
    target_csvs = {
        "forum_master.csv": "💬 掲示板",
        "materials.csv": "📚 資料マスター",
        "questions.csv": "📝 問題データ"
    }
    pdf_cache_dir = os.path.join(OUT_DATA_DIR, "study", ".pdf_cache")

    # --- レイアウト: 2カラム (メイン検索 | トレンド) ---
    col_main, col_rank = st.columns([3, 1])

    with col_main:
        # 検索入力
        search_query = st.text_input("検索キーワードを入力", placeholder="調べたい用語を入力してEnter", key="search_input")

        if search_query:
            # 履歴の保存
            save_search_log(search_query)

            # 検索実行
            results = []

            # 1. CSV検索
            for filename, label in target_csvs.items():
                path = os.path.join(IN_DATA_DIR, filename)
                if os.path.exists(path):
                    try:
                        with open(path, "r", encoding="utf_8_sig", errors="ignore") as f:
                            reader = csv.reader(f)
                            for i, row in enumerate(reader, 1):
                                line_text = " | ".join(row)
                                if search_query.lower() in line_text.lower():
                                    results.append({
                                        "種別": label,
                                        "場所": f"{filename} (L{i})",
                                        "内容抜粋": line_text
                                    })
                    except:
                        pass

            # 2. PDFキャッシュ検索
            if os.path.exists(pdf_cache_dir):
                for file in os.listdir(pdf_cache_dir):
                    if search_query.lower() in file.lower():
                        results.append({
                            "種別": "📄 PDF資料",
                            "場所": ".pdf_cache",
                            "内容抜粋": f"ファイル名: {file}"
                        })

            # 結果表示
            if results:
                st.success(f"{len(results)} 件のヒットがありました。")
                df_res = pd.DataFrame(results)
                st.dataframe(df_res, width='stretch', hide_index=True)
            else:
                st.error("一致する情報が見つかりませんでした。")

    with col_rank:
        st.markdown("### 🔥 検索トレンド")
        ranking = get_search_ranking()
        if ranking:
            for i, (word, freq) in enumerate(ranking, 1):
                # クリックしたら検索される仕組みをボタンで再現
                if st.button(f"{i}. {word} ({freq}回)", key=f"rank_{i}", width='stretch'):
                    # クエリをセットして再実行するためにsession_stateを利用
                    st.session_state.search_input = word
                    st.rerun()
        else:
            st.write("履歴がありません")

    st.divider()
    if st.button("🏠 メインメニューへ戻る", width='stretch'):
        st.session_state.page = "main"
        st.rerun()
def save_search_log(query):
    """個人の検索履歴を保存（assets/users/ID/search_history.csv）"""
    if 'user' not in st.session_state: return

    user_id = st.session_state['user']['id']
    user_dir = os.path.join(ASSETS_DIR, "users", str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    log_path = os.path.join(user_dir, "search_history.csv")

    with open(log_path, "a", encoding="utf_8_sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), query])
def get_search_ranking():
    """全ユーザーの履歴を集計して上位10件を返す"""
    all_queries = []
    users_base = os.path.join(ASSETS_DIR, "users")

    if os.path.exists(users_base):
        for uid in os.listdir(users_base):
            log_path = os.path.join(users_base, uid, "search_history.csv")
            if os.path.exists(log_path):
                try:
                    with open(log_path, "r", encoding="utf_8_sig") as f:
                        reader = csv.reader(f)
                        for row in reader:
                            if len(row) >= 2: all_queries.append(row[1])
                except:
                    pass

    return Counter(all_queries).most_common(10)
# ==========================================
#　シミュレーション関連
# ==========================================
def show_simulation_page():
    # サブページの初期化
    if 'sub_page' not in st.session_state:
        st.session_state['sub_page'] = 'menu'

    # 1. メニュー画面
    if st.session_state['sub_page'] == 'menu':
        st.markdown("## 🎮 シミュレーション・トレーニング")
        st.write("トレーニングしたい項目を選択してください。")

        col1, col2, col3 = st.columns(3)

        with col1:
            with st.container(border=True):
                st.subheader("💊 持参薬鑑別")
                st.write("お薬手帳と現物を確認し、鑑別報告書を作成する練習です。")
                if st.button("持参薬鑑別を始める", width='stretch', type="primary"):
                    st.session_state['sub_page'] = 'kanbetsu'
                    st.rerun()

        with col2:
            with st.container(border=True):
                st.subheader("🧪 レジメン監査")
                st.write("プロトコルに基づき、抗がん剤の処方監査を練習します。")
                if st.button("レジメン監査を始める", width='stretch', type="primary"):
                    st.session_state['sub_page'] = 'regimen'
                    st.rerun()

        with col3:
            with st.container(border=True):
                st.subheader("📈 TDM解析練習")
                st.write("VCM/TEICの血中濃度予測と初期投与設計を練習します。")
                if st.button("TDM練習を始める", width='stretch', type="primary"):
                    st.session_state['sub_page'] = 'tdm_practice'
                    st.rerun()

        st.divider()
        if st.button("🏠 メインメニューへ戻る"):
            st.session_state['page'] = 'main'
            st.rerun()

    # 各ページへのルーティング
    elif st.session_state['sub_page'] == 'kanbetsu':
        show_kanbetsu_practice()
    elif st.session_state['sub_page'] == 'regimen':
        show_regimen_simulation()
    elif st.session_state['sub_page'] == 'tdm_practice':
        show_tdm_simulation()
def show_kanbetsu_practice():
    # --- 1. 厳格なユーザー特定 ---
    if 'user' not in st.session_state or not st.session_state['user'].get('id'):
        st.error("❌ ログイン情報が確認できません。一度ログアウトして再度ログインしてください。")
        if st.button("ログイン画面へ"):
            st.session_state.clear()
            st.rerun()
        return

    user_id = st.session_state['user']['id']
    user_dir = f"assets/users/{user_id}"

    if not os.path.exists(user_dir):
        os.makedirs(user_dir, exist_ok=True)

    st.markdown("### 💊 持参薬鑑別トレーニング")

    # --- 2. データの読み込み (文字化け・KeyError対策版) ---
    @st.cache_data
    def load_data():
        m_path = "assets/spread_data/drug_master.csv"
        # 鑑別用のケースファイル。シミュレーションと共通化している場合はファイル名に注意
        c_path = "assets/spread_data/kanbetsu_cases.csv"

        # BOM付きUTF-8(Excel/PyCharm)を安全に読み込むための encoding='utf-8-sig'
        def safe_read_csv(path):
            if os.path.exists(path):
                tmp_df = pd.read_csv(path, encoding="utf_8_sig")
                # カラム名に含まれるBOMや空白、引用符を徹底的に掃除
                tmp_df.columns = tmp_df.columns.str.strip().str.replace('"', '').str.replace("'", "")
                return tmp_df
            return pd.DataFrame()

        m_df = safe_read_csv(m_path)
        if m_df.empty:
            m_df = pd.DataFrame(columns=["品名"])

        c_df = safe_read_csv(c_path)
        return m_df, c_df

    master_df, cases_df = load_data()

    if cases_df.empty:
        st.error("症例データ(kanbetsu_cases.csv)が見つからないか、空です。")
        return

    # --- 3. 患者選択と状態管理 ---
    # ここで cases_df["case_id"] の KeyError を防ぐため、str.strip() 済みのカラムを使用
    target_id = st.sidebar.selectbox(
        "演習する症例を選択",
        options=cases_df["case_id"].tolist(),
        format_func=lambda x: f"ID:{x}"
    )

    if "last_case_id" not in st.session_state or st.session_state.last_case_id != target_id:
        st.session_state.target_med_idx = 0
        st.session_state.last_case_id = target_id
        st.session_state.show_results = False
        # ウィジェットのキーをリセット
        for key in list(st.session_state.keys()):
            if any(key.startswith(prefix) for prefix in ["sb_", "ds_", "us_", "dy_", "rm_", "cm_"]):
                del st.session_state[key]

    # 症例の抽出
    selected_case = cases_df[cases_df["case_id"] == target_id].iloc[0]

    # 鑑別データ構造の解析 (handbooksカラム)
    parts = selected_case["handbooks"].split(",")
    hospital_name = parts[0]
    raw_meds = parts[1].split("/")

    parsed_handbook = []
    for m_str in raw_meds:
        m = m_str.split(":")
        if len(m) >= 5:
            drug_full = m[0]
            drug_name = drug_full.split(".", 1)[1] if "." in drug_full else drug_full
            parsed_handbook.append({
                "name": drug_name.strip(),
                "dose": m[1].strip(),
                "usage": m[2].strip(),
                "days": m[3].strip(),
                "stock": m[4].strip()
            })

    # --- 4. 上部UI：手帳参照と現物確認 ---
    col_left, col_right = st.columns([1, 1])
    with col_left:
        st.markdown(
            f'<div style="background-color: white; padding: 10px; border: 1px solid #ccc; border-radius: 5px; color: #333; font-family: \'MS Gothic\', sans-serif;"><b>{selected_case["patient_name"]} 様</b> ({hospital_name})</div>',
            unsafe_allow_html=True)
        for i, med in enumerate(parsed_handbook):
            bg = "#f0f8ff" if i == st.session_state.target_med_idx else "transparent"
            st.markdown(
                f'<div style="background-color: {bg}; border-bottom: 1px solid #eee; padding: 4px; font-size: 0.8em; color: #333;">{i + 1}) {med["name"]} {med["dose"]} 【{med["usage"]}】</div>',
                unsafe_allow_html=True)

    with col_right:
        curr_idx = st.session_state.target_med_idx
        target_med = parsed_handbook[curr_idx]
        st.info(f"現物確認中：**{target_med['name']}**")
        c1, c2, c3 = st.columns([1, 1.5, 1])
        if c1.button("⬅️ 前へ", use_container_width=True) and curr_idx > 0:
            st.session_state.target_med_idx -= 1
            st.rerun()
        c2.write(f"<center>{curr_idx + 1} / {len(parsed_handbook)}剤目</center>", unsafe_allow_html=True)
        if c3.button("次へ ➡️", use_container_width=True) and curr_idx < len(parsed_handbook) - 1:
            st.session_state.target_med_idx += 1
            st.rerun()

        # アイコン表示 (残薬数に応じて表示)
        try:
            stock_num = int(target_med['stock'])
        except:
            stock_num = 0

        icon = "💊" if "カプセル" in target_med['name'] else "⚪"
        icons_html = "".join(
            [f"<span style='font-size: 20px;'>{icon}</span>" + ("<br>" if (j + 1) % 10 == 0 else "") for j in
             range(stock_num)])
        st.markdown(
            f'<div style="background-color: #f8f9fa; padding: 10px; border: 1px solid #ddd; border-radius: 10px; text-align: center; min-height: 120px;">{icons_html}</div>',
            unsafe_allow_html=True)

    st.divider()

    # --- 5. 入力グリッド ---
    st.markdown("#### 【鑑別登録】")

    def calc_update(idx, mode):
        try:
            def get_val(key):
                s = st.session_state.get(key, "0")
                if not s: return 0.0
                return float(''.join(filter(lambda x: x.isdigit() or x == '.', str(s))))

            dose = get_val(f"ds_{idx}")
            if mode == "days":
                st.session_state[f"rm_{idx}"] = str(int(dose * get_val(f"dy_{idx}")))
            elif mode == "rem":
                if dose > 0:
                    st.session_state[f"dy_{idx}"] = str(int(get_val(f"rm_{idx}") / dose))
        except:
            pass

    usage_list = [
        "", "1日1回起床時", "1日1回朝食前", "1日1回朝食直前", "1日1回朝食直後", "1日1回朝食後",
        "1日1回昼食前", "1日1回昼食直後", "1日1回昼食後", "1日1回夕食前", "1日1回夕食直前", "1日1回夕食直後", "1日1回夕食後",
        "1日1回就寝前", "1日1回空腹時", "1日2回朝食前と就寝前", "1日2回朝食後と就寝前", "1日2回朝昼食前", "1日2回朝昼食後",
        "1日2回朝夕食前", "1日2回朝夕食直前", "1日2回朝夕食直後", "1日2回朝夕食後", "1日2回昼夕食前", "1日2回昼夕食後",
        "1日2回夕食前と就寝前", "1日2回夕食後と就寝前", "1日3回朝昼夕食前", "1日3回朝昼夕食直前", "1日3回朝昼夕食直後", "1日3回朝昼夕食後",
        "1日3回朝食後・昼食後・就寝前", "1日3回朝食後・夕食後・就寝前", "1日4回朝昼夕食前と就寝前", "1日4回朝昼夕食後と就寝前",
        "頓用(疼痛時)", "頓用(発熱時)", "頓用(不眠時)", "頓用(便秘時)", "頓用(発作時)", "1日1回貼付", "1日2回貼付", "1日1回外用"
    ]

    h_cols = st.columns([0.5, 3.0, 0.8, 1.8, 0.7, 0.7, 1.5])
    for col, label in zip(h_cols, ["No", "薬品名", "1日量", "用法", "日数", "残数", "全判定"]):
        col.write(f"**{label}**")

    total_error_cells = 0
    mistake_log_details = []

    for i in range(len(parsed_handbook)):
        ans = parsed_handbook[i]
        cols = st.columns([0.5, 3.0, 0.8, 1.8, 0.7, 0.7, 1.5])
        cols[0].write(f"{i + 1}")

        u_name = cols[1].selectbox(f"drug_{i}", options=[""] + master_df["品名"].tolist(), label_visibility="collapsed",
                                   key=f"sb_{i}")
        u_dose = cols[2].text_input("量", label_visibility="collapsed", key=f"ds_{i}")
        u_usage = cols[3].selectbox("用", options=usage_list, label_visibility="collapsed", key=f"us_{i}")
        u_days = cols[4].text_input("日", label_visibility="collapsed", key=f"dy_{i}", on_change=calc_update,
                                    args=(i, "days"))
        u_rem = cols[5].text_input("残", label_visibility="collapsed", key=f"rm_{i}", on_change=calc_update,
                                   args=(i, "rem"))

        if st.session_state.get("show_results"):
            def norm(v):
                val = str(v).strip().replace("錠", "").replace("g", "")
                return val if val != "" else "EMPTY_VALUE_ERROR"

            err_list = []
            if u_name != ans["name"]: err_list.append("薬")
            if norm(u_dose) != norm(ans["dose"]): err_list.append("量")
            if u_usage != ans["usage"]: err_list.append("法")
            if norm(u_days) != norm(ans["days"]): err_list.append("日")
            if norm(u_rem) != norm(ans["stock"]): err_list.append("残")

            if not err_list:
                cols[6].success("✅ Clear")
            else:
                cols[6].error(f"❌ {' '.join(err_list)}")
                total_error_cells += len(err_list)
                mistake_log_details.append(f"Rp{i + 1}:{''.join(err_list)}")

    if st.button("🏁 判定して記録を保存", use_container_width=True, type="primary"):
        st.session_state.show_results = True
        log_entry = pd.DataFrame([{
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "case_id": target_id,
            "mistake_count": total_error_cells,
            "details": "|".join(mistake_log_details)
        }])

        log_file = f"assets/users/{user_id}/kanbetsu_history.csv"
        # 保存時も utf_8_sig で保存することで、次に開く時も文字化けしない
        log_entry.to_csv(log_file, mode='a', header=not os.path.exists(log_file), index=False, encoding="utf_8_sig")
        st.rerun()
def show_regimen_simulation():
    # --- 1. スタイル定義 ---
    st.markdown("""
        <style>
        .matrix-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; background-color: white; table-layout: fixed; }
        .matrix-table th, .matrix-table td { border: 1px solid #666 !important; padding: 4px; text-align: center; }
        .row-label { background-color: #e0e0e0 !important; font-weight: bold; text-align: left !important; width: 150px; }
        .sub-label { background-color: #f9f9f9 !important; text-align: left !important; padding-left: 10px !important; width: 120px; }
        .header-dark { background-color: #444 !important; color: white !important; }
        .header-gray { background-color: #eee !important; font-weight: bold; }
        .mark-dot { color: blue !important; font-weight: bold; font-size: 1.1rem; }
        .mark-star { color: orange !important; font-weight: bold; font-size: 1.1rem; }
        .desc-box { font-size: 0.75rem; color: #555; background-color: #f0f2f6; padding: 10px; border-radius: 5px; margin-top: 10px; }
        </style>
    """, unsafe_allow_html=True)

    # --- 2. データロード ---
    current_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(current_dir, "assets", "spread_data")
    # 集約型CSVを使用
    df_cases = pd.read_csv(os.path.join(data_dir, "regimen_cases.csv"))

    # 患者選択
    patient_names = df_cases['patient_name'].unique().tolist()
    selected_name = st.sidebar.selectbox("患者氏名", patient_names)

    # 対象患者の全薬剤データを取得
    patient_data = df_cases[df_cases['patient_name'] == selected_name]
    case = patient_data.iloc[0]  # 身体情報は最初の1行から取得
    p_id = str(case['case_id'])

    # --- 3. 最上部：医師連絡 / カルテメモ ---
    st.error(f"📋 **医師連絡 / カルテメモ**\n\n{case['memo'] if pd.notna(case['memo']) else '特記事項なし'}")

    # --- 4. セッション管理 ---
    for key in [f"audit_mark_{p_id}", f"audit_memo_{p_id}", f"check_mark_{p_id}", f"check_memo_{p_id}"]:
        if key not in st.session_state: st.session_state[key] = ""
    if f"show_cust_{p_id}" not in st.session_state: st.session_state[f"show_cust_{p_id}"] = False

    # 各薬剤のカスタム比率（％）を初期化
    for _, drug in patient_data.iterrows():
        k = f"r_{p_id}_{drug['drug_name']}"
        if k not in st.session_state:
            st.session_state[k] = float(drug['cust_curr'])

    # --- 5. 操作パネル ---
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**🖋️ 判定入力**")
        st.selectbox("監査 判定", ["", "●", "★"], key=f"sel_a_{p_id}")
        st.text_input("監査 備考", key=f"mem_a_{p_id}")
        st.selectbox("当日確認 判定", ["", "●", "★"], key=f"sel_c_{p_id}")
        st.text_input("当日 備考", key=f"mem_c_{p_id}")
        if st.button("反映"):
            st.session_state[f"audit_mark_{p_id}"] = st.session_state[f"sel_a_{p_id}"]
            st.session_state[f"audit_memo_{p_id}"] = st.session_state[f"mem_a_{p_id}"]
            st.session_state[f"check_mark_{p_id}"] = st.session_state[f"sel_c_{p_id}"]
            st.session_state[f"check_memo_{p_id}"] = st.session_state[f"mem_c_{p_id}"]
            st.rerun()
    with col2:
        st.markdown("**⚙️ レジメンカスタム**")
        if st.button("設定を開く/閉じる"):
            st.session_state[f"show_cust_{p_id}"] = not st.session_state[f"show_cust_{p_id}"]
            st.rerun()
        if st.session_state[f"show_cust_{p_id}"]:
            for _, drug in patient_data.iterrows():
                k = f"r_{p_id}_{drug['drug_name']}"
                st.session_state[k] = st.number_input(f"{drug['drug_name']} (%)", value=st.session_state[k],
                                                      key=f"num_{k}")

    # --- 6. 日付・Day設定 ---
    prev_label, today_label, next_label = "前回", "2/20", "2/21 (明日)"

    # CSVのcycle_daysを「今日のDay数」として取得
    today_day_count = case['cycle_days']
    today_day_val = f"Day {today_day_count}"

    # --- 7. 計算関数 ---
    def calc_bsa(w, h):
        return 0.007184 * (w ** 0.425) * (h ** 0.725)

    def calc_ccr(age, w, cre, sex):
        res = ((140 - age) * w) / (72 * cre)
        return res * 0.85 if sex == '女' else res

    def get_reco_mg(drug_row, weight, cre):
        base = float(drug_row['base_dose'])
        if drug_row['calc_type'] == 'bsa':
            return base * calc_bsa(weight, drug_row['height'])
        if drug_row['calc_type'] == 'calvert':
            ccr = calc_ccr(drug_row['age'], weight, cre, drug_row['sex'])
            return base * (min(ccr, 125) + 25)
        return base

    # --- 8. HTML構築 ---
    h = "<table class='matrix-table'>"
    h += f"<tr class='header-dark'><th colspan='2'>日付</th><th>{prev_label}</th><th>{today_label}</th><th>{next_label}</th></tr>"

    # day行の修正：今日はDay [cycle_days]、明日はDay 1
    h += f"<tr class='header-gray'><th colspan='2'>day</th><td>Day 1</td><td>{today_day_val}</td><td>Day 1</td></tr>"

    h += f"<tr><td colspan='2' class='row-label'>監査判定</td><td></td><td></td><td><span class='mark-dot'>{st.session_state[f'audit_mark_{p_id}']}</span></td></tr>"
    h += f"<tr><td colspan='2' class='row-label'>備考 (監査)</td><td></td><td></td><td>{st.session_state[f'audit_memo_{p_id}']}</td></tr>"
    h += f"<tr><td colspan='2' class='row-label'>当日確認</td><td></td><td></td><td><span class='mark-star'>{st.session_state[f'check_mark_{p_id}']}</span></td></tr>"
    h += f"<tr><td colspan='2' class='row-label'>備考 (当日)</td><td></td><td></td><td>{st.session_state[f'check_memo_{p_id}']}</td></tr>"

    h += "<tr class='header-gray'><td colspan='5' style='text-align:left; padding-left:10px;'>【身体情報】</td></tr>"
    h += f"<tr><td colspan='2' class='sub-label'>体重 (kg) / Cre</td><td>{case['weight_prev']} / {case['cre_prev']}</td><td></td><td>{case['weight_curr']} / {case['cre_curr']}</td></tr>"
    h += f"<tr><td colspan='2' class='sub-label'>BSA (m²)</td><td>{calc_bsa(case['weight_prev'], case['height']):.2f}</td><td></td><td>{calc_bsa(case['weight_curr'], case['height']):.2f}</td></tr>"

    for _, drug in patient_data.iterrows():
        # 推奨量(100%)の算出
        reco_prev_100 = get_reco_mg(drug, drug['weight_prev'], drug['cre_prev'])
        reco_curr_100 = get_reco_mg(drug, drug['weight_curr'], drug['cre_curr'])

        # カスタム比率適用後の推奨
        c_ratio_curr = st.session_state[f"r_{p_id}_{drug['drug_name']}"]
        reco_final_curr = reco_curr_100 * (c_ratio_curr / 100)
        reco_final_prev = reco_prev_100 * (drug['cust_prev'] / 100)

        # 実際のOrder量
        prev_order = drug['order_prev']
        curr_order = drug['order_curr']

        # パーセンテージ計算
        p_ratio_prev = (prev_order / reco_prev_100 * 100) if reco_prev_100 > 0 else 0
        p_ratio_curr = (curr_order / reco_curr_100 * 100) if reco_curr_100 > 0 else 0
        s_ratio_prev = (prev_order / reco_final_prev * 100) if reco_final_prev > 0 else 0
        s_ratio_curr = (curr_order / reco_final_curr * 100) if reco_final_curr > 0 else 0

        # 単位ラベル
        unit = "AUC" if drug['calc_type'] == 'calvert' else "mg/m²"
        dose_label = f"{drug['base_dose']} {unit}"

        h += f"<tr class='header-gray'><td colspan='5' style='text-align:left; padding-left:10px;'>【{drug['drug_name']}】</td></tr>"
        h += f"<tr><td rowspan='3' class='row-label'>投与量確認</td><td class='sub-label'>設定用量</td><td>{dose_label}</td><td></td><td>{dose_label}</td></tr>"
        h += f"<tr><td class='sub-label'>推奨 (mg)</td><td>{reco_prev_100:.1f} ({p_ratio_prev:.1f}%)</td><td></td><td>{reco_curr_100:.1f} ({p_ratio_curr:.1f}%)</td></tr>"
        h += f"<tr><td class='sub-label'>Order (mg)</td><td>{prev_order:.1f} ({s_ratio_prev:.1f}%)</td><td></td><td>{curr_order:.1f} ({s_ratio_curr:.1f}%)</td></tr>"

    h += "</table>"
    st.markdown(h, unsafe_allow_html=True)

    # --- 9. 説明追記 ---
    st.markdown("""
        <div class='desc-box'>
            <strong>【パーセンテージの定義】</strong><br>
            ・<strong>推奨量(mg)の隣</strong>：標準量(100% dose)の推奨量に対して、実際のオーダー量が何％にあたるかを表示。<br>
            ・<strong>Order(mg)の隣</strong>：カスタム設定(○○% dose)で算出された推奨量に対して、実際のオーダー量が何％にあたるかを表示。
        </div>
    """, unsafe_allow_html=True)

    st.divider()
# ==========================================
# TDMシミュレーション
# ==========================================
def model_2comp_infusion(y, t, k10, k12, k21, v1, r_inf):
    C1, C2 = y
    dc1dt = (r_inf / v1) - (k10 + k12) * C1 + k21 * C2
    dc2dt = k12 * C1 - k21 * C2
    return [dc1dt, dc2dt]
def solve_pk_single(dose_df, pk, max_t):
    t_eval = np.arange(0, float(max_t) + 0.5, 0.5)
    # 最終的な濃度を入れる箱（0で初期化）
    total_conc = np.zeros_like(t_eval)

    # パラメータの取り出し
    k10, k12, k21, v1 = pk['k10'], pk['k12'], pk['k21'], pk['V1']

    # 2コンパートメントモデルの解析解（点滴静注）に必要な定数を計算
    sum_k = k10 + k12 + k21
    prod_k = k10 * k21
    alpha = 0.5 * (sum_k + np.sqrt(sum_k ** 2 - 4 * prod_k))
    beta = 0.5 * (sum_k - np.sqrt(sum_k ** 2 - 4 * prod_k))

    A = (alpha - k21) / (v1 * (alpha - beta))
    B = (k21 - beta) / (v1 * (alpha - beta))

    # 全ての投与指示をループして「重ね掛け」
    for _, d in dose_df.iterrows():
        # --- ここからガードレール ---
        # 必須項目がNaN（空）または不完全な場合は、この行の計算をスキップする
        try:
            if pd.isna(d['1回量(mg)']) or pd.isna(d['回数']) or pd.isna(d['rel_t']) or pd.isna(d['投与時間(h)']):
                continue

            # 数値変換を試みる（ここで失敗しても計算が止まらないようにする）
            dose_amt = float(d['1回量(mg)'])
            inf_time = float(d['投与時間(h)'])
            rel_t = float(d['rel_t'])
            num_doses = int(float(d['回数']))
            interval = float(d['投与間隔(h)']) if not pd.isna(d['投与間隔(h)']) else 0

            # 意味のないデータ（1回量0や回数0）は無視
            if dose_amt <= 0 or num_doses <= 0 or inf_time <= 0:
                continue
        except (ValueError, TypeError):
            # 万が一数値変換に失敗しても、エラーを出さずに次の行へ
            continue
        # --- ここまでガードレール ---

        r_inf = dose_amt / inf_time
        t_inf = inf_time

        for n in range(num_doses):
            t_start = rel_t + n * interval

            # 各時間点での濃度を計算して足す
            for i, t in enumerate(t_eval):
                dt = t - t_start
                if dt <= 0:
                    continue  # まだ投与前

                # 点滴中と点滴終了後で式を分ける
                if dt <= t_inf:
                    # 点滴中
                    c = (r_inf * A / alpha * (1 - np.exp(-alpha * dt)) +
                         r_inf * B / beta * (1 - np.exp(-beta * dt)))
                else:
                    # 点滴終了後
                    c = (r_inf * A / alpha * (1 - np.exp(-alpha * t_inf)) * np.exp(-alpha * (dt - t_inf)) +
                         r_inf * B / beta * (1 - np.exp(-beta * t_inf)) * np.exp(-beta * (dt - t_inf)))

                total_conc[i] += c

    return t_eval, total_conc
def solve_vcm_yasuhara_mc(dose_df, weight, ccr, max_t, n_sim=10):
    t_eval = np.arange(0, float(max_t) + 0.5, 0.5)
    tv_cl = (0.797 * ccr) * 0.06 if ccr < 85 else 4.06 * ((weight / 55) ** 0.68)
    tv_vss = 60.7 * (weight / 55)
    tv_k12, tv_k21 = 0.525, 0.213
    om = {'CL': 0.385, 'Vss': 0.254, 'K21': 0.286}
    cl_sims = tv_cl * np.random.lognormal(-(om['CL'] ** 2) / 2, om['CL'], n_sim)
    vss_sims = tv_vss * np.random.lognormal(-(om['Vss'] ** 2) / 2, om['Vss'], n_sim)
    k21_sims = tv_k21 * np.random.lognormal(-(om['K21'] ** 2) / 2, om['K21'], n_sim)
    all_results = []
    for s in range(n_sim):
        v1_s = vss_sims[s] * (k21_sims[s] / (tv_k12 + k21_sims[s]))
        pk_s = {'k10': cl_sims[s] / v1_s, 'k12': tv_k12, 'k21': k21_sims[s], 'V1': v1_s}
        _, c = solve_pk_single(dose_df, pk_s, max_t)
        all_results.append(c)
    return t_eval, np.array(all_results), {'CL': tv_cl, 'Vss': tv_vss, 'k12': tv_k12, 'k21': tv_k21, 'om': om}
def solve_teic_nakayama_mc(dose_df, weight, ccr, max_t, n_sim=10):
    t_eval = np.arange(0, float(max_t) + 0.5, 0.5)
    tv_cl = 0.00498 * ccr + 0.00426 * weight
    tv_v1 = 10.4  # 中央容積は固定値
    tv_k12 = 0.380
    tv_k21 = 0.0485
    om = {'CL': 0.221, 'V1': 0.267, 'K21': 0.245}
    cl_sims = tv_cl * np.random.lognormal(-(om['CL'] ** 2) / 2, om['CL'], n_sim)
    v1_sims = tv_v1 * np.random.lognormal(-(om['V1'] ** 2) / 2, om['V1'], n_sim)
    k21_sims = tv_k21 * np.random.lognormal(-(om['K21'] ** 2) / 2, om['K21'], n_sim)
    all_results = []
    for s in range(n_sim):
        k10_s = cl_sims[s] / v1_sims[s]
        pk_s = {
            'k10': k10_s,
            'k12': tv_k12,
            'k21': k21_sims[s],
            'V1': v1_sims[s]
        }
        # solve_pk_single は内部で y0 = [0, 0] から開始するため、
        # 正しい初期値 0 からのシミュレーションになります。
        _, c_profile = solve_pk_single(dose_df, pk_s, max_t)
        all_results.append(c_profile)
    return t_eval, np.array(all_results), {'CL': tv_cl, 'V1': tv_v1, 'k12': tv_k12, 'k21': tv_k21, 'om': om}
def show_tdm_simulation():
    # Session State の維持
    if "dose_h" not in st.session_state:
        st.session_state.dose_h = pd.DataFrame(columns=["Day", "時刻", "1回量(mg)", "投与時間(h)", "投与間隔(h)", "回数", "rel_t"])
    if "obs_h" not in st.session_state:
        st.session_state.obs_h = pd.DataFrame(columns=["Day", "時刻", "実測値", "rel_t"])
    if "patient_info" not in st.session_state:
        st.session_state.patient_info = {"drug": "VCM (Yasuhara)", "age": 70, "weight": 60, "scr": 0.8}
    if "calc_ready" not in st.session_state:
        st.session_state.calc_ready = False

    def sync_time(df):
        # 入力中のNone対策: 必要な列がない、または中身が空ならそのまま返す
        if df is None or (isinstance(df, pd.DataFrame) and df.empty): return df
        if st.session_state.dose_h.empty: return df
        try:
            # 常に dose_h の 有効な1 行目を絶対的な基準（0時間）にする
            base_df = st.session_state.dose_h.dropna(subset=['Day', '時刻'])
            if base_df.empty: return df
            base_row = base_df.iloc[0]
            base_t = datetime.strptime(f"{int(base_row['Day'])} {base_row['時刻']}", "%d %H:%M")

            df['rel_t'] = df.apply(
                lambda r: (datetime.strptime(f"{int(r['Day'])} {r['時刻']}", "%d %H:%M") - base_t).total_seconds() / 3600
                if pd.notna(r['Day']) and pd.notna(r['時刻']) else np.nan,
                axis=1)
        except:
            pass
        return df

    # サイドバー：症例読み込み機能
    with st.sidebar:
        st.header("📂 症例選択")
        path_p, path_d, path_o = "assets/spread_data/tdm_patients.csv", "assets/spread_data/tdm_doses.csv", "assets/spread_data/tdm_observations.csv"
        if os.path.exists(path_p):
            df_p_all = pd.read_csv(path_p)
            selected_case = st.selectbox("症例を選択", df_p_all['CaseID'].unique())
            if st.button("症例データを読み込む"):
                p_match = df_p_all[df_p_all['CaseID'] == selected_case].iloc[0]
                st.session_state.patient_info = {
                    "drug": "VCM (Yasuhara)" if "VCM" in str(p_match['Drug']) else "TEIC (Nakayama)",
                    "age": int(p_match['Age']), "weight": float(p_match['Weight']), "scr": float(p_match['sCr'])}
                if os.path.exists(path_d):
                    d_all = pd.read_csv(path_d)
                    d_rows = d_all[d_all['CaseID'] == selected_case]
                    st.session_state.dose_h = pd.DataFrame(
                        {"Day": d_rows['Day'], "時刻": d_rows['Time'], "1回量(mg)": d_rows['Amount'],
                         "投与時間(h)": d_rows['InfTime'], "投与間隔(h)": d_rows['Interval'],
                         "回数": d_rows['Count']}).reset_index(drop=True)
                if os.path.exists(path_o):
                    o_all = pd.read_csv(path_o)
                    o_rows = o_all[o_all['CaseID'] == selected_case]
                    st.session_state.obs_h = pd.DataFrame(
                        {"Day": o_rows['Day'], "時刻": o_rows['Time'], "実測値": o_rows['Value']}).reset_index(drop=True)

                st.session_state.dose_h = sync_time(st.session_state.dose_h)
                st.session_state.obs_h = sync_time(st.session_state.obs_h)
                st.session_state.calc_ready = False
                st.rerun()

        st.divider()
        st.header("👤 患者パラメータ")
        p = st.session_state.patient_info
        drug_choice = st.radio("採用モデル", ["VCM (Yasuhara)", "TEIC (Nakayama)"], index=0 if "VCM" in p['drug'] else 1)
        age, weight, scr = st.number_input("年齢", 1, 120, p['age']), st.number_input("体重(kg)", 10, 150,
                                                                                    int(p['weight'])), st.number_input(
            "sCr(mg/dL)", 0.1, 10.0, p['scr'])
        ccr = (((140 - age) * weight) / (72 * max(scr, 0.6)))

        st.divider()
        show_pop, show_ci, show_bay = st.checkbox("母集団平均を表示", True), st.checkbox("95%信頼区間を表示", True), st.checkbox(
            "ベイズ推定を表示", True)
        x_max = st.slider("表示時間(h)", 24, 336, 120)

        # 【修正：計算ボタン】
        if st.button("🚀 計算実行", use_container_width=True):
            # 1. エディタから最新のDataFrameを取得し、時間に同期させる
            st.session_state.dose_h = sync_time(st.session_state.current_dose_df)
            st.session_state.obs_h = sync_time(st.session_state.current_obs_df)
            # 2. 計算フラグをON
            st.session_state.calc_ready = True
            st.rerun()

    # メイン画面：入力エディタ
    c1, c2 = st.columns(2)
    amount_list = list(range(0, 3050, 50))
    time_list = [f"{h:02d}:{m:02d}" for h in range(24) for m in [0, 30]]

    with c1:
        st.subheader("💉 投与スケジュール")
        # 戻り値を temporary な変数（current_dose_df）に受けることで、session_state.dose_h への即時書き込みを防ぎ、None問題を回避
        st.session_state.current_dose_df = st.data_editor(st.session_state.dose_h, key="ed_d", num_rows="dynamic",
                                                          column_config={
                                                              "Day": st.column_config.SelectboxColumn(
                                                                  options=list(range(1, 31))),
                                                              "時刻": st.column_config.SelectboxColumn(options=time_list),
                                                              "1回量(mg)": st.column_config.SelectboxColumn(
                                                                  options=amount_list),
                                                              "投与時間(h)": st.column_config.SelectboxColumn(
                                                                  options=[0.5, 1.0, 1.5, 2.0]),
                                                              "投与間隔(h)": st.column_config.SelectboxColumn(
                                                                  options=[8, 12, 24, 48]),
                                                              "回数": st.column_config.SelectboxColumn(
                                                                  options=list(range(1, 100)))
                                                          })

    with c2:
        st.subheader("🧪 TDM実測値")
        st.session_state.current_obs_df = st.data_editor(st.session_state.obs_h, key="ed_o", num_rows="dynamic",
                                                         column_config={
                                                             "Day": st.column_config.SelectboxColumn(
                                                                 options=list(range(1, 31))),
                                                             "時刻": st.column_config.SelectboxColumn(options=time_list)
                                                         })

    # グラフ表示
    if st.session_state.calc_ready and not st.session_state.dose_h.empty:
        if "VCM" in drug_choice:
            t_plot, sims, base_params = solve_vcm_yasuhara_mc(st.session_state.dose_h, weight, ccr, x_max)
            v_label, v_prior_key = "Vss", "Vss"
        else:
            t_plot, sims, base_params = solve_teic_nakayama_mc(st.session_state.dose_h, weight, ccr, x_max)
            v_label, v_prior_key = "V1", "V1"

        fig = go.Figure()
        if show_ci:
            up, lo = np.percentile(sims, 97.5, axis=0), np.percentile(sims, 2.5, axis=0)
            fig.add_trace(
                go.Scatter(x=np.concatenate([t_plot, t_plot[::-1]]), y=np.concatenate([up, lo[::-1]]), fill='toself',
                           fillcolor='rgba(0,100,255,0.1)', line=dict(color='rgba(0,0,0,0)'), name="95% CI"))
        if show_pop:
            fig.add_trace(go.Scatter(x=t_plot, y=np.mean(sims, axis=0), name="母集団平均", line=dict(color='Red', width=2)))

        v_obs = st.session_state.obs_h.dropna(subset=['実測値', 'rel_t'])
        pk_bayes_final = None
        if show_bay and not v_obs.empty:
            om = base_params['om']

            def bayesian_objective(params):
                cl_ind, v_ind, k21_ind = params
                v1_ind = v_ind * (k21_ind / (base_params['k12'] + k21_ind)) if "VCM" in drug_choice else v_ind
                pk_f = {'k10': cl_ind / v1_ind, 'k12': base_params['k12'], 'k21': k21_ind, 'V1': v1_ind}
                _, cp = solve_pk_single(st.session_state.dose_h, pk_f, x_max)
                c_pred = np.interp(v_obs['rel_t'], t_plot, cp)
                err = np.sum(((v_obs['実測値'] - c_pred) ** 2) / (c_pred * 0.2 + 0.1) ** 2)
                pen = ((np.log(cl_ind) - np.log(base_params['CL'])) ** 2 / om['CL'] ** 2) + \
                      ((np.log(v_ind) - np.log(base_params[v_prior_key])) ** 2 / om[v_prior_key] ** 2) + \
                      ((np.log(k21_ind) - np.log(base_params['k21'])) ** 2 / om['K21'] ** 2)
                return err + pen

            init = [base_params['CL'], base_params[v_prior_key], base_params['k21']]
            res_b = minimize(bayesian_objective, init, bounds=[(x * 0.1, x * 10) for x in init])
            b_cl, b_v, b_k21 = res_b.x
            b_v1 = b_v * (b_k21 / (base_params['k12'] + b_k21)) if "VCM" in drug_choice else b_v
            pk_bayes_final = {'CL': b_cl, v_label: b_v, 'k21': b_k21}
            _, c_bay = solve_pk_single(st.session_state.dose_h,
                                       {'k10': b_cl / b_v1, 'k12': base_params['k12'], 'k21': b_k21, 'V1': b_v1}, x_max)
            fig.add_trace(go.Scatter(x=t_plot, y=c_bay, name="ベイズ推定", line=dict(color='orange', width=4, dash='dot')))

        if not v_obs.empty:
            fig.add_trace(go.Scatter(x=v_obs['rel_t'], y=v_obs['実測値'], mode='markers', name="実測値",
                                     marker=dict(color='red', size=12, symbol='x')))

        fig.update_layout(xaxis_title="時間 (h)", yaxis_title="濃度 (μg/mL)", template="plotly_white", height=600)
        st.plotly_chart(fig, use_container_width=True)

        if pk_bayes_final:
            st.subheader("📊 推定パラメータ比較")
            st.table(pd.DataFrame({"Parameter": ["CL (L/h)", f"{v_label} (L)", "k21 (1/h)"],
                                   "Population": [base_params['CL'], base_params[v_prior_key], base_params['k21']],
                                   "Bayesian": [pk_bayes_final['CL'], pk_bayes_final[v_label],
                                                pk_bayes_final['k21']]}).style.format("{:.3f}", subset=["Population",
                                                                                                        "Bayesian"]))

# ==========================================
# ==========================================
# ==========================================
#　main
# ==========================================
# ==========================================
# ==========================================
def main():
    # --- 1. 状態の初期化 --- (省略なし)
    if 'user' not in st.session_state:
        st.session_state['user'] = {'name': 'ゲスト', 'id': 'guest'}
    if 'is_staff_confirmed' not in st.session_state: st.session_state['is_staff_confirmed'] = False
    if 'is_guest' not in st.session_state: st.session_state['is_guest'] = False
    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
    if 'view' not in st.session_state: st.session_state['view'] = 'login'
    if 'page' not in st.session_state: st.session_state['page'] = 'main'

    # 共通変数の初期化
    if 'correct_count' not in st.session_state: st.session_state.correct_count = 0
    if 'total_count' not in st.session_state: st.session_state.total_count = 0
    if "forum_view" not in st.session_state: st.session_state.forum_view = "list"
    if "temp_title" not in st.session_state: st.session_state.temp_title = ""

    # --- 2. ゲートキーパー（ログイン制限） ---
    if not st.session_state['is_staff_confirmed'] and not st.session_state['is_guest']:
        show_staff_confirmation_page()
        return

    if st.session_state['is_staff_confirmed'] and not st.session_state['logged_in']:
        if st.session_state['view'] == 'signup':
            show_signup_page()
        else:
            show_staff_confirmation_page()
        return

    # --- 📥 ログイン直後のデータロード（これだけは残す） ---
    if st.session_state['logged_in'] and not st.session_state.get('github_loaded', False):
        u_id = st.session_state['user'].get('id')
        if u_id and u_id != 'guest':
            with st.status("📥 最新データを取得中...", expanded=False) as status:
                sync_all_assets_recursive(u_id, mode="download")
                status.update(label="✅ 同期完了", state="complete")
            st.session_state['github_loaded'] = True
            st.rerun()

    # --- 3. 共通ナビゲーション ---
    current_page = st.session_state['page']
    u_role = str(st.session_state.get('user', {}).get('role', '一般'))
    is_mentor_staff = any(r in u_role for r in ["管理者", "教育係", "メンター"])

    # サイドバーの共通クリーンアップ処理
    if current_page != 'main':
        with st.sidebar:
            st.markdown("---")
            if st.button("🏠 メインメニューへ", use_container_width=True):
                st.session_state['page'] = 'main'
                # 各種フラグのリセット
                st.session_state['sub_page'] = 'menu'
                st.session_state.forum_view = "list"
                if "adding_material" in st.session_state: st.session_state.adding_material = False
                if "selected_material_idx" in st.session_state: st.session_state.selected_material_idx = None
                st.rerun()

    # --- 4. ページ分岐ロジック ---
    if current_page == 'main':
        if st.session_state['is_guest']:
            show_guest_menu()
        else:
            # show_main_menu内での「終了」ボタンは、
            # すでに都度同期しているので、単にログアウト処理だけでOKにできます。
            show_main_menu()

    elif current_page in ['study', 'meeting']:
        show_study_page()

    elif current_page == 'progress_view':
        show_progress_page()

    elif current_page == 'quiz':
        if st.session_state.get('quiz_started'):
            show_quiz_engine()
        else:
            show_quiz_page()

    elif current_page == 'review':
        if st.session_state['is_guest']:
            st.warning("ゲストモードでは履歴機能は利用できません。")
        else:
            show_review_page()

    elif current_page == 'board':
        if st.session_state['is_guest']:
            st.error("この機能は職員専用です。")
        else:
            show_message_hub()

    elif current_page == 'diary':
        if st.session_state['is_guest']:
            st.error("ゲストモードでは日誌機能は利用できません。")
        else:
            show_diary_page()

    elif current_page == 'search':
        show_search_page()

    elif current_page in ['mentor', 'mentor_dashboard']:
        if is_mentor_staff:
            show_mentor_page()
        else:
            st.error("アクセス権限がありません。")

    elif current_page == 'simulation':
        show_simulation_page()

    else:
        st.warning(f"不明なページです: {current_page}")
        if st.button("ホームへ戻る"):
            st.session_state['page'] = 'main'
            st.rerun()

if __name__ == "__main__":
    main()


