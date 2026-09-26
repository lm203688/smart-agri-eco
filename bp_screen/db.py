# -*- coding: utf-8 -*-
"""
三库分离存储：案例库 / 评估记录库 / 规则版本库（SQLite 实现，标准库零依赖）

路径约定：
  AGRI_BP_DB  可覆盖数据库文件绝对路径（测试用临时库时用，避免污染真实数据）
  缺省        bp_screen/data/cases.db —— 放在包内自包含，不写入项目共享的 data/ 目录，
              避免与 env_recipes / feedback_log 等本项目数据混在一起

修：旧版 `_conn()` 只建连接不建表，冷启动（DB 文件不存在）时 any 函数都会抛
    sqlite3.OperationalError: no such table: cases。现在首次连接自动建表 + 灌种子案例，
    幂等，任何入口（MCP / Web / 单测）都能直接调。
"""
import sqlite3, json, time, os

_DB_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.environ.get("AGRI_BP_DB") or os.path.join(_DB_DIR, "cases.db")

_INITIALIZED = False


def _conn():
    d = os.path.dirname(DB_PATH)
    if d:
        os.makedirs(d, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

SCHEMA = """
CREATE TABLE IF NOT EXISTS rule_versions(
  version TEXT PRIMARY KEY, released TEXT, notes TEXT, active INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS cases(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT, category TEXT, is_benchmark INTEGER DEFAULT 0,
  metrics TEXT, outcome TEXT, source TEXT,
  data_quality TEXT DEFAULT 'ok', created REAL
);
CREATE TABLE IF NOT EXISTS assessments(
  id TEXT PRIMARY KEY,
  company_name TEXT DEFAULT '',
  files TEXT DEFAULT '[]',
  rules_version TEXT,
  status TEXT DEFAULT 'running',
  stage TEXT,
  category TEXT,
  category_confidence REAL,
  category_confirmed_by_user INTEGER DEFAULT 0,
  score REAL, grade TEXT,
  report TEXT,
  created REAL,
  finished REAL
);
CREATE TABLE IF NOT EXISTS supplement_files(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  assess_id TEXT, filename TEXT, parsed TEXT, created REAL
);
"""


def init_db():
    """幂等建表 + 灌种子案例与规则版本。可重复调用。"""
    c = _conn()
    c.executescript(SCHEMA)
    c.commit()
    need_seed = c.execute("SELECT COUNT(*) AS n FROM cases").fetchone()["n"] == 0
    c.close()

    # 规则版本：始终登记当前版本，历史版本由 init_db 重复调用时累积
    from . import rules
    c = _conn()
    c.execute("UPDATE rule_versions SET active=0")
    c.execute(
        "INSERT OR IGNORE INTO rule_versions(version, released, notes, active) VALUES(?,?,?,1)",
        (rules.RULES_VERSION, rules.RELEASED, rules.VERSION_HISTORY[-1]))
    c.commit()
    if need_seed:
        from . import seed_cases
        seed_cases.seed()   # 无参，内部走 insert_case
    c.close()
    return True


def ensure_ready():
    """首次调用自动初始化（进程内只跑一次）。任何只读函数都可先调它。"""
    global _INITIALIZED
    if _INITIALIZED:
        return
    if not os.path.exists(DB_PATH):
        init_db()
        _INITIALIZED = True
        return
    c = _conn()
    n = c.execute("SELECT COUNT(*) AS n FROM sqlite_master WHERE type='table'").fetchone()["n"]
    c.close()
    if n == 0:
        init_db()
    _INITIALIZED = True


def execute(sql, params=()):

    ensure_ready()  # 冷启动自动建表+灌种子
    c = _conn()
    c.execute(sql, params)
    c.commit()
    c.close()


def _active_version():

    ensure_ready()  # 冷启动自动建表+灌种子
    c = _conn()
    r = c.execute("SELECT version FROM rule_versions WHERE active=1 ORDER BY released DESC LIMIT 1").fetchone()
    c.close()
    return r["version"] if r else "v0"


def _now_iso():
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def create_assessment(aid, company, files):

    ensure_ready()  # 冷启动自动建表+灌种子
    c = _conn()
    c.execute("INSERT INTO assessments(id, company_name, files, rules_version, status, stage, created) VALUES(?,?,?,?,?,?,?)",
              (aid, company or "", json.dumps(files, ensure_ascii=False), _active_version(),
               "running", json.dumps({"idx": -2, "stage": "排队中", "detail": ""}, ensure_ascii=False), time.time()))
    c.commit()
    c.close()


def update_stage(aid, idx, detail_json):

    ensure_ready()  # 冷启动自动建表+灌种子
    """idx: 0-8 流水线阶段；-1 error"""
    c = _conn()
    status = "error" if idx == -1 else None
    if status:
        c.execute("UPDATE assessments SET stage=?, status=? WHERE id=?", (detail_json, status, aid))
    else:
        c.execute("UPDATE assessments SET stage=? WHERE id=?", (detail_json, aid))
    c.commit()
    c.close()


def set_report(aid, report_json, status=None, score=None, grade=None, category=None, confidence=None):

    ensure_ready()  # 冷启动自动建表+灌种子
    c = _conn()
    sets, vals = ["report=?"], [report_json]
    if status is not None:
        sets.append("status=?"); vals.append(status)
    if score is not None:
        sets.append("score=?"); vals.append(score)
    if grade is not None:
        sets.append("grade=?"); vals.append(grade)
    if category is not None:
        sets.append("category=?"); vals.append(category)
    if confidence is not None:
        sets.append("category_confidence=?"); vals.append(confidence)
    if status in ("done",):
        sets.append("finished=?"); vals.append(time.time())
    vals.append(aid)
    c.execute(f"UPDATE assessments SET {', '.join(sets)} WHERE id=?", vals)
    c.commit()
    c.close()


def get_assessment(aid):

    ensure_ready()  # 冷启动自动建表+灌种子
    c = _conn()
    r = c.execute("SELECT * FROM assessments WHERE id=?", (aid,)).fetchone()
    c.close()
    return dict(r) if r else None


def list_assessments(limit=30):

    ensure_ready()  # 冷启动自动建表+灌种子
    c = _conn()
    rows = c.execute("SELECT id, company_name, category, score, grade, status, created FROM assessments ORDER BY created DESC LIMIT ?",
                     (limit,)).fetchall()
    c.close()
    return [dict(r) for r in rows]


def add_supplement(aid, filename, parsed):

    ensure_ready()  # 冷启动自动建表+灌种子
    c = _conn()
    c.execute("INSERT INTO supplement_files(assess_id, filename, parsed, created) VALUES(?,?,?,?)",
              (aid, filename, json.dumps(parsed, ensure_ascii=False), time.time()))
    c.commit()
    c.close()


def all_cases():

    ensure_ready()  # 冷启动自动建表+灌种子
    c = _conn()
    rows = c.execute("SELECT * FROM cases").fetchall()
    c.close()
    return [dict(r) for r in rows]


def insert_case(name, category, metrics, outcome="verified", is_benchmark=0, source="seed"):

    ensure_ready()  # 冷启动自动建表+灌种子
    c = _conn()
    c.execute("INSERT INTO cases(name, category, is_benchmark, metrics, outcome, source, created) VALUES(?,?,?,?,?,?,?)",
              (name, category, is_benchmark, json.dumps(metrics, ensure_ascii=False), outcome, source, time.time()))
    c.commit()
    c.close()
