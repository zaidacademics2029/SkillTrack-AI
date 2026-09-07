import os
import sqlite3
import json
import secrets
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "app.db")


def get_db():
    """Opens a connection to the SQLite file. row_factory lets us access
    columns by name (row['username']) instead of by position (row[1])."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")   # enforce foreign key constraints
    return conn


def now_iso():
    """Consistent timestamp format used everywhere in this project."""
    return datetime.now(timezone.utc).isoformat()


def new_token():
    """A random, URL-safe string used for both login tokens and
    employer-verification links."""
    return secrets.token_urlsafe(24)


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('trainee','developer','employer')),
    api_token TEXT UNIQUE,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS consent_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    consent_given INTEGER NOT NULL,       -- 1 = agreed, 0 = declined
    consent_date TEXT,
    tracking_scope_version TEXT DEFAULT 'v1'
);

CREATE TABLE IF NOT EXISTS trainee_profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    name TEXT, age INTEGER, gender TEXT, phone TEXT,
    known_skills TEXT,                  -- stored as a JSON string, e.g. '["Python","Excel"]'
    desired_domain TEXT,
    desired_scheme TEXT,
    district TEXT,
    prior_experience_months REAL,
    prior_workplace TEXT,
    profile_pic TEXT,
    grade TEXT,                         -- Beginner / Intermediate / Pro
    overall_test_score REAL,
    created_at TEXT,
    employment_status TEXT DEFAULT 'not_placed',
    employment_role TEXT,
    employment_date TEXT,
    employment_location TEXT,
    starting_salary REAL,
    current_salary REAL,
    verification_status TEXT DEFAULT 'unverified',
    last_checked_date TEXT,
    non_placement_reason TEXT
);

CREATE TABLE IF NOT EXISTS job_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_name TEXT,
    industry TEXT,                -- 'IT' or 'Vocational'
    required_skills TEXT          -- JSON list, e.g. '["SQL","Excel","Python"]'
);

CREATE TABLE IF NOT EXISTS training_programs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT,
    level TEXT,                   -- Beginner / Intermediate / Pro
    title TEXT,
    description TEXT,
    created_by INTEGER,           -- which developer/admin created it
    created_at TEXT,
    enroll_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS program_modules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    program_id INTEGER REFERENCES training_programs(id),
    seq INTEGER,                  -- order within the program: 1, 2, 3...
    title TEXT
);

CREATE TABLE IF NOT EXISTS enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    program_id INTEGER REFERENCES training_programs(id),
    status TEXT DEFAULT 'in_progress',    -- in_progress / completed
    started_at TEXT,
    completed_at TEXT,
    consistency_score REAL
);

CREATE TABLE IF NOT EXISTS enrollment_modules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enrollment_id INTEGER REFERENCES enrollments(id),
    module_id INTEGER REFERENCES program_modules(id),
    completed_at TEXT              -- NULL until the trainee marks it done
);

CREATE TABLE IF NOT EXISTS skill_test_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    skill TEXT,
    score REAL,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS certificates_uploaded (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    title TEXT,
    filepath TEXT,
    uploaded_at TEXT
);

CREATE TABLE IF NOT EXISTS issued_certificates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    program_id INTEGER REFERENCES training_programs(id),
    issued_at TEXT,
    filepath TEXT
);

CREATE TABLE IF NOT EXISTS employer_verifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    employer_name_declared TEXT,
    token TEXT UNIQUE,              -- the random string in the verification link
    status TEXT DEFAULT 'pending',  -- pending / confirmed / disputed
    created_at TEXT,
    confirmed_date TEXT
);

CREATE TABLE IF NOT EXISTS follow_ups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    scheduled_date TEXT,
    months_after_placement INTEGER,    -- 3 / 6 / 12
    status TEXT DEFAULT 'pending',     -- pending / responded
    response_status TEXT,              -- still_employed / left_job
    salary_at_check REAL,
    created_at TEXT
);
"""


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


MAHARASHTRA_DISTRICTS = ["Pune", "Mumbai", "Nagpur", "Nashik", "Aurangabad", "Kolhapur"]


