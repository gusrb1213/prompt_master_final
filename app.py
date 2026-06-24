"""
PromptMaster — 프롬프트 엔지니어링 문제집
실행: streamlit run app.py
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pandas as pd
import streamlit as st

import auth
import scoring as sc

ROOT        = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "example_data.json"

LEVEL_COLORS = {
    "beginner":     "#2e7d32",
    "elementary":   "#1565c0",
    "intermediate": "#6a1b9a",
    "advanced":     "#e65100",
    "expert":       "#b71c1c",
}

# ── 페이지 설정 ──────────────────────────────────────────────
st.set_page_config(
    page_title="PromptMaster",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .pm-header { background: linear-gradient(90deg,#1a237e,#283593); color:#fff;
        padding:1.2rem 1.5rem; border-radius:8px; margin-bottom:1rem; }
    .pm-header h1 { color:#fff !important; font-size:1.5rem; margin:0; }
    .pm-header p  { color:#e8eaf6; margin:.4rem 0 0; font-size:.95rem; }
    .pm-badge { display:inline-block; padding:2px 8px; border-radius:4px;
        font-size:.75rem; font-weight:600; color:#fff; }
    .tier-badge { display:inline-flex; align-items:center; gap:6px;
        padding:4px 12px; border-radius:20px; font-size:.85rem; font-weight:600;
        background:#f0f2f6; }
    .score-delta-pos { color:#2e7d32; font-weight:600; }
    .score-delta-neg { color:#c62828; font-weight:600; }
    .hint-toggle-btn { cursor:pointer; }
    div[data-testid="stDataFrame"] { font-size:.9rem; }
    .stButton > button[kind="primary"] { background-color:#283593; }
</style>
""", unsafe_allow_html=True)


# ── 캐시 ─────────────────────────────────────────────────────
CONFIG_VERSION = 3

@st.cache_data
def load_config(_v: int, _mt: float) -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

def get_config() -> dict:
    mt = CONFIG_PATH.stat().st_mtime if CONFIG_PATH.exists() else 0.0
    return load_config(CONFIG_VERSION, mt)

@st.cache_resource(show_spinner="V11 엔진 로딩 중 (최초 1회)…")
def load_engine():
    from prompt_master_v11 import PromptMasterV11
    return PromptMasterV11.from_json_config(CONFIG_PATH)


def normalize_scenarios(raw: list[dict]) -> list[dict]:
    defaults = ["business_tone", "json_format", "length_limit"]
    result = []
    for i, item in enumerate(raw):
        s = dict(item)
        s.setdefault("number",             1001 + i)
        s.setdefault("active_constraints", defaults)
        s.setdefault("pass_threshold",     60)
        s.setdefault("level",              "intermediate")
        s.setdefault("hint",               "출력 형식·톤·분량을 구체적으로 적어 보세요.")
        result.append(s)
    return result


def scenario_no(s: dict) -> int:
    return int(s["number"])


def constraint_label(config: dict, cid: str) -> str:
    for c in config.get("constraints", []):
        if c["id"] == cid:
            return c["name"]
    return cid


def level_map(config: dict) -> dict[str, dict]:
    return {lv["id"]: lv for lv in config.get("levels", [])}


# ── 세션 초기화 ───────────────────────────────────────────────
def init_session() -> None:
    for k, v in [
        ("logged_in",    False),
        ("email",        ""),
        ("view",         "list"),
        ("problem_no",   None),
        ("filter_level", "전체"),
        ("hint_shown",   {}),   # {problem_no: bool}
    ]:
        if k not in st.session_state:
            st.session_state[k] = v


