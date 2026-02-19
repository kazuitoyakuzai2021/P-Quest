import streamlit as st
import pandas as pd
import os
import csv
import random
import re
import datetime
import base64
import shutil
import time
import io
import plotly.express as px
from collections import Counter

# --- 1. 設定・パス関連 ---
LOGIN_FILE = "login_data.csv"
USERS_BASE_DIR = "assets/users"
SYSTEM_REQUEST_FILE = "assets/spread_data/system_requests.csv"

# フォルダが存在しない場合は作成
os.makedirs(USERS_BASE_DIR, exist_ok=True)
if not os.path.exists(LOGIN_FILE):
    with open(LOGIN_FILE, mode="w", encoding="utf_8_sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "password", "role", "level", "exp", "points"])

st.set_page_config(page_title="P-Quest", page_icon="💊", layout="wide")

# --- 2. スタイル設定 (Tkinterのデザインを再現) ---
st.markdown("""
    <style>
    /* 全体背景: 明るいグレー */
    .main { background-color: #F8FAFC; color: #1E293B; }

    /* ログインカードのデザイン */
    .login-container {
        background-color: white;
        padding: 50px;
        border-radius: 20px;
        border: 1px solid #E2E8F0;
        box-shadow: 0 10px 25px rgba(0,0,0,0.05);
        text-align: center;
        max-width: 500px;
        margin: auto;
    }

    /* タイトルとフォント設定 */
    .title-text { font-family: 'Helvetica', sans-serif; font-size: 52px; font-weight: bold; color: #0F172A; margin-bottom: 0; }
    .ver-text { font-family: 'Consolas', sans-serif; font-size: 16px; color: #64748B; margin-bottom: 20px; }
    .badge { background-color: #F1F5F9; color: #64748B; padding: 5px 15px; border-radius: 5px; font-weight: bold; font-family: 'Consolas'; }

    /* 入力ラベル */
    .input-label { font-family: 'Meiryo', sans-serif; font-weight: bold; color: #475569; text-align: left; margin-top: 15px; }

    /* ボタンのデザイン */
    div.stButton > button {
        background-color: #3B82F6 !important;
        color: white !important;
        border-radius: 8px !important;
        font-size: 1.2rem !important;
        font-weight: bold !important;
        height: 3.5rem !important;
        border: none !important;
        transition: 0.3s;
    }
    div.stButton > button:hover { background-color: #2563EB !important; transform: translateY(-2px); }

    /* 新規登録リンク */
    .signup-link { color: #3B82F6; text-decoration: underline; cursor: pointer; font-size: 14px; }

    /* 文字を大きく読みやすく */
    input { font-size: 1.5rem !important; text-align: center !important; }
    </style>
    """, unsafe_allow_html=True)
# --- 3. ロジック関数 ---
import streamlit as st
def show_staff_confirmation_page():
    st.title("🏥 浜松医療センター 薬剤科")
    st.subheader("利用前の確認・同意")

    st.info("本システムは薬剤科職員の学習支援を目的としています。")

    # 薬剤科紹介リンク
    url = "https://www.hmedc.or.jp/department/pharmacy/"
    st.markdown(f"👉 [浜松医療センター 薬剤科の紹介はこちら]({url})")

    st.write("---")

    # --- 同意事項のセクション ---
    st.markdown("#### 📝 学会発表等へのデータ利用に関する同意")
    st.caption("""
    職員として本システムを利用する場合、入力された研修結果や学習履歴は、
    個人が特定されない形で統計的に処理した上で、**学会発表や論文等の研究データとして
    利用させていただく可能性**があります。
    """)

    # チェックボックス
    agreed = st.checkbox("上記の内容を理解し、データの研究利用に同意します。")

    st.write("---")
    st.warning("あなたは薬剤科の職員ですか？")

    col1, col2 = st.columns(2)

    with col1:
        # agreed が False の間は disabled=True になり、ボタンが押せません
        if st.button("✅ はい（職員ログインへ）", use_container_width=True, disabled=not agreed):
            st.session_state['is_staff_confirmed'] = True
            st.session_state['is_guest'] = False
            st.rerun()

        # チェックしていない時に補足説明を出す（親切設計）
        if not agreed:
            st.caption("⚠️ 職員の方は同意にチェックを入れると進めます。")

    with col2:
        # ゲストは同意不要で進める設定
        if st.button("👤 いいえ（ゲストモード）", use_container_width=True):
            st.session_state['is_staff_confirmed'] = False
            st.session_state['is_guest'] = True
            st.session_state['logged_in'] = True
            st.session_state['page'] = 'main'
            st.rerun()
# --- ゲスト専用メニュー（任意） ---
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
def check_login(user_id, password):
    """CSVからログイン情報を確認"""
    if user_id == "000000" and password == "9999":  # 管理者
        return {"id": "admin", "name": "管理者", "role": "管理者", "level": 99, "exp": 0, "points": 0}

    with open(LOGIN_FILE, mode="r", encoding="utf_8_sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['id'] == user_id and row['password'] == password:
                return row
    return None
def register_user(user_id, user_name, user_pw):
    """新規ユーザー登録"""
    df = pd.read_csv(LOGIN_FILE)
    if user_id in df['id'].astype(str).values:
        return False, "この番号は既に登録されています。"

    new_data = [user_id, user_name, user_pw, "薬剤師"]
    with open(LOGIN_FILE, mode="a", encoding="utf_8_sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(new_data)

    os.makedirs(os.path.join(USERS_BASE_DIR, user_id), exist_ok=True)
    return True, "登録が完了しました！"
# --- 4. 画面表示関数 ---
def show_login_page():
    """ログイン画面（ユーザー環境の自動初期化機能付き）"""
    # 画面中央に寄せるためのレイアウト
    _, col, _ = st.columns([1, 1.2, 1])

    with col:
        # ヘッダーデザイン
        st.markdown("""
            <div class='login-container' style='text-align: center; margin-bottom: 20px;'>
                <div class='title-text' style='font-size: 42px; font-weight: bold; color: #1E293B;'>P-Quest</div>
                <div class='ver-text' style='color: #64748B;'>ver 1.0</div>
                <span class='badge' style='background-color: #3B82F6; color: white; padding: 4px 12px; border-radius: 12px; font-size: 12px;'>SYSTEM LOGIN</span>
            </div>
        """, unsafe_allow_html=True)

        # ログインフォーム
        with st.form("login_form", clear_on_submit=False):
            st.markdown("<p class='input-label' style='margin-bottom: -15px; font-weight: bold;'>職員番号</p>",
                        unsafe_allow_html=True)
            u_id = st.text_input("ID", label_visibility="collapsed", placeholder="半角6桁")

            st.markdown(
                "<p class='input-label' style='margin-bottom: -15px; font-weight: bold; margin-top: 10px;'>パスワード</p>",
                unsafe_allow_html=True)
            u_pw = st.text_input("PW", label_visibility="collapsed", type="password", placeholder="数字4桁")

            # 入力候補・自動保存の抑制用JS（ブラウザの干渉を防ぐ）
            st.components.v1.html("""
                <script>
                    const inputs = window.parent.document.querySelectorAll('input');
                    inputs.forEach(input => {
                        input.setAttribute('autocomplete', 'new-password');
                        input.setAttribute('name', Math.random().toString(36));
                    });
                </script>
            """, height=0)

            # ログイン実行ボタン
            submit = st.form_submit_button("ログイン", use_container_width=True)

            if submit:
                # 1. 認証チェック
                user = check_login(u_id, u_pw)

                if user:
                    # 2. ユーザー環境（フォルダ・各CSVファイル）の自動生成
                    # 初回ログイン時や、ファイルが足りない場合にここで作成される
                    initialize_user_environment(user['id'])

                    # 3. 数値データの型変換（CSVから読むと文字列になるため）
                    if user['id'] != "admin":
                        try:
                            user['exp'] = int(user.get('exp', 0))
                            user['level'] = int(user.get('level', 1))
                        except (ValueError, TypeError):
                            user['exp'] = 0
                            user['level'] = 1

                    # 4. セッション状態の確定
                    st.session_state['logged_in'] = True
                    st.session_state['user'] = user
                    st.session_state['page'] = 'main'  # 明示的にメインへ

                    st.success(f"ログイン成功：{user['name']} さん")
                    time.sleep(0.5)  # 成功メッセージを見せるための僅かな待機
                    st.rerun()
                else:
                    st.error("職員番号またはパスワードが正しくありません。")

        # フォーム外のリンクボタン
        st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)
        if st.button("▶ 初めての方・新規ユーザー登録はこちら", type="secondary", use_container_width=True):
            st.session_state['view'] = 'signup'
            st.rerun()

        # フッター
        st.markdown("""
            <p style='color:#94A3B8; font-size:12px; margin-top:30px; text-align:center;'>
                Powered by 浜松医療センター 薬剤科
            </p>
        """, unsafe_allow_html=True)
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
                        st.session_state['view'] = 'login'
                        st.rerun()
                    else:
                        st.error(msg)
                else:
                    st.warning("入力を確認してください。")

        if st.button("ログイン画面へ戻る"):
            st.session_state['view'] = 'login'
            st.rerun()
def initialize_user_environment(user_id):
    """新規ユーザー用のディレクトリと指定された5つの空CSVファイルを一括作成する"""

    # ユーザー専用ディレクトリのパス
    user_base_dir = os.path.join("assets", "users", str(user_id))

    # 1. フォルダ作成
    if not os.path.exists(user_base_dir):
        os.makedirs(user_base_dir, exist_ok=True)
        st.toast(f"ユーザーフォルダを作成しました: {user_id}")

    # 2. 作成すべき空ファイルの定義（ご指定の5ファイル）
    files_to_create = {
        "diary.csv": ["日付", "内容", "コメント"],
        "my_progress.csv": ["カテゴリ", "項目", "習得度"],
        "my_forum.csv": ["ID", "日時", "ユーザー", "タイトル", "内容", "回答", "ステータス", "公開フラグ"],
        # クイズ等の全履歴（日報的なサマリー用）
        "my_all_results.csv": ["日時", "タイプ", "タイトル", "スコア", "正解数", "総数"],
        # 特定のテスト成績（内規テストなど、重要な試験の記録用）
        "my_test_results.csv": ["実施日", "テスト名", "得点", "満点", "判定", "経過時間"]
    }

    # 3. 各ファイルの存在確認と初期化
    for filename, columns in files_to_create.items():
        file_path = os.path.join(user_base_dir, filename)
        if not os.path.exists(file_path):
            pd.DataFrame(columns=columns).to_csv(file_path, index=False, encoding="utf_8_sig")
def show_main_menu():
    """メイン画面（教育係対応スリムヘッダー版）"""
    user = st.session_state['user']
    role = user.get('role', '一般')

    # --- 1. コンパクト・ヘッダー ---
    st.markdown("<div class='header-box'>", unsafe_allow_html=True)

    # カラム比率を調整して右側のボタン領域を確保
    h_col1, h_col2, h_col3, h_col4 = st.columns([1.5, 1.2, 0.8, 2.5])

    with h_col1:
        badge_icon = "🎓" if role == "教育係" else "🔰"
        st.markdown(
            f"<div class='user-info'>{badge_icon} {user['name']} <span class='level-label'>Lv.{user.get('level', 1)}</span></div>",
            unsafe_allow_html=True)

    with h_col2:
        exp = int(user.get('exp', 0)) % 1000
        st.progress(exp / 1000)
        st.caption(f"EXP: {exp}/1000")

    with h_col3:
        st.markdown(
            f"<div style='margin-top:5px;'><span class='point-label'>🪙 {int(user.get('points', 0))}</span></div>",
            unsafe_allow_html=True)

    with h_col4:
        # ボタンを並べるためのコンテナを開始
        st.markdown('<div class="compact-btn-container">', unsafe_allow_html=True)

        # 内部でさらに細かいカラムを作ってボタンを配置（これで横並びを担保）
        btn_count = 4 if role == "教育係" else 3
        inner_cols = st.columns(btn_count)

        col_idx = 0

        # 1. 進捗ボタン（教育係のみ）
        if role == "教育係":
            with inner_cols[col_idx]:
                # 教育係ボタンだけ紫にするためのクラスを適用
                st.markdown('<div class="mentor-btn">', unsafe_allow_html=True)
                if st.button("👥 進捗", key="h_mentor", use_container_width=True):
                    st.session_state['page'] = 'mentor_dashboard'
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
            col_idx += 1

        # 2. 検索ボタン
        with inner_cols[col_idx]:
            # width='stretch' に変更し、ページ遷移のロジックを追加
            if st.button("🔍 検索", key="search", type="secondary", width='stretch'):
                st.session_state['page'] = 'search'  # 遷移先を指定
                st.rerun()  # 画面を再描画して遷移を確定させる
        col_idx += 1

        # 4. 終了ボタン
        with inner_cols[col_idx]:
            if st.button("🚪 終了", key="h_logout", type="secondary", use_container_width=True):
                st.session_state.clear()
                st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)

    # --- 2. メインメニュー（カードはそのまま） ---
    st.markdown("<h3 style='text-align: center; margin-bottom: 25px; color: #475569;'>MENU</h3>",
                unsafe_allow_html=True)

    m_col1, m_col2, m_col3 = st.columns(3)
    menu_items = [
        {"title": "📚 参考資料", "id": "study", "col": m_col1},
        {"title": "📝 問題演習", "id": "quiz", "col": m_col2},
        {"title": "❓ 掲示板", "id": "board", "col": m_col3},
        {"title": "📖 勉強会資料", "id": "meeting", "col": m_col1},
       {"title": "💻 シミュレーション", "id": "simulation", "col": m_col2},
        {"title": "📔 業務日誌", "id": "diary", "col": m_col3},
    ]

    for item in menu_items:
        with item['col']:
            if st.button(item['title'], key=item['id'], use_container_width=True):
                st.session_state['page'] = item['id']
                st.rerun()
def show_study_page():
    """参考資料ライブラリ画面（管理者・本人限定編集版）"""
    st.markdown("## 📚 参考資料ライブラリ")

    # --- パス設定 ---
    BASE_DIR = "assets"
    STORAGE_DIR = os.path.join(BASE_DIR, "drive_data", "参考資料")
    CSV_FILE = os.path.join(BASE_DIR, "spread_data", "materials.csv")
    os.makedirs(STORAGE_DIR, exist_ok=True)

    # データ読み込み
    if os.path.exists(CSV_FILE):
        df = pd.read_csv(CSV_FILE, encoding="utf_8_sig").fillna("")
        if "URL" not in df.columns: df["URL"] = ""
    else:
        df = pd.DataFrame(columns=["大カテゴリー", "小カテゴリー", "タイトル", "内容", "ファイルパス", "URL", "作問者"])

    if 'adding_new' not in st.session_state: st.session_state.adding_new = False

    # 現在のログインユーザー情報
    current_user_name = st.session_state['user']['name']
    is_admin = st.session_state['user'].get('role') == "教育係"

    # --- サイドバー：フィルター ---
    with st.sidebar:
        st.markdown("### 🔍 フィルター")
        sub_categories = {"内規": ["調剤室業務", "注射室業務"], "薬剤": ["精神神経・筋疾患", "骨・関節疾患", "免疫疾患", "心臓・血管系疾患", "腎・泌尿器疾患",
                  "産科婦人科疾患", "呼吸器疾患", "消化器疾患", "血液及び造血器疾患",
                  "感覚器疾患", "内分泌・代謝疾患", "皮膚疾患", "感染症", "悪性腫瘍", "その他"],
                          "チーム": ["感染", "栄養", "緩和"], "その他": ["その他"]}
        p_filter = st.selectbox("大カテゴリー", ["すべて"] + list(sub_categories.keys()))
        c_filter = st.selectbox("小カテゴリー", ["すべて"] + (sub_categories[p_filter] if p_filter != "すべて" else []))

        st.divider()
        # 新規追加ボタンは誰でも押せるが、保存時に本人が「作問者」として記録される
        if st.button("➕ 新規資料を追加", use_container_width=True):
            st.session_state.adding_new = True
            st.rerun()

    # フィルタリング
    f_df = df.copy()
    if p_filter != "すべて": f_df = f_df[f_df["大カテゴリー"] == p_filter]
    if c_filter != "すべて": f_df = f_df[f_df["小カテゴリー"] == c_filter]

    col_list, col_detail = st.columns([1, 2])

    with col_list:
        st.write(f"資料一覧 ({len(f_df)}件)")
        if st.session_state.adding_new:
            st.warning("✨ 新規資料を作成中...")
            selected_title = None
        else:
            selected_title = st.radio("資料を選択", f_df["タイトル"].tolist(),
                                      label_visibility="collapsed") if not f_df.empty else None

    with col_detail:
        # --- 1. 新規登録画面 ---
        if st.session_state.adding_new:
            st.markdown("### 🆕 新規資料の登録")
            with st.container(border=True):
                new_title = st.text_input("タイトル", value="", placeholder="資料のタイトル")
                new_content = st.text_area("内容・解説", value="", height=150)
                new_url = st.text_input("🌐 参考URL (あれば)", value="")
                uploaded_file = st.file_uploader("PDFファイルを選択", type=["pdf"])

                st.divider()
                c1, c2 = st.columns(2)
                if c1.button("💾 資料を保存して登録", type="primary", use_container_width=True):
                    if not new_title:
                        st.error("タイトルは必須です。")
                    else:
                        rel_path = ""
                        if uploaded_file:
                            save_path = os.path.join(STORAGE_DIR, uploaded_file.name)
                            with open(save_path, "wb") as f:
                                f.write(uploaded_file.getbuffer())
                            rel_path = f"参考資料/{uploaded_file.name}"

                        new_data = {
                            "大カテゴリー": "その他", "小カテゴリー": "その他", "タイトル": new_title,
                            "内容": new_content, "ファイルパス": rel_path, "URL": new_url,
                            "作問者": current_user_name  # 自動的に本人を記録
                        }
                        df = pd.concat([df, pd.DataFrame([new_data])], ignore_index=True)
                        df.to_csv(CSV_FILE, index=False, encoding="utf_8_sig")
                        st.session_state.adding_new = False
                        st.success("登録完了しました！")
                        st.rerun()

                if c2.button("✖ キャンセル", use_container_width=True):
                    st.session_state.adding_new = False
                    st.rerun()

        # --- 2. 既存資料の表示/編集 ---
        elif selected_title:
            idx = df[df["タイトル"] == selected_title].index[0]
            data = df.loc[idx]

            # 【重要】修正権限の判定
            # 管理者(教育係) であるか、もしくは 作問者(本人) であるか
            can_modify = is_admin or (str(data["作問者"]) == current_user_name)

            # 権限がある場合のみ編集モードトグルを表示
            edit_mode = False
            if can_modify:
                edit_mode = st.toggle("📝 編集モードを有効にする", value=False)
            else:
                st.info("💡 あなたはこの資料の閲覧権限を持っています。")

            with st.container(border=True):
                if edit_mode:
                    # --- 修正画面 ---
                    e_title = st.text_input("タイトル", value=data["タイトル"])
                    e_content = st.text_area("内容", value=data["内容"], height=200)
                    e_url = st.text_input("URL", value=data["URL"])
                    e_file = st.file_uploader("PDFファイルを差し替え", type=["pdf"])

                    st.divider()
                    b_col1, b_col2 = st.columns(2)
                    if b_col1.button("💾 変更を確定", type="primary", use_container_width=True):
                        if e_file:
                            save_path = os.path.join(STORAGE_DIR, e_file.name)
                            with open(save_path, "wb") as f:
                                f.write(e_file.getbuffer())
                            df.at[idx, "ファイルパス"] = f"参考資料/{e_file.name}"

                        df.at[idx, "タイトル"] = e_title
                        df.at[idx, "内容"] = e_content
                        df.at[idx, "URL"] = e_url
                        df.to_csv(CSV_FILE, index=False, encoding="utf_8_sig")
                        st.success("更新しました")
                        st.rerun()

                    if b_col2.button("🗑 資料を削除", use_container_width=True):
                        if st.warning("本当に削除しますか？"):
                            df = df.drop(idx)
                            df.to_csv(CSV_FILE, index=False, encoding="utf_8_sig")
                            st.rerun()
                else:
                    # --- 閲覧画面 ---
                    st.markdown(f"### {data['タイトル']}")
                    st.markdown(f"**【大カテゴリー】** {data['大カテゴリー']} / **【小カテゴリー】** {data['小カテゴリー']}")
                    st.write(data["内容"])

                    st.divider()
                    # URLがある場合
                    if data["URL"]:
                        st.link_button("🌐 参考サイトへ移動", data["URL"], use_container_width=True)

                    # PDFがある場合
                    if data["ファイルパス"]:
                        pdf_file = os.path.join(BASE_DIR, "drive_data", data["ファイルパス"])
                        if os.path.exists(pdf_file):
                            with open(pdf_file, "rb") as f:
                                st.download_button("📄 PDF資料を表示/保存", f, file_name=os.path.basename(pdf_file),
                                                   use_container_width=True)
                        else:
                            st.error("ファイルが見つかりません。パスを確認してください。")

                st.caption(f"登録者: {data['作問者']}")
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
    """テストの最終結果（合否を含む）をユーザーフォルダに保存"""
    u_id = st.session_state['user'].get('id', 'guest')
    path = f"assets/users/{u_id}/my_test_results.csv"
    os.makedirs(os.path.dirname(path), exist_ok=True)

    is_passed = "合格" if rate >= pass_line else "不合格"
    file_exists = os.path.exists(path)

    with open(path, "a", encoding="utf_8_sig", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["日時", "カテゴリー", "正解数", "全問題数", "正答率", "合格ライン", "判定"])

        writer.writerow([
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            category,
            correct,
            total,
            f"{rate}%",
            f"{pass_line}%",
            is_passed
        ])
    print(f"✅ テスト結果を保存しました: {is_passed} ({rate}%)")
def show_progress_page():
    """📊 習得度チェックリスト画面（1=0%, 5=100% 計算版）"""
    name = st.session_state.get('current_task_view', '不明')
    st.markdown(f"### 📊 {name} の習得度")

    # 1. 共通マスター読み込み
    TASK_CSV = "assets/spread_data/task_list.csv"
    if not os.path.exists(TASK_CSV):
        st.error("評価項目リストが見つかりません。")
        return

    tasks_df = pd.read_csv(TASK_CSV, encoding="utf_8_sig")
    relevant_tasks = tasks_df[tasks_df["カテゴリ"] == name]["項目"].tolist()

    if not relevant_tasks:
        st.warning("このカテゴリーには評価項目が登録されていません。")
        if st.button("戻る"):
            st.session_state['page'] = 'quiz'
            st.rerun()
        return

    # 2. ユーザー別フォルダ設定
    u_id = st.session_state['user'].get('id', 'guest')
    user_dir = f"assets/users/{u_id}"
    os.makedirs(user_dir, exist_ok=True)
    PROG_PATH = os.path.join(user_dir, "my_progress.csv")

    # 3. 既存データの読み込み
    current_progress = {}
    if os.path.exists(PROG_PATH):
        with open(PROG_PATH, "r", encoding="utf_8_sig") as f:
            for r in csv.reader(f):
                if len(r) >= 3 and r[0] == name:
                    current_progress[r[1]] = int(r[2])

    # 4. スライダー表示
    scores = []
    st.markdown("---")
    for task in relevant_tasks:
        col1, col2 = st.columns([3, 2])
        col1.write(f"**{task}**")
        val = col2.select_slider(
            "自信度",
            options=[1, 2, 3, 4, 5],
            value=current_progress.get(task, 1),
            key=f"task_val_{task}",
            label_visibility="collapsed"
        )
        scores.append(val)

    # 5. 【計算修正】1=0%, 5=100% ロジック
    total_items = len(scores)
    current_sum = sum(scores)
    max_gain = total_items * 4  # (5-1) * 項目数

    if max_gain > 0:
        # 分子から項目数分を引くことで、全項目1のときに0%になる
        perc = int(((current_sum - total_items) / max_gain) * 100)
    else:
        perc = 0

    # 0未満にならないようガード
    perc = max(0, perc)

    st.divider()
    st.write(f"現在の習得状況: **{perc}%**")
    st.progress(perc / 100)

    # 6. 保存
    if st.button("💾 進捗を保存して報酬を獲得", type="primary", use_container_width=True):
        save_data = []
        if os.path.exists(PROG_PATH):
            with open(PROG_PATH, "r", encoding="utf_8_sig") as f:
                # 他のカテゴリーのデータを退避
                save_data = [r for r in csv.reader(f) if len(r) >= 3 and r[0] != name]

        # 新しいデータを追加
        now_str = datetime.datetime.now().strftime("%Y-%m-%d")
        for task, score in zip(relevant_tasks, scores):
            save_data.append([name, task, score, now_str])

        with open(PROG_PATH, "w", encoding="utf_8_sig", newline="") as f:
            csv.writer(f).writerows(save_data)

        st.success(f"保存完了！習得率 {perc}% に到達しました。")

        # 経験値などのゲーム要素
        if 'gain_exp' in st.session_state:
            # 習得率に応じたボーナスなどを設定可能
            st.session_state.gain_exp(perc // 2)

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
def setup_quiz_data():
    """クイズデータをCSVから読み込み、セッションにセットする"""
    print("\n" + "=" * 40)
    print("🚀 [ENTER] setup_quiz_data を実行します")
    print("=" * 40)

    # 1. パスの解決
    current_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(current_dir, "assets", "spread_data", "questions.csv")

    # 2. 検索キーワードの取得とクリーニング
    raw_target = st.session_state.get('test_target', "")
    import re
    clean_target = re.sub(r'[^\w・]', '', raw_target).strip()

    print(f"DEBUG: 検索キーワード -> '{clean_target}'")
    print(f"DEBUG: 読み込みパス -> {path}")

    if not os.path.exists(path):
        print(f"❌ エラー: ファイルが存在しません: {path}")
        st.error(f"CSVファイルが見つかりません: {path}")
        return

    all_q = []
    try:
        # UTF-8 BOM付き(utf_8_sig)で読み込み
        with open(path, mode="r", encoding="utf_8_sig") as f:
            r = csv.reader(f)
            header = next(r, None)  # ヘッダーをスキップ

            for i, row in enumerate(r):
                if len(row) < 2:
                    continue

                # CSV側のデータ（1列目:大項目, 2列目:小項目）
                csv_major = row[0].strip()
                csv_minor = row[1].strip()

                # 部分一致(in)で判定（「調剤」が含まれていればOK）
                if clean_target in csv_major or clean_target in csv_minor:
                    all_q.append(row)

                # 最初の数行だけ中身をターミナルに出して確認
                if i < 5:
                    print(f"DEBUG: CSV {i + 1}行目確認 -> 大:[{csv_major}] 小:[{csv_minor}]")

    except Exception as e:
        print(f"❌ 例外発生: {e}")
        st.error(f"読み込みエラーが発生しました: {e}")
        return

    # 3. 結果の判定とセッションへの保存
    if not all_q:
        print(f"⚠️ 一致する問題がゼロでした（検索語: {clean_target}）")
        st.error(f"「{clean_target}」に一致する問題がありませんでした。CSVの文字を確認してください。")
        st.session_state.quiz_started = False
        # 0件のときは rerun せずに止める
    else:
        print(f"✅ ヒットしました！ 合計 {len(all_q)} 件中 10件を選択します。")
        # セッション状態を更新
        st.session_state.questions = random.sample(all_q, min(len(all_q), 10))
        st.session_state.quiz_started = True
        st.session_state.quiz_finished = False
        st.session_state.current_index = 0
        st.session_state.correct_count = 0

        print(f"✅ セットアップ完了。アプリをリロードします。")
        st.rerun()
def display_answer_ui(q):
    # すでに回答済みで、フィードバック（解説）待機中の場合
    if st.session_state.get('show_feedback'):
        display_feedback(q)
        return

    # --- 以下、通常の回答UI（○×、4択、記述） ---
    q_type = q[2]
    correct_data = q[5]
    explanation = q[6] if len(q) > 6 else "なし"

    if q_type == "〇×問題":
        cols = st.columns(2)
        if cols[0].button("⭕ 〇", use_container_width=True):
            process_answer("〇", correct_data, q)
        if cols[1].button("❌ ×", use_container_width=True):
            process_answer("×", correct_data, q)

    elif "4択問題" in q_type:
        options = correct_data.split("|")
        # 1:正解, 2:選択肢1, 3:選択肢2, 4:選択肢3, 5:選択肢4 という構造を想定
        choices = options[1:5]
        for i, choice in enumerate(choices):
            if st.button(f"{i + 1}. {choice}", use_container_width=True):
                process_answer(str(i + 1), correct_data, q)

    else:  # 記述問題
        user_ans = st.text_input("回答を入力してください", key=f"q_{st.session_state.current_index}")
        if st.button("回答を送信"):
            st.session_state.temp_ans = user_ans
            st.session_state.show_self_check = True

        if st.session_state.get('show_self_check'):
            with st.container(border=True):
                st.write(f"あなたの回答: **{st.session_state.temp_ans}**")
                st.write(f"模範解答: **{correct_data}**")
                st.info(f"【解説】\n{explanation}")
                c1, c2 = st.columns(2)
                if c1.button("✅ 正解にする"): process_answer(True, correct_data, q, is_written=True)
                if c2.button("❌ 不正解にする"): process_answer(False, correct_data, q, is_written=True)
def process_answer(user_ans, correct_data, q, is_written=False):
    """正誤判定とステート更新、および履歴保存の実行"""
    # 1. 正誤判定のロジック
    if is_written:
        is_ok = user_ans  # 記述式はユーザーの自己申告(True/False)
    else:
        # 4択などは correct_data の最初の要素が正解
        ans = correct_data.split("|")[0] if "|" in correct_data else correct_data
        is_ok = (str(user_ans).strip() == str(ans).strip())

    # 2. セッション状態の更新
    st.session_state.last_result = is_ok
    st.session_state.show_feedback = True
    if is_ok:
        st.session_state.correct_count += 1

    # ★ 3. 履歴の保存を実行！
    # correct_dataから表示用の正解テキストを抽出
    display_correct_ans = correct_data.split("|")[0] if "|" in correct_data else correct_data
    save_quiz_history(q, user_ans, display_correct_ans, is_ok)

    st.rerun()
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
# --- フィードバック画面などの補助関数 ---
def show_result_screen():
    total = len(st.session_state.questions)
    correct = st.session_state.correct_count
    rate = int((correct / total) * 100) if total > 0 else 0
    target = st.session_state.get('test_target', '不明')
    mode = st.session_state.get('quiz_mode', 'normal')

    st.markdown(f"## 🏁 {mode.upper()} 終了")

    # --- 保存処理 (テストモードの場合のみ実行) ---
    # st.session_state に保存済みフラグを持たせて重複保存を防止
    if mode == "test" and not st.session_state.get('test_recorded', False):
        pass_line = st.session_state.get('pass_line', 80)
        save_test_result(target, total, correct, rate, pass_line)
        st.session_state.test_recorded = True  # 保存済みフラグ

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
    st.session_state.quiz_started = False
    st.session_state.page = "quiz"
    st.rerun()
def save_quiz_history(q, user_ans, correct_ans, is_ok):
    """ユーザーフォルダにクイズ結果をCSV保存"""
    try:
        u_id = st.session_state['user'].get('id', 'guest')
        path = f"assets/users/{u_id}/my_all_results.csv"
        os.makedirs(os.path.dirname(path), exist_ok=True)

        file_exists = os.path.exists(path)
        with open(path, "a", encoding="utf_8_sig", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                # ユーザーが後で見やすいように列順を整理
                writer.writerow(["日時", "カテゴリー", "判定", "問題文", "自分の回答", "正解"])

            writer.writerow([
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                q[1],  # カテゴリー
                "正解" if is_ok else "不正解",
                q[4],  # 問題文
                user_ans,
                correct_ans
            ])
        print(f"✅ CSV保存完了: {path}")  # ターミナルで確認用
    except Exception as e:
        print(f"❌ CSV保存失敗: {e}")
def show_review_page():
    """📊 学習履歴・復習・統計画面（総問題数表示・タブ整理版）"""
    st.markdown("# 📊 学習履歴と復習")

    u_id = st.session_state.get('user', {}).get('id', 'default_user')
    user_dir = f"assets/users/{u_id}"

    if not os.path.exists(user_dir):
        os.makedirs(user_dir, exist_ok=True)

    QUESTIONS_CSV = "assets/spread_data/questions.csv"
    RESULTS_CSV = os.path.join(user_dir, "my_all_results.csv")
    TEST_RESULTS_CSV = os.path.join(user_dir, "my_test_results.csv")

    # --- 1. 個人成績データの読み込みと集計 ---
    stats = {}
    if os.path.exists(RESULTS_CSV):
        try:
            with open(RESULTS_CSV, "r", encoding="utf_8_sig") as f:
                r = csv.reader(f)
                next(r, None)  # ヘッダー飛ばし
                for row in r:
                    if len(row) >= 4:
                        res = row[2].strip()  # 判定
                        q_text = row[3].strip()  # 問題文
                        if q_text not in stats:
                            stats[q_text] = []
                        stats[q_text].append(res)
        except Exception as e:
            st.error(f"成績データの読み込みに失敗しました: {e}")

    # --- 2. フィルター用サイドバー ---
    with st.sidebar:
        st.markdown("### 🔍 フィルター設定")
        sub_categories = {
            "内規": ["すべて", "調剤室業務", "注射室業務"],
            "薬剤と疾患": ["すべて", "精神神経・筋疾患", "骨・関節疾患", "免疫疾患", "心臓・血管系疾患",
                      "腎・泌尿器疾患", "産科婦人科疾患", "呼吸器疾患", "消化器疾患",
                      "血液及び造血器疾患", "感覚器疾患", "内分泌・代謝疾患", "皮膚疾患",
                      "感染症", "悪性腫瘍", "その他"]
        }
        maj_cat = st.selectbox("大カテゴリー", ["すべて"] + list(sub_categories.keys()))
        min_options = sub_categories.get(maj_cat, ["すべて"]) if maj_cat != "すべて" else ["すべて"]
        min_cat = st.selectbox("小カテゴリー", min_options)
        level_filter = st.selectbox("難易度", ["すべて", "★", "★★", "★★★", "★★★★"])
        result_filter = st.selectbox("最新成績で絞り込み", ["すべて", "正解", "不正解", "未回答"])

    # --- 3. メインコンテンツ（2タブ構成に変更） ---
    tab1, tab2 = st.tabs(["📖 問題管理・統計", "🏆 テスト履歴"])

    with tab1:
        if not os.path.exists(QUESTIONS_CSV):
            st.error("問題データが見つかりません。")
        else:
            df_q = pd.read_csv(QUESTIONS_CSV, encoding="utf_8_sig")
            total_questions_count = len(df_q)  # 全問題数

            display_data = []
            for _, row in df_q.iterrows():
                q_txt = str(row["問題文"]).strip()
                h = stats.get(q_txt, [])

                first_res = h[0] if h else "未回答"
                latest_res = h[-1] if h else "未回答"

                # フィルター適用
                if maj_cat != "すべて" and str(row["大項目"]) != maj_cat: continue
                if min_cat != "すべて" and str(row["小項目"]) != min_cat: continue
                if level_filter != "すべて" and str(row["レベル"]) != level_filter: continue
                if result_filter != "すべて" and latest_res != result_filter: continue

                display_data.append({
                    "大項目": row["大項目"],
                    "小項目": row["小項目"],
                    "レベル": row["レベル"],
                    "問題文": q_txt,
                    "初回成績": first_res,
                    "最新成績": latest_res,
                    "回答回数": len(h),
                    "解答": row["解答"],
                    "解説": row["解説"]
                })

            if display_data:
                res_df = pd.DataFrame(display_data)

                # --- 統計メトリクスのアップデート ---
                col_m1, col_m2, col_m3 = st.columns(3)
                overcome_count = len(res_df[(res_df["初回成績"] == "不正解") & (res_df["最新成績"] == "正解")])
                answered_count = len(res_df[res_df['最新成績'] != '未回答'])

                col_m1.metric("弱点克服数", f"{overcome_count} 問")
                col_m2.metric("総解答数 / 全問題数", f"{answered_count} / {total_questions_count}")
                # 進捗率を％で表示
                progress_percent = int(
                    (answered_count / total_questions_count) * 100) if total_questions_count > 0 else 0
                col_m3.metric("学習進捗率", f"{progress_percent} %")

                st.subheader("📋 復習対象の選択")

                selected_event = st.dataframe(
                    res_df[["大項目", "小項目", "レベル", "問題文", "初回成績", "最新成績", "回答回数"]],
                    width='stretch',
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="multi-row"
                )

                selected_rows = selected_event.selection.rows

                c_btn1, c_btn2 = st.columns(2)
                with c_btn1:
                    if st.button(f"🔄 選択した {len(selected_rows)} 問を復習", width='stretch', type="primary",
                                 disabled=len(selected_rows) == 0):
                        selected_q_texts = res_df.iloc[selected_rows]["問題文"].tolist()
                        target_questions = df_q[df_q["問題文"].isin(selected_q_texts)].values.tolist()
                        st.session_state.questions = target_questions
                        st.session_state.quiz_started = True
                        st.session_state.current_index = 0
                        st.session_state.quiz_mode = "manual_review"
                        st.rerun()

                with c_btn2:
                    if st.button("📖 表示中の全問題を復習", width='stretch'):
                        target_questions = df_q[df_q["問題文"].isin(res_df["問題文"])].values.tolist()
                        st.session_state.questions = target_questions
                        st.session_state.quiz_started = True
                        st.session_state.current_index = 0
                        st.session_state.quiz_mode = "filter_review"
                        st.rerun()

                if len(selected_rows) == 1:
                    st.divider()
                    q_detail = res_df.iloc[selected_rows[0]]
                    with st.container(border=True):
                        st.markdown(f"### 🔍 問題プレビュー\n**{q_detail['問題文']}**")
                        if q_detail['最新成績'] != "未回答":
                            st.success(f"**【解答】**\n{q_detail['解答']}")
                            st.info(f"**【解説】**\n{q_detail['解説']}")
            else:
                st.info("条件に一致するデータがありません。")

    with tab2:
        st.markdown("### 🏆 テスト履歴")
        if os.path.exists(TEST_RESULTS_CSV):
            df_test = pd.read_csv(TEST_RESULTS_CSV, encoding="utf_8_sig")
            df_test = df_test.sort_values(by="日時", ascending=False)
            st.dataframe(df_test, width='stretch', hide_index=True)
        else:
            st.info("テスト履歴がありません。")
# --- 1. 補助関数（ファイル管理・データ操作） ---
def ensure_csv_exists(path, columns):
    """CSVファイルとディレクトリの存在を保証する"""
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        pd.DataFrame(columns=columns).to_csv(path, index=False, encoding="utf_8_sig")
def save_message(title, content, status, is_anon, is_public, u_name, MASTER_CSV, USER_CSV):
    """メッセージをマスターとユーザー用CSVの両方に保存する"""
    now = datetime.datetime.now()
    new_data = {
        "ID": now.strftime("%Y%m%d%H%M%S"),
        "日時": now.strftime("%Y/%m/%d %H:%M"),
        "ユーザー": "匿名さん" if is_anon else u_name,
        "タイトル": title,
        "内容": content,
        "回答": "",
        "ステータス": status,
        "公開フラグ": "公開" if is_public else "非公開"
    }
    cols = ["ID", "日時", "ユーザー", "タイトル", "内容", "回答", "ステータス", "公開フラグ"]
    for path in [MASTER_CSV, USER_CSV]:
        ensure_csv_exists(path, cols)
        df = pd.read_csv(path, encoding="utf_8_sig")
        df = pd.concat([df, pd.DataFrame([new_data])], ignore_index=True)
        df.to_csv(path, index=False, encoding="utf_8_sig")
def delete_message(msg_id, MASTER_CSV, USER_CSV):
    """マスターとユーザー用CSVからメッセージを削除する"""
    for path in [MASTER_CSV, USER_CSV]:
        if os.path.exists(path):
            df = pd.read_csv(path, encoding="utf_8_sig")
            # IDを文字列として比較して削除
            df = df[df['ID'].astype(str) != str(msg_id)]
            df.to_csv(path, index=False, encoding="utf_8_sig")
def submit_answer(m_id, ans_text, MASTER_CSV):
    """管理者回答を保存する"""
    df = pd.read_csv(MASTER_CSV, encoding="utf_8_sig")
    df.loc[df['ID'].astype(str) == str(m_id), '回答'] = ans_text
    df.loc[df['ID'].astype(str) == str(m_id), 'ステータス'] = "回答済み"
    df.to_csv(MASTER_CSV, index=False, encoding="utf_8_sig")
# --- 2. 描画パーツ ---
def render_post_form(u_name, u_role, MASTER_CSV, USER_CSV):
    """新規投稿フォーム"""
    st.subheader("📝 メッセージ作成")

    # 状態管理（問題引用によるタイトル自動入力用）
    if "temp_title" not in st.session_state:
        st.session_state.temp_title = ""

    type_options = ["質問", "システムの要望", "問題の異議申し立て"]
    if any(r in str(u_role) for r in ["管理者", "メンター", "教育係"]):
        type_options.insert(0, "お知らせ")

    msg_type = st.selectbox("カテゴリー", type_options, key="msg_type_select")

    # 異議申し立ての場合の引用ツール（送信ボタンの反応を避けるためFormの外）
    if msg_type == "問題の異議申し立て":
        st.info("👇 引用する問題を選択すると、タイトルに問題文が自動入力されます。")
        Q_CSV = "assets/spread_data/questions.csv"
        if os.path.exists(Q_CSV):
            df_q = pd.read_csv(Q_CSV, encoding="utf_8_sig")
            c1, c2 = st.columns(2)
            maj = c1.selectbox("大項目", ["すべて"] + sorted(df_q["大項目"].unique().tolist()))
            tmp = df_q if maj == "すべて" else df_q[df_q["大項目"] == maj]
            min_cat = c2.selectbox("小項目", ["すべて"] + sorted(tmp["小項目"].unique().tolist()))

            final_df = tmp if min_cat == "すべて" else tmp[tmp["小項目"] == min_cat]
            selected_q = st.selectbox("問題を選択", ["-- 選択 --"] + final_df["問題文"].tolist())

            if selected_q != "-- 選択 --":
                st.session_state.temp_title = selected_q  # タイトルにセット
        else:
            st.error("問題データが見つかりません。")

    with st.form("post_form"):
        # 引用がある場合はその値を初期値にする
        title = st.text_input("件名（問題文）", value=st.session_state.temp_title)
        content = st.text_area("本文", height=200, placeholder="具体的な要望や、異議の内容を詳しく記入してください。")
        c1, c2 = st.columns(2)
        is_anon = c1.checkbox("匿名投稿（管理側には氏名が記録されます）")
        is_public = c2.checkbox("全体公開", value=True)

        if st.form_submit_button("🚀 メッセージを送信", width='stretch'):
            if title and content:
                save_message(title, content, msg_type, is_anon, is_public, u_name, MASTER_CSV, USER_CSV)
                st.session_state.temp_title = ""  # リセット
                st.success("送信しました！")
                st.session_state.forum_view = "list"
                st.rerun()
            else:
                st.error("件名と本文を入力してください。")

    if st.button("← 戻る"):
        st.session_state.temp_title = ""
        st.session_state.forum_view = "list"
        st.rerun()
# --- 3. メイン機能 ---
def show_message_hub():
    """掲示板メイン"""
    u_id = st.session_state.get('user', {}).get('id', 'guest')
    u_name = st.session_state.get('user', {}).get('name', 'Unknown')
    u_role = st.session_state.get('user', {}).get('role', '一般')

    MASTER_CSV = "assets/spread_data/forum_master.csv"
    USER_CSV = f"assets/users/{u_id}/my_forum.csv"
    cols = ["ID", "日時", "ユーザー", "タイトル", "内容", "回答", "ステータス", "公開フラグ"]

    ensure_csv_exists(MASTER_CSV, cols)
    ensure_csv_exists(USER_CSV, cols)

    if st.session_state.get("forum_view") == "post":
        render_post_form(u_name, u_role, MASTER_CSV, USER_CSV)
        return

    # --- 一覧表示画面 ---
    with st.sidebar:
        st.markdown("### 📂 カテゴリー")
        f_cat = st.radio("表示切り替え", ["すべて", "お知らせ", "質問", "システムの要望", "問題の異議申し立て", "解決済み"])
        st.divider()
        if st.button("➕ 新規メッセージ作成", type="primary", use_container_width=True):
            st.session_state.forum_view = "post"
            st.rerun()

    df = pd.read_csv(MASTER_CSV, encoding="utf_8_sig")

    # フィルタリング
    if f_cat == "解決済み":
        df = df[df["ステータス"] == "回答済み"]
    elif f_cat != "すべて":
        df = df[df["ステータス"] == f_cat]

    # 公開制限
    is_admin = any(r in str(u_role) for r in ["管理者", "メンター", "教育係"])
    df = df[(df["公開フラグ"] == "公開") | (df["ユーザー"] == u_name) | (is_admin)]

    col_l, col_r = st.columns([1, 1.2])

    with col_l:
        selected_event = None
        if df.empty:
            st.info("表示できるメッセージはありません。")
        else:
            list_df = df[["日時", "ステータス", "タイトル"]].sort_values("日時", ascending=False)
            selected_event = st.dataframe(
                list_df, width='stretch', hide_index=True,
                on_select="rerun", selection_mode="single-row"
            )

    with col_r:
        if selected_event is not None and "selection" in selected_event and len(selected_event.selection.rows) > 0:
            idx = list_df.index[selected_event.selection.rows[0]]
            msg = df.loc[idx]

            # --- 詳細ヘッダー ---
            st.markdown(f"#### {msg['タイトル']}")
            st.caption(f"📅 {msg['日時']} | 👤 {msg['ユーザー']} | 🏷️ {msg['ステータス']}")

            # 自分の投稿、または管理者なら削除ボタンを表示
            can_delete = (msg['ユーザー'] == u_name) or (msg['ユーザー'] == "匿名さん" and is_admin) or is_admin

            if can_delete:
                if st.button("🗑️ この投稿を削除する", type="secondary"):
                    delete_message(msg['ID'], MASTER_CSV, USER_CSV)
                    st.toast("削除しました")
                    st.rerun()

            st.markdown("---")
            st.markdown(msg['内容'])

            # 回答表示
            if pd.notna(msg['回答']) and str(msg['回答']).strip():
                st.success(f"**【回答】**\n\n{msg['回答']}")

            # 管理者回答エリア
            if is_admin:
                st.divider()
                with st.expander("💬 回答を入力・更新する"):
                    ans_text = st.text_area("回答内容", key=f"ans_{msg['ID']}")
                    if st.button("回答を登録", key=f"btn_{msg['ID']}"):
                        submit_answer(msg['ID'], ans_text, MASTER_CSV)
                        st.success("回答を登録しました。")
                        st.rerun()
        else:
            st.info("左側のリストからメッセージを選択してください。")
def show_meeting_page():
    """📖 勉強会資料：PPT/PDF対応・フォルダ管理機能"""
    st.markdown("## 📖 勉強会資料ライブラリ")

    # --- 1. ディレクトリ設定 ---
    MEETING_DIR = os.path.join("assets", "drive_data", "meeting")
    if not os.path.exists(MEETING_DIR):
        os.makedirs(MEETING_DIR, exist_ok=True)

    u_role = str(st.session_state.get('user', {}).get('role', '一般'))
    is_admin = any(r in u_role for r in ["管理者", "教育係", "メンター"])

    # --- 2. サイドバー：フォルダ管理 ---
    with st.sidebar:
        st.header("📂 フォルダ管理")

        folders = sorted([f for f in os.listdir(MEETING_DIR) if os.path.isdir(os.path.join(MEETING_DIR, f))])

        if is_admin:
            with st.expander("🆕 新規フォルダ作成"):
                new_folder_name = st.text_input("フォルダ名を入力", key="new_folder_input")
                if st.button("フォルダを作成", use_container_width=True):
                    if new_folder_name:
                        new_path = os.path.join(MEETING_DIR, new_folder_name)
                        if not os.path.exists(new_path):
                            os.makedirs(new_path)
                            st.success(f"作成: {new_folder_name}")
                            st.rerun()
                        else:
                            st.warning("既に存在します")

        if not folders:
            st.info("フォルダを作成してください")
            selected_folder = None
        else:
            selected_folder = st.selectbox("カテゴリを選択", folders)

        # フォルダ削除の修正（安全な削除処理）
        if is_admin and selected_folder:
            st.divider()
            st.warning(f"「{selected_folder}」を削除")
            if st.button("🚨 フォルダを完全に消去", use_container_width=True):
                try:
                    target_path = os.path.join(MEETING_DIR, selected_folder)
                    # フォルダを削除（中身があっても強制削除）
                    shutil.rmtree(target_path, ignore_errors=True)
                    st.toast(f"{selected_folder} を削除しました")
                    time.sleep(0.5)  # 反映待ち
                    st.rerun()
                except Exception as e:
                    st.error(f"削除失敗: {e}")

    # --- 3. メインエリア ---
    if selected_folder:
        folder_path = os.path.join(MEETING_DIR, selected_folder)

        # PDFとPPT(x)を両方取得
        files = sorted([f for f in os.listdir(folder_path)
                        if f.lower().endswith(('.pdf', '.pptx', '.ppt'))])

        col_list, col_view = st.columns([1, 2])

        with col_list:
            st.markdown(f"### 📁 {selected_folder}")

            if is_admin:
                with st.expander("📤 ファイルを追加"):
                    # PDF, PPT, PPTXを許可
                    uploaded_file = st.file_uploader("資料を選択", type=["pdf", "pptx", "ppt"])
                    if uploaded_file:
                        save_path = os.path.join(folder_path, uploaded_file.name)
                        with open(save_path, "wb") as f:
                            f.write(uploaded_file.getbuffer())
                        st.success("アップロード完了")
                        st.rerun()

            st.divider()

            if not files:
                st.write("ファイルがありません")
                selected_file = None
            else:
                selected_file = st.radio("資料を選択", files, key="meeting_file_radio")

                if is_admin and selected_file:
                    if st.button("🗑️ ファイルを削除"):
                        os.remove(os.path.join(folder_path, selected_file))
                        st.rerun()

        with col_view:
            if selected_file:
                file_ext = os.path.splitext(selected_file)[1].lower()
                full_path = os.path.join(folder_path, selected_file)

                if file_ext == ".pdf":
                    # PDFはプレビュー表示
                    display_pdf(full_path)
                else:
                    # PowerPointはダウンロード案内
                    st.markdown("#### 📊 PowerPoint資料")
                    st.info("PowerPointファイルはブラウザで直接プレビューできません。ダウンロードしてご確認ください。")
                    with open(full_path, "rb") as f:
                        st.download_button(
                            label=f"📥 {selected_file} をダウンロード",
                            data=f,
                            file_name=selected_file,
                            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                            use_container_width=True
                        )
                    # アイコン表示などで賑やかし
                    st.image("https://img.icons8.com/color/144/powerpoint.png")
            else:
                st.info("資料を選択してください")
    else:
        st.info("フォルダを選択してください")
def display_pdf(file_path):
    """PDF表示用HTML"""
    try:
        with open(file_path, "rb") as f:
            base64_pdf = base64.b64encode(f.read()).decode('utf-8')
        pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800px" type="application/pdf"></iframe>'
        st.markdown(pdf_display, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"エラー: {e}")
def show_diary_page():
    """📔 業務・学習日誌ページ"""
    st.markdown("## 📔 業務・学習日誌ポートフォリオ")

    # --- 1. ユーザー情報とパス設定 ---
    u_id = st.session_state.get('user', {}).get('id', 'guest')
    u_name = st.session_state.get('user', {}).get('name', 'Unknown')
    u_role = str(st.session_state.get('user', {}).get('role', '一般'))

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

            # リストから選択（初期値は「新規作成」相当としてNoneを扱えるようにする）
            list_options = ["🆕 新規作成"] + df_display["日付"].tolist()
            selected_date = st.radio("記録を選択", list_options)
        else:
            st.info("記録がありません。")
            selected_date = "🆕 新規作成"

    # --- 3. メインエリア：編集・閲覧 ---

    # モード判定
    is_new = (selected_date == "🆕 新規作成")

    if is_new:
        st.subheader("📝 本日の学びを記録する")
        current_date = datetime.date.today().strftime("%Y-%m-%d")
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
        if st.button("💾 日誌を保存", type="primary", use_container_width=True):
            if not content.strip():
                st.error("内容を入力してください。")
            else:
                # 更新処理
                new_row = {"日付": current_date, "内容": content, "コメント": current_comment}

                if is_new:
                    # 同じ日付が既にないかチェック
                    if current_date in df["日付"].values:
                        # 上書き
                        df.loc[df["日付"] == current_date, ["内容", "コメント"]] = [content, current_comment]
                    else:
                        # 新規追加
                        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                        # 経験値獲得のメッセージ（実際の加算処理はシステムに合わせて呼び出し）
                        st.toast("経験値を獲得しました！(+10 EXP)")
                else:
                    df.loc[df["日付"] == current_date, ["内容", "コメント"]] = [content, current_comment]

                df.to_csv(DIARY_CSV, index=False, encoding="utf_8_sig")
                st.success(f"{current_date} の記録を保存しました。")
                time.sleep(1)
                st.rerun()

    with col_del:
        if not is_new:
            if st.button("🗑 記録を削除", use_container_width=True):
                df = df[df["日付"] != current_date]
                df.to_csv(DIARY_CSV, index=False, encoding="utf_8_sig")
                st.warning("記録を削除しました。")
                time.sleep(1)
                st.rerun()

    # --- 4. 管理者用：フィードバック入力機能 ---
    is_mentor = any(r in u_role for r in ["管理者", "教育係", "メンター"])

    if is_mentor and not is_new:
        st.divider()
        st.subheader("👨‍🏫 指導者用フィードバック入力")
        new_comment = st.text_area("アドバイス・返信", value=current_comment, key="mentor_comment")
        if st.button("コメントを登録", use_container_width=True):
            df.loc[df["日付"] == current_date, "コメント"] = new_comment
            df.to_csv(DIARY_CSV, index=False, encoding="utf_8_sig")
            st.success("フィードバックを登録しました。")
            time.sleep(1)
            st.rerun()
# --- 1. 共通定数の設定 ---
ASSETS_DIR = "assets"
LOGIN_CSV = "login_data.csv"
TASK_CSV = "assets/spread_data/task_list.csv"
def show_mentor_page():
    """教育者用コンソールのメインエントリポイント"""
    st.sidebar.markdown("### 🛠️ Mentor Console")

    # メニュー選択
    menu = st.sidebar.radio(
        "メニューを選択",
        ["👥 新人進捗ダッシュボード", "📊 全員比較マトリックス", "📋 チェックリスト編集"],
        key="mentor_menu_v2"
    )

    st.sidebar.divider()
    if st.sidebar.button("🏠 メインメニューへ戻る", width='stretch'):
        st.session_state.page = "main"
        st.rerun()

    # 各画面の呼び出し
    if menu == "👥 新人進捗ダッシュボード":
        render_dashboard_view()
    elif menu == "📊 全員比較マトリックス":
        render_matrix_view()
    elif menu == "📋 チェックリスト編集":
        render_checklist_editor()
# ==========================================
# 1. 進捗ダッシュボード & 個別詳細
# ==========================================
def render_dashboard_view():
    st.title("新人薬剤師 育成進捗一覧")

    if not os.path.exists(LOGIN_CSV):
        st.error("ユーザーデータ(login_data.csv)が見つかりません。")
        return

    # ユーザーリスト読み込み
    df_users = pd.read_csv(LOGIN_CSV, encoding="utf_8_sig")
    newcomers = df_users[df_users['role'].isin(["新人薬剤師", "新人"])]

    # タスク合計数の把握
    total_tasks = {"調剤室業務": 0, "注射室業務": 0}
    if os.path.exists(TASK_CSV):
        df_tasks = pd.read_csv(TASK_CSV, encoding="utf_8_sig")
        for cat in total_tasks.keys():
            total_tasks[cat] = len(df_tasks[df_tasks['カテゴリ'] == cat])

    summary_list = []
    for _, user in newcomers.iterrows():
        user_id = str(user['id'])
        p_path = f"{ASSETS_DIR}/users/{user_id}/my_progress.csv"

        counts = {"調剤室業務": 0, "注射室業務": 0}
        status = "未ログイン"

        if os.path.exists(p_path):
            try:
                df_p = pd.read_csv(p_path, encoding="utf_8_sig")
                for cat in counts.keys():
                    counts[cat] = len(df_p[df_p['カテゴリ'] == cat])
                status = "利用中"
            except:
                status = "データエラー"

        def make_bar_text(d, t):
            if t <= 0: return "□□□□□□□□□□ 0%"
            p = min(100, int((d / t) * 100))
            bar = '■' * (p // 10) + '□' * (10 - (p // 10))
            return f"{bar} {p}%"

        summary_list.append({
            "ID": user_id,
            "新人氏名": user['name'],
            "調剤室業務 進捗": make_bar_text(counts["調剤室業務"], total_tasks["調剤室業務"]),
            "注射室業務 進捗": make_bar_text(counts["注射室業務"], total_tasks["注射室業務"]),
            "状態": status
        })

    df_summary = pd.DataFrame(summary_list)
    st.dataframe(df_summary.drop(columns=["ID"]), width='stretch', hide_index=True)

    # --- 個別詳細セクション ---
    st.divider()
    if not df_summary.empty:
        selected_name = st.selectbox("詳細を確認する新人を選択", df_summary['新人氏名'])

        if st.button(f"👤 {selected_name} さんの個別詳細・指導画面を表示", width='stretch'):
            st.session_state.target_user = df_summary[df_summary['新人氏名'] == selected_name].iloc[0]
            st.session_state.show_detail = True

    # 詳細画面が表示フラグが立っている場合
    if st.session_state.get('show_detail'):
        render_individual_detail(st.session_state.target_user)
def render_individual_detail(user):
    """特定のユーザーの進捗・日誌を深く確認し、指導コメントを残す"""
    st.markdown(f"---")
    st.subheader(f"📊 {user['新人氏名']} さんの詳細状況")

    t1, t2, t3 = st.tabs(["📔 日誌指導", "📋 実務進捗", "🏆 成績推移"])

    with t1:
        d_path = f"{ASSETS_DIR}/users/{user['ID']}/diary.csv"
        if os.path.exists(d_path):
            df_diary = pd.read_csv(d_path, encoding="utf_8_sig")
            if not df_diary.empty:
                dates = df_diary['日付'].tolist()
                sel_date = st.selectbox("指導する日付を選択", dates)
                day_data = df_diary[df_diary['日付'] == sel_date].iloc[0]

                st.info(f"**新人記入内容:**\n\n{day_data['内容']}")

                mentor_note = st.text_area("✍ メンターコメント", value=str(day_data.get('コメント', '')), key=f"note_{user['ID']}")
                if st.button("指導コメントを保存"):
                    df_diary.loc[df_diary['日付'] == sel_date, 'コメント'] = mentor_note
                    df_diary.to_csv(d_path, index=False, encoding="utf_8_sig")
                    st.success("コメントを保存しました。")
            else:
                st.write("まだ日誌の記入がありません。")
        else:
            st.warning("日誌ファイルが存在しません。")

    with t2:
        p_path = f"{ASSETS_DIR}/users/{user['ID']}/my_progress.csv"
        if os.path.exists(p_path):
            st.dataframe(pd.read_csv(p_path, encoding="utf_8_sig"), width='stretch')
        else:
            st.info("進捗データがありません。")

    with t3:
        r_path = f"{ASSETS_DIR}/users/{user['ID']}/my_test_results.csv"
        if os.path.exists(r_path):
            df_res = pd.read_csv(r_path, encoding="utf_8_sig")
            if not df_res.empty:
                st.line_chart(df_res.set_index('実施日')['得点'])
            st.dataframe(df_res, width='stretch')
        else:
            st.info("テスト履歴がありません。")

    if st.button("詳細画面を閉じる"):
        st.session_state.show_detail = False
        st.rerun()
# ==========================================
# 2. 全員比較マトリックス
# ==========================================
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

    matrix = df_tasks.copy()
    for _, user in newcomers.iterrows():
        if user['name'] not in selected_names: continue

        p_path = f"{ASSETS_DIR}/users/{user['id']}/my_progress.csv"
        scores = {}
        if os.path.exists(p_path):
            try:
                df_p = pd.read_csv(p_path, encoding="utf_8_sig")
                scores = dict(zip(df_p['項目'], df_p['習得度']))
            except:
                pass

        def convert_score(v):
            v = str(v)
            return v.count("★") if "★" in v else (int(v) if v.isdigit() else 0)

        matrix[user['name']] = matrix['項目'].apply(lambda x: convert_score(scores.get(x, 0)))

    st.dataframe(matrix, width='stretch', hide_index=True)

    # Excelダウンロード
    try:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            matrix.to_excel(writer, index=False, sheet_name='進捗比較')

        st.download_button(
            label="📗 Excelレポートをダウンロード",
            data=output.getvalue(),
            file_name=f"進捗レポート_{datetime.now().strftime('%Y%m%d')}.xlsx",  # ← ここでエラーが出ていました
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width='stretch'
        )
    except Exception as e:
        st.error(f"Excel作成エラー (xlsxwriterが必要): {e}")
# ==========================================
# 3. チェックリスト編集
# ==========================================
def render_checklist_editor():
    st.title("📋 実務チェックリスト項目編集")

    if os.path.exists(TASK_CSV):
        df_tasks = pd.read_csv(TASK_CSV, encoding="utf_8_sig")
    else:
        df_tasks = pd.DataFrame(columns=["カテゴリ", "項目"])

    st.write("※ 編集後、必ず下の保存ボタンを押してください。")
    edited_df = st.data_editor(df_tasks, num_rows="dynamic", width='stretch')

    if st.button("💾 この内容でマスターを更新保存", width='stretch'):
        edited_df.to_csv(TASK_CSV, index=False, encoding="utf_8_sig")
        st.success("タスクリストを更新しました。")
        time.sleep(1)
        st.rerun()
# --- 定数設定（Tkinter版のパスを継承） ---
IN_DATA_DIR = "assets/spread_data"
OUT_DATA_DIR = "assets/drive_data"
ASSETS_DIR = "assets"
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
# --- 履歴管理用補助関数 ---
def save_search_log(query):
    """個人の検索履歴を保存（assets/users/ID/search_history.csv）"""
    if 'user' not in st.session_state: return

    user_id = st.session_state['user']['id']
    user_dir = os.path.join(ASSETS_DIR, "users", str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    log_path = os.path.join(user_dir, "search_history.csv")

    with open(log_path, "a", encoding="utf_8_sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"), query])
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
def show_simulation_page():
    # サブページの初期化
    if 'sub_page' not in st.session_state:
        st.session_state['sub_page'] = 'menu'

    # 1. メニュー画面
    if st.session_state['sub_page'] == 'menu':
        st.markdown("## 🎮 シミュレーション・トレーニング")
        st.write("トレーニングしたい項目を選択してください。")

        col1, col2 = st.columns(2)

        with col1:
            with st.container(border=True):
                st.subheader("💊 持参薬鑑別")
                st.write("お薬手帳と現物を確認し、鑑別報告書を作成する練習です。")
                if st.button("持参薬鑑別を始める", use_container_width=True, type="primary"):
                    st.session_state['sub_page'] = 'kanbetsu'
                    st.rerun()

        with col2:
            with st.container(border=True):
                st.subheader("🧪 レジメン監査")
                st.write("浜松医療センターのプロトコルに基づき、抗がん剤の処方監査を練習します。")
                if st.button("レジメン監査を始める", use_container_width=True, type="primary"):
                    st.session_state['sub_page'] = 'regimen'
                    st.rerun()

        st.divider()
        if st.button("🏠 メインメニューへ戻る"):
            st.session_state['page'] = 'main'
            st.rerun()

    # 2. 持参薬鑑別ページ
    elif st.session_state['sub_page'] == 'kanbetsu':
        show_kanbetsu_practice() # 前回の厳格判定版

    # 3. レジメン監査ページ
    elif st.session_state['sub_page'] == 'regimen':
        show_regimen_simulation() # 新規作成


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

    if st.button("🏠 シミュレーションメニューに戻る", use_container_width=True):
        st.session_state['sub_page'] = 'menu'
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
    if st.button("🏠 シミュレーションメニューに戻る", use_container_width=True):
        st.session_state['sub_page'] = 'menu'
        st.rerun()
# --- 5. メイン制御 ---
def main():
    # --- 1. 状態の初期化 ---
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
        if st.session_state['view'] == 'login':
            show_login_page()
        else:
            show_signup_page()
        return

    # --- 3. 共通ナビゲーション設定 ---
    current_page = st.session_state['page']
    u_role = str(st.session_state.get('user', {}).get('role', '一般'))
    # 管理者、教育係、メンターのいずれかであれば教育者権限ありとみなす
    is_mentor_staff = any(r in u_role for r in ["管理者", "教育係", "メンター"])

    # メイン画面以外でのサイドバー処理
    if current_page != 'main':
        with st.sidebar:
            st.markdown("---")
            # use_container_width=True でボタン幅を調整
            if st.button("🏠 メインメニューへ", use_container_width=True):
                # ページ移動時に各ページの状態をリセット
                st.session_state['page'] = 'main'

                # 【修正ポイント】シミュレーション内の階層をリセット
                if 'sub_page' in st.session_state:
                    st.session_state['sub_page'] = 'menu'

                st.session_state['quiz_started'] = False
                st.session_state.forum_view = "list"
                st.session_state.temp_title = ""
                # メンター用の選択状態や詳細表示フラグもリセット
                if "selected_mentor_user" in st.session_state:
                    del st.session_state["selected_mentor_user"]
                if "show_detail" in st.session_state:
                    st.session_state.show_detail = False
                st.rerun()

    # --- 4. ページ分岐ロジック ---

    # A. ホーム
    if current_page == 'main':
        if st.session_state['is_guest']:
            show_guest_menu()
        else:
            show_main_menu()

    # B. 参考資料
    elif current_page == 'study':
        show_study_page()

    # C. 学習・クイズ
    elif current_page == 'quiz':
        if st.session_state.get('quiz_started'):
            show_quiz_engine()
        else:
            show_quiz_page()

    # D. 学習履歴
    elif current_page == 'review':
        if st.session_state['is_guest']:
            st.warning("ゲストモードでは履歴機能は利用できません。")
        else:
            show_review_page()

    # E. 掲示板
    elif current_page == 'board':
        if st.session_state['is_guest']:
            st.error("この機能は職員専用です。")
        else:
            show_message_hub()

    # F. 勉強会資料
    elif current_page == 'meeting':
        show_meeting_page()

    # G. 業務日誌
    elif current_page == 'diary':
        if st.session_state['is_guest']:
            st.error("ゲストモードでは日誌機能は利用できません。")
        else:
            show_diary_page()

    # H. 統合検索
    elif current_page == 'search':
        show_search_page()

    # I. 教育者用コンソール
    elif current_page in ['mentor', 'mentor_dashboard']:
        if is_mentor_staff:
            show_mentor_page()
        else:
            st.error("アクセス権限がありません。")

    # J. 拡張ツール
    elif current_page == 'simulation':
        show_simulation_page()

    # K. 不明なページ
    else:
        st.warning(f"不明なページです: {current_page}")
        if st.button("ホームへ戻る"):
            st.session_state['page'] = 'main'
            st.rerun()

if __name__ == "__main__":
    main()
