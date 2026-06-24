"""
auth.py — PromptMaster 이메일 인증 로그인 모듈
SQLite 기반 로컬 사용자 저장소
"""
from __future__ import annotations

import hashlib
import os
import random
import sqlite3
import string
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "users.db"
CODE_TTL = 600  # 인증코드 유효 시간(초)


# ── DB 초기화 ────────────────────────────────────────────
def init_db() -> None:
    with _conn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            email       TEXT PRIMARY KEY,
            password    TEXT NOT NULL,
            created_at  REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS verify_codes (
            email       TEXT PRIMARY KEY,
            code        TEXT NOT NULL,
            expires_at  REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS scores (
            email           TEXT PRIMARY KEY,
            total_score     INTEGER DEFAULT 0,
            solved_count    INTEGER DEFAULT 0,
            hint_used_count INTEGER DEFAULT 0,
            wrong_count     INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS problem_records (
            email       TEXT NOT NULL,
            number      INTEGER NOT NULL,
            passed      INTEGER NOT NULL,
            score_delta INTEGER NOT NULL,
            hint_used   INTEGER NOT NULL,
            attempts    INTEGER DEFAULT 1,
            PRIMARY KEY (email, number)
        );
        """)


def _conn() -> sqlite3.Connection:
    return sqlite3.connect(str(DB_PATH))


def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


# ── 인증 코드 ────────────────────────────────────────────
def generate_code(email: str) -> str:
    code = "".join(random.choices(string.digits, k=6))
    with _conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO verify_codes VALUES (?,?,?)",
            (email, code, time.time() + CODE_TTL),
        )
    return code

import smtplib
from email.mime.text import MIMEText

GMAIL_USER = "ggyu1213@gmail.com"   # 여기 입력
GMAIL_PASS = "vqih taqr bbtd uyfc"        # 여기 입력

def send_code_email(to_email: str, code: str) -> None:
    msg = MIMEText(f"PromptMaster 인증 코드: {code}\n\n10분 내에 입력해 주세요.")
    msg["Subject"] = "[PromptMaster] 이메일 인증 코드"
    msg["From"]    = GMAIL_USER
    msg["To"]      = to_email

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(GMAIL_USER, GMAIL_PASS)
        s.send_message(msg)


def verify_code(email: str, code: str) -> bool:
    with _conn() as con:
        row = con.execute(
            "SELECT code, expires_at FROM verify_codes WHERE email=?", (email,)
        ).fetchone()
    if not row:
        return False
    stored_code, expires_at = row
    if time.time() > expires_at:
        return False
    return stored_code == code.strip()


def delete_code(email: str) -> None:
    with _conn() as con:
        con.execute("DELETE FROM verify_codes WHERE email=?", (email,))


# ── 회원가입 / 로그인 ──────────────────────────────────────
def register(email: str, password: str) -> tuple[bool, str]:
    with _conn() as con:
        exists = con.execute(
            "SELECT 1 FROM users WHERE email=?", (email,)
        ).fetchone()
        if exists:
            return False, "이미 가입된 이메일입니다."
        con.execute(
            "INSERT INTO users VALUES (?,?,?)",
            (email, _hash(password), time.time()),
        )
        con.execute(
            "INSERT OR IGNORE INTO scores VALUES (?,0,0,0,0)", (email,)
        )
    return True, "회원가입 완료"


def login(email: str, password: str) -> tuple[bool, str]:
    with _conn() as con:
        row = con.execute(
            "SELECT password FROM users WHERE email=?", (email,)
        ).fetchone()
    if not row:
        return False, "존재하지 않는 이메일입니다."
    if row[0] != _hash(password):
        return False, "비밀번호가 틀렸습니다."
    return True, "로그인 성공"


def user_exists(email: str) -> bool:
    with _conn() as con:
        return bool(
            con.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone()
        )


# ── 점수 조회 / 기록 ──────────────────────────────────────
def get_score_row(email: str) -> dict:
    with _conn() as con:
        row = con.execute(
            "SELECT total_score, solved_count, hint_used_count, wrong_count "
            "FROM scores WHERE email=?",
            (email,),
        ).fetchone()
    if not row:
        return {"total_score": 0, "solved_count": 0, "hint_used_count": 0, "wrong_count": 0}
    return dict(zip(["total_score", "solved_count", "hint_used_count", "wrong_count"], row))


def get_problem_record(email: str, number: int) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT passed, score_delta, hint_used, attempts "
            "FROM problem_records WHERE email=? AND number=?",
            (email, number),
        ).fetchone()
    if not row:
        return None
    return dict(zip(["passed", "score_delta", "hint_used", "attempts"], row))


def get_all_records(email: str) -> dict[int, dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT number, passed, score_delta, hint_used, attempts "
            "FROM problem_records WHERE email=?",
            (email,),
        ).fetchall()
    return {
        r[0]: {"passed": bool(r[1]), "score_delta": r[2], "hint_used": bool(r[3]), "attempts": r[4]}
        for r in rows
    }


def record_attempt(
    email: str,
    number: int,
    passed: bool,
    score_delta: int,
    hint_used: bool,
) -> None:
    """문제 시도 기록 + 점수 반영. 이미 AC된 문제는 추가 점수 없음."""
    with _conn() as con:
        existing = con.execute(
            "SELECT passed, attempts FROM problem_records WHERE email=? AND number=?",
            (email, number),
        ).fetchone()

        if existing:
            old_passed, attempts = existing
            if old_passed:
                # 이미 맞힌 문제 — 기록만 업데이트
                con.execute(
                    "UPDATE problem_records SET attempts=? WHERE email=? AND number=?",
                    (attempts + 1, email, number),
                )
                return
            # 이전에 틀렸던 문제 재시도
            con.execute(
                "UPDATE problem_records SET passed=?, score_delta=?, hint_used=?, attempts=? "
                "WHERE email=? AND number=?",
                (int(passed), score_delta, int(hint_used), attempts + 1, email, number),
            )
        else:
            con.execute(
                "INSERT INTO problem_records VALUES (?,?,?,?,?,1)",
                (email, number, int(passed), score_delta, int(hint_used)),
            )

        # 점수 테이블 갱신
        if passed:
            con.execute(
                "UPDATE scores SET total_score=total_score+?, solved_count=solved_count+1 "
                "WHERE email=?",
                (score_delta, email),
            )
        else:
            # 오답 감점
            con.execute(
                "UPDATE scores SET total_score=MAX(0, total_score+?), wrong_count=wrong_count+1 "
                "WHERE email=?",
                (score_delta, email),  # score_delta < 0
            )

        if hint_used:
            con.execute(
                "UPDATE scores SET hint_used_count=hint_used_count+1 WHERE email=?",
                (email,),
            )


init_db()