# ════════════════════════════════════════════════════════════
#  인증 화면
# ════════════════════════════════════════════════════════════
def render_auth() -> None:
    st.markdown("""
    <div class="pm-header">
        <h1>📋 PromptMaster</h1>
        <p>프롬프트 엔지니어링 실력을 키우는 100제 문제집</p>
    </div>
    """, unsafe_allow_html=True)

    tab_login, tab_register = st.tabs(["로그인", "회원가입"])

    # ── 로그인 탭 ──────────────────────────────────────────
    with tab_login:
        email_l = st.text_input("이메일", key="login_email")
        pw_l    = st.text_input("비밀번호", type="password", key="login_pw")

        if st.button("로그인", type="primary", use_container_width=True, key="btn_login"):
            if not email_l or not pw_l:
                st.warning("이메일과 비밀번호를 입력해 주세요.")
            else:
                ok, msg = auth.login(email_l.strip(), pw_l)
                if ok:
                    st.session_state.logged_in = True
                    st.session_state.email = email_l.strip()
                    st.rerun()
                else:
                    st.error(msg)

    # ── 회원가입 탭 ─────────────────────────────────────────
    with tab_register:
        st.markdown("이메일 인증 후 가입이 완료됩니다.")

        reg_step = st.session_state.get("reg_step", "input")  # input | verify

        if reg_step == "input":
            email_r = st.text_input("이메일", key="reg_email")
            pw_r    = st.text_input("비밀번호 (8자 이상)", type="password", key="reg_pw")
            pw_r2   = st.text_input("비밀번호 확인",       type="password", key="reg_pw2")

            if st.button("인증 코드 발송", use_container_width=True, key="btn_send_code"):
                if not email_r or not pw_r:
                    st.warning("이메일과 비밀번호를 입력해 주세요.")
                elif pw_r != pw_r2:
                    st.error("비밀번호가 일치하지 않습니다.")
                elif len(pw_r) < 8:
                    st.error("비밀번호는 8자 이상이어야 합니다.")
                elif not re.match(r"[^@]+@[^@]+\.[^@]+", email_r):
                    st.error("올바른 이메일 형식을 입력해 주세요.")
                elif auth.user_exists(email_r.strip()):
                    st.error("이미 가입된 이메일입니다.")
                else:
                    code = auth.generate_code(email_r.strip())
                    st.session_state["_reg_email"] = email_r.strip()
                    st.session_state["_reg_pw"]    = pw_r
                    st.session_state["reg_step"]   = "verify"
                    # 실제 서비스에서는 이메일 발송 — 개발 환경에서는 터미널 출력
                    auth.send_code_email(email_r.strip(), code)
                    st.info("📧 입력하신 이메일로 인증 코드를 발송했습니다.")
                    st.session_state["reg_step"] = "verify"
                    st.rerun()

        else:  # verify
            pending_email = st.session_state.get("_reg_email", "")
            st.info(f"**{pending_email}** 으로 발송된 6자리 코드를 입력하세요.")
            if st.session_state.get("_reg_code_display"):
                st.info(f"📧 인증 코드: **{st.session_state['_reg_code_display']}**")
            code_input = st.text_input("인증 코드", max_chars=6, key="reg_code")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("인증 완료", type="primary", use_container_width=True):
                    if auth.verify_code(pending_email, code_input.strip()):
                        auth.delete_code(pending_email)
                        ok, msg = auth.register(pending_email, st.session_state["_reg_pw"])
                        if ok:
                            st.success("회원가입 완료! 로그인 탭에서 로그인해 주세요.")
                            st.session_state["reg_step"] = "input"
                        else:
                            st.error(msg)
                    else:
                        st.error("인증 코드가 올바르지 않거나 만료되었습니다.")
            with col2:
                if st.button("다시 입력", use_container_width=True):
                    st.session_state["reg_step"] = "input"
                    st.rerun()