def seed_if_empty():
    """Only inserts demo data the very first time — if users already exist,
    this does nothing. Safe to call every time the app starts."""
    conn = get_db()
    user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if user_count > 0:
        conn.close()
        return

    def add_user(username, password, role):
        conn.execute(
            "INSERT INTO users (username, password_hash, role, api_token, created_at) VALUES (?,?,?,?,?)",
            (username, generate_password_hash(password), role, new_token(), now_iso())
        )
        return conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()["id"]

    dev_id = add_user("dev", "dev123", "developer")
    add_user("employer1", "employer123", "employer")

    # --- Job role catalogue: IT + vocational, matching the PS's expected scope ---
    job_roles = [
        ("Data Analyst", "IT", ["SQL", "Excel", "Python", "Statistics", "Data Visualization"]),
        ("Software Developer", "IT", ["Programming", "Data Structures", "Git", "APIs", "Database"]),
        ("ML Engineer", "IT", ["Python", "Machine Learning", "Statistics", "Model Evaluation"]),
        ("Web Developer", "IT", ["HTML/CSS", "JavaScript", "Frontend Framework", "APIs", "Database"]),
        ("Business Analyst", "IT", ["Excel", "SQL", "Communication", "Business Analysis", "Visualization"]),
        ("Electrician", "Vocational", ["Wiring Safety", "Circuit Basics", "Tools Handling", "Safety Compliance", "Customer Service"]),
        ("Tailoring & Garment Making", "Vocational", ["Pattern Making", "Machine Operation", "Fabric Handling", "Finishing", "Quality Check"]),
        ("Hospitality Associate", "Vocational", ["Communication", "Food Safety", "POS Systems", "Customer Service", "Housekeeping Standards"]),
        ("Plumbing", "Vocational", ["Pipefitting", "Fixture Installation", "Safety Compliance", "Tools Handling", "Basic Maths"]),
    ]
    for name, industry, skills in job_roles:
        conn.execute("INSERT INTO job_roles (role_name, industry, required_skills) VALUES (?,?,?)",
                     (name, industry, json.dumps(skills)))

    # --- Training programs: (domain, level, title, description, [modules]) ---
    programs = [
        ("Web Development", "Beginner", "Web Dev Foundations", "HTML, CSS and JavaScript basics.",
         ["HTML Fundamentals", "CSS Styling & Layout", "JavaScript Basics", "Building Your First Page", "Intro to Git"]),
        ("Web Development", "Intermediate", "Full-Stack Fundamentals", "From static pages to working web apps.",
         ["Responsive Design", "JavaScript DOM & Events", "Backend Basics", "Databases & SQL", "Deploying a Web App"]),
        ("Data Science", "Beginner", "Data Science Starter", "Foundations of working with data in Python.",
         ["Python for Data Science", "Pandas Basics", "Data Visualization", "Intro to Statistics", "Excel for Data Cleaning"]),
        ("Data Science", "Intermediate", "Applied Machine Learning", "From clean data to working ML models.",
         ["Exploratory Data Analysis", "Feature Engineering", "Supervised Learning Models", "Model Evaluation", "Mini Project"]),
        ("Software Development", "Beginner", "Programming Foundations", "Learn programming logic from scratch.",
         ["Programming Basics", "Control Structures", "Functions & Arrays", "Intro to Python", "Problem Solving Practice"]),
        ("Software Development", "Intermediate", "Software Engineering Essentials", "Build real applications well.",
         ["Object-Oriented Programming", "Data Structures", "Version Control (Git)", "Testing Basics", "Small Team Project"]),
        ("Electrician", "Beginner", "Electrical Basics Bootcamp", "Core electrical concepts, hands-on.",
         ["Circuit Fundamentals", "Ohm's Law & Power", "Basic Wiring Safety", "Using a Multimeter", "Intro to Electronics"]),
        ("Electrician", "Intermediate", "Applied Electrical Skills", "Practical, job-ready electrical skills.",
         ["Industrial Wiring", "Motors & Control Circuits", "PLC Basics", "Troubleshooting Techniques", "Safety Standards"]),
        ("Tailoring & Garment Making", "Beginner", "Tailoring Foundations", "Core stitching and pattern skills.",
         ["Pattern Making Basics", "Machine Operation", "Fabric Handling", "Basic Stitching", "Finishing Techniques"]),
        ("Hospitality Associate", "Beginner", "Hospitality Service Basics", "Guest-facing service fundamentals.",
         ["Customer Service Basics", "Food Safety", "POS Systems", "Housekeeping Standards", "Communication Skills"]),
        ("Plumbing", "Beginner", "Plumbing Foundations", "Core plumbing and safety skills.",
         ["Pipefitting Basics", "Fixture Installation", "Tools Handling", "Safety Compliance", "Basic Maths for Plumbing"]),
    ]
    for domain, level, title, desc, modules in programs:
        conn.execute(
            "INSERT INTO training_programs (domain, level, title, description, created_by, created_at) VALUES (?,?,?,?,?,?)",
            (domain, level, title, desc, dev_id, now_iso())
        )
        pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        for i, m in enumerate(modules, start=1):
            conn.execute("INSERT INTO program_modules (program_id, seq, title) VALUES (?,?,?)", (pid, i, m))

    conn.commit()

    # --- 12 demo trainees with varied, reproducible employment/verification data ---
    import random
    random.seed(11)   # fixed seed = same demo data every time, for consistent team demos

    domains = ["Web Development", "Data Science", "Electrician", "Software Development",
               "Tailoring & Garment Making", "Hospitality Associate", "Plumbing"]
    names = ["Aditi Sharma", "Rohan Verma", "Priya Nair", "Karan Mehta", "Sneha Iyer",
             "Vikram Rao", "Ananya Das", "Farhan Sheikh", "Meera Pillai", "Arjun Kapoor",
             "Sanjay Patil", "Kavita Joshi"]
    grades = ["Beginner", "Intermediate", "Pro"]
    schemes = ["PMKVY", "NAPS", "DDU-GKY", "JSS", "ITI/CTS"]
    employment_statuses = ["employed_formal", "self_employed", "apprentice", "not_placed"]
    non_placement_reasons = ["still_searching", "relocated", "further_study", "other"]

    all_programs = conn.execute("SELECT id, domain, level FROM training_programs").fetchall()

    for i, name in enumerate(names):
        username = f"trainee{i+1}"
        uid = add_user(username, "trainee123", "trainee")

        conn.execute(
            "INSERT INTO consent_records (user_id, consent_given, consent_date, tracking_scope_version) VALUES (?,?,?,?)",
            (uid, 1, now_iso(), "v1")
        )

        domain = random.choice(domains)
        grade = random.choice(grades)
        district = random.choice(MAHARASHTRA_DISTRICTS)
        matching = [p for p in all_programs if p["domain"] == domain and p["level"] == grade]
        program = random.choice(matching) if matching else random.choice(all_programs)

        emp_status = random.choice(employment_statuses)
        is_placed = emp_status != "not_placed"
        starting_salary = round(random.uniform(12000, 35000), 0) if is_placed else None
        current_salary = round(starting_salary * random.uniform(1.0, 1.25), 0) if is_placed else None
        verification_status = random.choice(["verified", "self_reported", "self_reported"]) if is_placed else "unverified"

        conn.execute("""
            INSERT INTO trainee_profiles
            (user_id, name, age, gender, phone, known_skills, desired_domain, desired_scheme, district,
             prior_experience_months, prior_workplace, grade, overall_test_score, created_at,
             employment_status, employment_role, employment_date, employment_location,
             starting_salary, current_salary, verification_status, last_checked_date, non_placement_reason)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            uid, name, random.randint(19, 30), random.choice(["Male", "Female"]),
            f"9{random.randint(100000000,999999999)}",
            json.dumps(random.sample(["Python", "C", "Web Development", "Excel", "Communication"], 2)),
            domain, random.choice(schemes), district,
            round(random.uniform(0, 12), 1),
            random.choice(["None", "Local shop", "Family business", "Internship"]),
            grade, round(random.uniform(30, 95), 1), now_iso(),
            emp_status, domain if is_placed else None,
            now_iso() if is_placed else None, district if is_placed else None,
            starting_salary, current_salary, verification_status,
            now_iso() if is_placed else None,
            None if is_placed else random.choice(non_placement_reasons)
        ))

        if verification_status == "verified":
            conn.execute("""
                INSERT INTO employer_verifications (user_id, employer_name_declared, token, status, created_at, confirmed_date)
                VALUES (?,?,?,?,?,?)
            """, (uid, f"{domain} Employer Pvt Ltd", new_token(), "confirmed", now_iso(), now_iso()))
        elif verification_status == "self_reported":
            conn.execute("""
                INSERT INTO employer_verifications (user_id, employer_name_declared, token, status, created_at)
                VALUES (?,?,?,?,?)
            """, (uid, f"{domain} Employer Pvt Ltd", new_token(), "pending", now_iso()))

        if is_placed and random.random() > 0.3:
            months = random.choice([3, 6, 12])
            responded = random.random() > 0.2
            conn.execute("""
                INSERT INTO follow_ups (user_id, scheduled_date, months_after_placement, status, response_status, salary_at_check, created_at)
                VALUES (?,?,?,?,?,?,?)
            """, (
                uid, now_iso(), months, "responded" if responded else "pending",
                random.choice(["still_employed", "still_employed", "left_job"]) if responded else None,
                current_salary if responded else None, now_iso()
            ))

        status = random.choice(["in_progress", "completed", "completed", "in_progress"])
        started = datetime.now(timezone.utc) - timedelta(days=random.randint(10, 60))
        conn.execute("""
            INSERT INTO enrollments (user_id, program_id, status, started_at, completed_at, consistency_score)
            VALUES (?,?,?,?,?,?)
        """, (
            uid, program["id"], status, started.isoformat(),
            (started + timedelta(days=random.randint(5, 30))).isoformat() if status == "completed" else None,
            round(random.uniform(40, 95), 1)
        ))
        eid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        mods = conn.execute("SELECT id FROM program_modules WHERE program_id=? ORDER BY seq", (program["id"],)).fetchall()
        n_complete = len(mods) if status == "completed" else random.randint(0, len(mods) - 1)
        for j in range(n_complete):
            completed_time = started + timedelta(days=j * random.randint(2, 6))
            conn.execute(
                "INSERT INTO enrollment_modules (enrollment_id, module_id, completed_at) VALUES (?,?,?)",
                (eid, mods[j]["id"], completed_time.isoformat())
            )
        conn.execute("UPDATE training_programs SET enroll_count = enroll_count + 1 WHERE id=?", (program["id"],))

    conn.commit()
    conn.close()