# ════════════════════════════════════════════════════════════
#  사이드바 (로그인 후)
# ════════════════════════════════════════════════════════════
def render_sidebar(config: dict) -> None:
    email = st.session_state.email
    row   = auth.get_score_row(email)
    total = row["total_score"]
    tier  = sc.get_tier(total)
    nxt   = sc.get_next_tier(total)
    prog  = sc.tier_progress(total)

    with st.sidebar:
        st.markdown(f"### 👤 {email}")
        st.markdown(
            f'<div class="tier-badge" style="background:{tier["color"]}22;color:{tier["color"]}">'
            f'● {tier["name"]}</div>',
            unsafe_allow_html=True,
        )
        next_min = nxt["min"] if nxt else None
        progress_text = f"{total}점 / {next_min}점" if next_min else f"{total}점 (MAX)"
        st.progress(prog, text=progress_text)
        st.caption(
            f"풀이: {row['solved_count']}문제 · "
            f"오답: {row['wrong_count']}회 · "
            f"힌트: {row['hint_used_count']}회"
        )

        st.divider()
        if st.button("📋 문제집 홈", use_container_width=True):
            st.session_state.view       = "list"
            st.session_state.problem_no = None
            st.rerun()

        st.divider()
        st.markdown("#### 난이도 & 점수")
        level_info = {
            "beginner":     ("입문자 Lv.1", 10),
            "elementary":   ("초급   Lv.2", 20),
            "intermediate": ("중급   Lv.3", 40),
            "advanced":     ("고급   Lv.4", 70),
            "expert":       ("전문가 Lv.5",100),
        }
        for lvid, (label, pts) in level_info.items():
            color = LEVEL_COLORS[lvid]
            st.markdown(
                f'<span style="color:{color};font-weight:600">{label}</span>'
                f'<span style="color:#888;font-size:.8rem"> · +{pts}점 / -{ pts//2}점</span>',
                unsafe_allow_html=True,
            )

        st.divider()
        st.markdown("#### 티어 기준")
        cur_name = tier["name"]
        for t in sc.TIERS:
            mark = "▶ " if t["name"] == cur_name else "  "
            st.markdown(
                f'<span style="color:{t["color"]};font-size:.85rem">'
                f'{mark}{t["name"]} ({t["min"]}점+)</span>',
                unsafe_allow_html=True,
            )

        st.divider()
        if st.button("🔄 캐시 새로고침", use_container_width=True):
            load_config.clear()
            load_engine.clear()
            st.rerun()
        if st.button("🚪 로그아웃", use_container_width=True):
            for k in ["logged_in","email","view","problem_no","hint_shown"]:
                st.session_state.pop(k, None)
            st.rerun()


# ════════════════════════════════════════════════════════════
#  문제 목록
# ════════════════════════════════════════════════════════════
def render_problem_list(config: dict, scenarios: list[dict]) -> None:
    email   = st.session_state.email
    records = auth.get_all_records(email)
    levels  = level_map(config)
    ps      = config.get("problemset", {})

    st.markdown(f"""
    <div class="pm-header">
        <h1>문제집 : {ps.get("title","PromptMaster")}</h1>
        <p>{ps.get("description","")}</p>
    </div>
    """, unsafe_allow_html=True)

    total  = len(scenarios)
    solved = sum(1 for s in scenarios if records.get(scenario_no(s), {}).get("passed"))
    row_s  = auth.get_score_row(email)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("전체 문제",   total)
    c2.metric("맞힌 문제",   solved)
    c3.metric("내 점수",     row_s["total_score"])
    c4.metric("진행률",      f"{(solved/total*100):.0f}%" if total else "0%")

    st.markdown("##### 난이도 필터")
    level_names = ["전체"] + [
        levels[lid]["name"]
        for lid in sorted(levels, key=lambda x: levels[x]["order"])
    ]
    pick = st.radio("난이도", level_names, horizontal=True,
                    label_visibility="collapsed", key="level_radio")
    st.session_state.filter_level = pick

    filtered = scenarios
    if pick != "전체":
        lid = next(k for k, v in levels.items() if v["name"] == pick)
        filtered = [s for s in scenarios if s["level"] == lid]

    rows = []
    for s in sorted(filtered, key=scenario_no):
        lv   = levels.get(s["level"], {})
        num  = scenario_no(s)
        rec  = records.get(num)
        ac   = "✅ AC" if rec and rec["passed"] else ("⚠️ 시도" if rec else "-")
        pts  = sc.base_score(s["level"])
        rows.append({
            "번호":   num,
            "문제명": s["title"],
            "난이도": lv.get("name", s["level"]),
            "배점":   f"+{pts}점",
            "감점":   f"-{pts//2}점",
            "합격선": f"{s.get('pass_threshold',60)}점",
            "AC":     ac,
        })

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "번호": st.column_config.NumberColumn(width="small"),
            "AC":   st.column_config.TextColumn(width="small"),
        },
    )

    st.markdown("##### 문제 바로가기")
    cols = st.columns(5)
    for i, s in enumerate(sorted(filtered, key=scenario_no)):
        num   = scenario_no(s)
        badge = levels.get(s["level"], {}).get("badge", "")
        rec   = records.get(num)
        label = f"{'✅' if rec and rec['passed'] else ''}{num}\n{badge}"
        with cols[i % 5]:
            if st.button(label, key=f"open_{num}", use_container_width=True):
                st.session_state.problem_no = num
                st.session_state.view       = "solve"
                st.session_state.pop("last_evaluation", None)
                st.rerun()


# ════════════════════════════════════════════════════════════
#  풀이 화면
# ════════════════════════════════════════════════════════════
def render_solve(config: dict, scenarios: list[dict]) -> None:
    email  = st.session_state.email
    number = st.session_state.problem_no
    levels = level_map(config)

    scenario = next((s for s in scenarios if scenario_no(s) == number), None)
    if not scenario:
        st.error("문제를 찾을 수 없습니다.")
        if st.button("목록으로"):
            st.session_state.view = "list"; st.rerun()
        return

    lv    = levels.get(scenario["level"], {})
    color = LEVEL_COLORS.get(scenario["level"], "#333")
    pts   = sc.base_score(scenario["level"])
    rec   = auth.get_problem_record(email, number)

    if st.button("← 문제 목록으로"):
        st.session_state.view = "list"
        st.session_state.pop("last_evaluation", None)
        st.rerun()

    st.markdown(
        f'<span class="pm-badge" style="background:{color}">'
        f'{lv.get("name","")} · {lv.get("badge","")}</span>',
        unsafe_allow_html=True,
    )
    st.title(f"#{number} {scenario['title']}")
    st.caption(scenario.get("domain", ""))

    # 이미 AC된 문제 알림
    if rec and rec["passed"]:
        st.success(f"✅ 이미 정답 처리된 문제입니다. (획득 점수: +{rec['score_delta']}점) 다시 풀어볼 수 있습니다.")

    col_l, col_r = st.columns([1, 1])

    with col_l:
        st.markdown("#### 문제 상황")
        st.info(scenario["situation"])
        st.markdown("#### 과제")
        st.markdown(scenario["objective"])
        with st.expander("채점 기준"):
            for item in scenario.get("checklist", []):
                st.markdown(f"- {item}")
            active = scenario.get("active_constraints", [])
            st.markdown(
                "**채점 항목:** "
                + ", ".join(constraint_label(config, c) for c in active)
            )
            st.caption(f"합격선: **{scenario.get('pass_threshold',60)}점** 이상")

        # ── 점수 안내 ──────────────────────────────────────
        hint_used_now = st.session_state.hint_shown.get(number, False)
        earn_pts = pts if not hint_used_now else pts // 2
        st.markdown(
            f"**이 문제 배점:** "
            f'<span class="score-delta-pos">+{earn_pts}점</span> 정답 / '
            f'<span class="score-delta-neg">-{pts//2}점</span> 오답'
            + (" *(힌트 사용으로 획득 점수 50%)*" if hint_used_now else ""),
            unsafe_allow_html=True,
        )

    with col_r:
        # ── 힌트 (클릭해서 열기) ──────────────────────────
        with st.expander("💡 힌트 보기 (클릭 시 점수 반감)", expanded=False):
            if not st.session_state.hint_shown.get(number):
                st.session_state.hint_shown[number] = True
                st.rerun()  # 배점 안내 갱신
            st.success(scenario.get("hint", "제약을 구체적인 숫자·키 이름으로 적어 보세요."))
            st.caption("⚠️ 힌트를 확인했습니다. 이 문제의 획득 점수가 50%로 줄어듭니다.")

        st.markdown("#### 내 프롬프트 (지시문)")
        user_prompt = st.text_area(
            "프롬프트",
            height=180,
            placeholder="LLM에게 보낼 지시문을 작성하세요…",
            key=f"prompt_{number}",
            label_visibility="collapsed",
        )

        if st.button("채점 제출", type="primary", use_container_width=True):
            if not user_prompt.strip():
                st.warning("프롬프트를 입력한 뒤 제출하세요.")
            else:
                hint_used = st.session_state.hint_shown.get(number, False)
                try:
                    from evaluator import build_evaluation

                    active_ids = scenario.get("active_constraints")
                    with st.spinner("채점 중… (첫 실행은 모델 다운로드로 1~2분 걸릴 수 있음)"):
                        engine    = load_engine()
                        diagnosis = engine.diagnose(user_prompt.strip(), constraint_ids=active_ids)
                        evaluation = build_evaluation(
                            diagnosis,
                            scenario_title=scenario["title"],
                            pass_threshold=float(scenario.get("pass_threshold", 60)),
                        )

                    passed      = evaluation["passed"]
                    delta       = sc.calc_score(scenario["level"], passed, hint_used)
                    evaluation["score_delta"]  = delta
                    evaluation["hint_used"]    = hint_used

                    st.session_state["last_evaluation"] = evaluation

                    # DB 기록
                    auth.record_attempt(email, number, passed, delta, hint_used)

                except Exception as exc:
                    st.error(f"채점 오류: {exc}")
                    st.exception(exc)

    # ── 채점 결과 ─────────────────────────────────────────
    if "last_evaluation" in st.session_state:
        ev = st.session_state["last_evaluation"]
        st.markdown("---")
        render_evaluation(ev)
        if ev["passed"]:
            st.balloons()


def render_evaluation(ev: dict) -> None:
    passed = ev["passed"]
    label  = "합격 (AC) ✅" if passed else "불합격 ❌ — 다시 시도"
    delta  = ev.get("score_delta", 0)
    delta_str = (
        f'<span class="score-delta-pos">+{delta}점</span>' if delta > 0
        else f'<span class="score-delta-neg">{delta}점</span>'
    )

    col1, col2 = st.columns([2, 1])
    with col1:
        st.metric("종합 점수", f"{ev['overall_score']:.1f}",
                  delta=f"{ev['grade']}등급 · {label}")
    with col2:
        st.markdown(f"**점수 변화:** {delta_str}", unsafe_allow_html=True)
        if ev.get("hint_used"):
            st.caption("*(힌트 사용 — 획득 점수 50%)*")

    st.write(ev["summary"])

    # GPT-4o 실제 출력 표시
    if ev.get("llm_output"):
        with st.expander("🤖 AI 실제 출력 보기 (GPT-4o가 프롬프트를 실행한 결과)"):
            st.code(ev["llm_output"], language=None)

    st.markdown("#### 채점 상세")
    for row in ev["constraints"]:
        mark = "O" if row["passed"] else "X"
        st.progress(
            min(max(row["score"] / 100.0, 0.0), 1.0),
            text=f"[{mark}] {row['constraint_name']}: {row['score']:.1f}점",
        )
        st.caption(row["feedback"])

    st.markdown("#### 코치 팁")
    for tip in ev["coach_tips"]:
        st.markdown(f"- {tip}")


# ════════════════════════════════════════════════════════════
#  메인
# ════════════════════════════════════════════════════════════
init_session()

if not st.session_state.logged_in:
    render_auth()
    st.stop()

# 로그인 후
try:
    config = get_config()
except FileNotFoundError:
    st.error(f"설정 파일 없음: {CONFIG_PATH}")
    st.stop()

scenarios = normalize_scenarios(config.get("scenarios", []))
if not scenarios:
    st.error("example_data.json에 scenarios가 없습니다.")
    st.stop()

render_sidebar(config)

if st.session_state.view == "solve" and st.session_state.problem_no:
    render_solve(config, scenarios)
else:
    st.session_state.view = "list"
    render_problem_list(config, scenarios)
