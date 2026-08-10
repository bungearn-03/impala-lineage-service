# Impala Lineage Service

บริการสำหรับสแกน metadata ของ Impala / Hive Metastore และประกอบสร้าง SQL
lineage (ทั้งระดับตารางและระดับคอลัมน์) จากนิยามของ view/query พร้อมเว็บ UI
สำหรับเรียกดูฐานข้อมูลที่สแกนแล้วและแสดง lineage เป็นกราฟ

ตัวบริการเชื่อมต่อกับ Impala และ/หรือ Hive Metastore เพื่อค้นหาฐานข้อมูล
ตาราง และ view จากนั้นแปลง (parse) SQL ที่อยู่หลัง view เพื่อหา lineage edge
(โดยจะ fallback ไปใช้ AI ช่วยวิเคราะห์เมื่อการ parse แบบ static ไม่สามารถ
สรุปผลระดับคอลัมน์ได้อย่างมั่นใจ) แล้วเก็บผลลงใน Postgres เพื่อให้ frontend
ดึงไปแสดงเป็นไดอะแกรมแบบโต้ตอบได้

## เริ่มต้นใช้งานแบบเร็ว (Quick start)

วิธีที่เร็วที่สุดจาก `git clone` มาจนแอปทำงานได้ — ทุกขั้นตอนด้านล่างรันผ่าน
Docker ทั้งหมด ไม่ต้องลง Python/Node บนเครื่องเอง ดูหัวข้อ "การติดตั้งบนเครื่อง
(Local setup)" ด้านล่างสำหรับขั้นตอนแบบละเอียด (รวมถึงแนวทางที่ไม่ผ่าน Docker
สำหรับรัน Alembic/scripts ตรงบนเครื่อง) และหัวข้อ "ตัวแปรสภาพแวดล้อมที่สำคัญ"
สำหรับค่าอื่นๆที่ควรตั้งเพิ่ม

```bash
# จากที่ไหนก็ได้ที่เก็บโปรเจกต์
git clone <repo-url> && cd impala-lineage-service
cp backend/.env.example backend/.env
```

```powershell
git clone <repo-url>; cd impala-lineage-service
Copy-Item backend\.env.example backend\.env
```

เปิดไฟล์ `backend/.env` แล้วตั้งค่าอย่างน้อย `SECRET_KEY` ให้เป็นค่าจริง

```bash
docker compose up --build -d
docker compose exec -w /migrations backend alembic -c alembic.ini upgrade head
```

```powershell
docker compose up --build -d
docker compose exec -w /migrations backend alembic -c alembic.ini upgrade head
```

- Frontend: http://localhost:5173
- Backend: http://localhost:9000

`-d` คือรันทุก service แบบ background เพื่อให้ terminal ว่างสำหรับรันคำสั่ง
migration ด้านบนต่อได้ทันที ดู log ทีหลังด้วย `docker compose logs -f`
ขั้นตอน migration นี้**จำเป็นต้องรัน** และ**ไม่ได้ถูกรันอัตโนมัติ**ตอน
container เริ่มทำงาน (ดูเหตุผลในหัวข้อ "การติดตั้งบนเครื่อง") — ถ้าลืมขั้นตอนนี้
จะเจอ error `relation "connections" does not exist` (หรือชื่อ table อื่นๆ
ในทำนองเดียวกัน) ตอนที่ frontend เรียก API ครั้งแรก

## สถาปัตยกรรม (Architecture)

FastAPI backend (`backend/app/`) จัดโครงสร้างเป็นเลเยอร์ แต่ละเลเยอร์มี
หน้าที่รับผิดชอบเฉพาะทางของตัวเอง:

- **`connectors/`** - `BaseConnector` นิยาม interface (`list_databases`,
  `list_objects`, `get_columns`, `get_ddl`, `get_view_definition`, ...)
  ที่ถูก implement โดย `ImpalaConnector` และ `HiveMetastoreConnector` ทำให้
  ส่วนอื่นของแอปเรียกใช้ backend ตัวไหนก็ได้สลับกันได้โดยไม่ต้องสนใจว่า
  `Connection` นั้นตั้งค่าให้ใช้ตัวไหนอยู่
- **`metadata/`** - ตัว loader ที่สั่งให้ connector ค้นหา object, column, และ
  นิยามของ view แล้วบันทึกเป็นแถวข้อมูล `DataObject`/`Column`
  (`object_scanner.py`, `schema_loader.py`, `view_definition_loader.py`)
- **`parsers/`** - วิเคราะห์ SQL แบบ static บนพื้นฐานของ `sqlglot`: ปรับ
  ความต่างของ dialect ให้เป็นมาตรฐาน (`sql_normalizer.py`), หาความสัมพันธ์
  lineage ระดับตาราง (`table_lineage.py`) และระดับคอลัมน์
  (`column_lineage.py`), สกัดกราฟของ join (`join_extractor.py`), และขยาย
  lineage แบบวนซ้ำผ่าน nested view (`recursive_resolver.py`)
- **`ai/`** - wrapper แบบเบาๆที่แยกส่วนไว้เฉพาะสำหรับเรียก Anthropic SDK
  (`ai_client.py`, `prompts.py`, `response_schema.py`, `result_validator.py`)
  ใช้เป็นแค่ fallback เมื่อ parser ที่ใช้ sqlglot ไม่สามารถสรุป column
  lineage ได้อย่างมั่นใจเท่านั้น จะถูกปิดใช้งานทั้งหมดถ้าไม่ได้ตั้งค่า
  `ANTHROPIC_API_KEY`
- **`graph/`** - แปลง lineage edge ที่บันทึกไว้ให้เป็นกราฟแบบ `networkx`
  และจัดรูปแบบสำหรับตัวแสดงผล Cytoscape.js ของ frontend
  (`graph_builder.py`, `graph_filter.py`, `cytoscape_formatter.py`)
  ตั้งใจแยกออกจาก ORM และ Pydantic schema เพื่อให้ unit test ได้ด้วย dict
  ธรรมดา
- **`repositories/`** - เลเยอร์เดียวที่คุยกับ SQLAlchemy ตรงๆ:
  `object_repository.py` (upsert ของ DataObject/Column), `lineage_repository.py`
  (บันทึก LineageEdge + จัดรูปแบบ raw-dict ให้ `graph/`), `job_repository.py`
  (วงจรชีวิตของ ScanJob)
- **`workers/`** - รัน scan job แบบ background ผ่าน `BackgroundTasks` ของ
  FastAPI เพื่อไม่ให้การสแกน Impala/Metastore ที่ใช้เวลานานไปบล็อก request
  ของ API: `scan_worker.py` (สแกน metadata) และ `lineage_worker.py`
  (สแกน lineage รวมถึงตัดสินใจว่าจะ fallback ไปใช้ AI ต่อ view หรือไม่)
- **`api/`** - FastAPI router ที่เปิด endpoint สำหรับ connections, metadata,
  scan job, และ lineage/diagram ภายใต้ `/api/v1` ประกอบรวมกันใน
  `app/main.py`

ฝั่ง Vite/React frontend (`frontend/`) เป็น single-page app แยกออกมาต่างหาก
ที่คุยกับ backend ผ่าน HTTP API `/api/v1` และแสดงกราฟ lineage ด้วย
Cytoscape.js

## โครงสร้างไดเรกทอรี (Directory layout)

```
impala-lineage-service/
├── backend/
│   ├── app/
│   │   ├── ai/             # AI fallback ที่ใช้ Anthropic ช่วยหา lineage
│   │   ├── api/             # FastAPI router (/api/v1/...)
│   │   ├── connectors/     # ตัวเชื่อมต่อ Impala / Hive Metastore
│   │   ├── core/           # config, database session, security, logging
│   │   ├── graph/          # สร้างและจัดรูปแบบกราฟ lineage
│   │   ├── metadata/       # สแกน/โหลด metadata
│   │   ├── models/         # SQLAlchemy models (ตรงกับ Alembic migration)
│   │   ├── parsers/        # แปลง SQL lineage ด้วย sqlglot
│   │   ├── repositories/    # เลเยอร์ query ของ SQLAlchemy
│   │   ├── schemas/        # Pydantic request/response schema
│   │   ├── workers/         # scan/lineage job แบบ background
│   │   └── main.py          # ประกอบรวม FastAPI app
│   ├── scripts/
│   │   └── seed_connections.py  # ลงทะเบียน Connection จากตัวแปร IMPALA_*
│   ├── tests/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example        # ก็อปปี้ไปเป็น .env
├── database/
│   └── migrations/         # Alembic environment (อยู่ข้าง backend/ ไม่ได้อยู่ข้างใน)
│       ├── alembic.ini
│       ├── env.py
│       ├── script.py.mako
│       └── versions/
│           └── 0001_initial_schema.py
├── frontend/                # Vite/React SPA (มี Dockerfile ของตัวเอง ไม่ได้พูดถึงในนี้)
├── docker-compose.yml
└── README.md
```

## การติดตั้งบนเครื่อง (Local setup)

### 1. ตั้งค่า environment ของ backend

```bash
# รันจาก root ของ repo
cp backend/.env.example backend/.env
```

```powershell
# เทียบเท่าบน PowerShell
Copy-Item backend\.env.example backend\.env
```

เปิด `backend/.env` แล้วกรอกค่าจริง อย่างน้อยต้องมี `SECRET_KEY` ตั้งค่า
`ANTHROPIC_API_KEY` ด้วยถ้าต้องการเปิดใช้ AI-assisted lineage fallback
(ดูหมายเหตุด้านล่าง)

### 2. เริ่มแค่ Postgres ก่อน

```bash
docker compose up -d postgres
```

```powershell
docker compose up -d postgres
```

รอจนสถานะเป็น healthy (เช็คด้วย `docker compose ps`)

### 3. รัน migration ครั้งแรก

Alembic environment อยู่ที่ `database/migrations/` ซึ่งอยู่ข้างๆ `backend/`
(sibling directory) ดังนั้น `env.py` จะเพิ่ม `backend/` เข้า `sys.path`
ให้เองไม่ต้อง install package `app` เพิ่ม แต่ยังต้องมี Python dependency
ชุดเดียวกันติดตั้งอยู่ (อย่างน้อย `alembic` และทุกอย่างที่
`app.core.config`/`app.models` import) และต้องเชื่อมต่อ `DATABASE_URL`
ได้จากที่ที่รันคำสั่งนี้ (`localhost:5432` ถ้ารันตรงบนเครื่อง host เข้าไปยัง
port ที่ container `postgres` เปิดไว้ ซึ่งเป็นค่า default ของ
`backend/.env.example`)

ต้องใช้ **Python 3.10 ขึ้นไป** (ตัว Docker image เองใช้ 3.11) — เพราะ
`networkx==3.3` ใน `requirements.txt` ตัด support Python 3.9 ไปแล้ว ถ้าใช้
Python เก่ากว่านี้ `pip install` จะ error
`No matching distribution found for networkx==3.3` บน Windows ที่ใช้
pyenv-win ให้สร้าง venv โดยระบุเวอร์ชัน Python ตรงๆ ไปเลย ไม่ต้องพึ่ง
`python` shim ที่อาจยังไม่อัปเดตตาม `pyenv local` ที่สลับไว้:
`& "$env:USERPROFILE\.pyenv\pyenv-win\versions\<3.10.x ขึ้นไป>\python.exe" -m venv .venv`

รันจากไดเรกทอรี `backend/` โดยมี virtualenv ที่ install
`backend/requirements.txt` แล้ว จากนั้น `cd` เข้าไปใน
`database/migrations/` ก่อนเรียก `alembic` (เหตุผลเดียวกับที่อธิบายไว้ใน
กล่องหมายเหตุด้านล่าง: `script_location = .` ตีความเทียบกับ CWD ที่รันคำสั่ง
ไม่ใช่ตำแหน่งไฟล์ `alembic.ini` เอง ถ้าเรียกจาก `backend/` ตรงๆด้วย path
`-c ../database/migrations/alembic.ini` จะ error
`Can't find Python file .\env.py` เหมือนกัน):

```bash
# รันจาก backend/
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd ../database/migrations
alembic -c alembic.ini upgrade head
cd ../../backend
```

```powershell
# รันจาก backend/
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd ..\database\migrations
alembic -c alembic.ini upgrade head
cd ..\..\backend
```

`env.py` อ่านค่า `DATABASE_URL` ผ่าน `app.core.config.get_settings()`
(คืออ่านจาก `backend/.env` หรือ process environment จริง) — ค่า
`sqlalchemy.url` ใน `alembic.ini` เองตั้งใจเว้นว่างไว้

> โปรเจกต์นี้ไม่ได้รัน migration อัตโนมัติจาก entrypoint ของ backend
> container `database/migrations` ถูก mount แบบ read-only เข้า container
> `backend` ที่ `/migrations` เพื่อความสะดวก ดังนั้นจะรันคำสั่งเดียวกันนี้
> จากใน container ที่กำลังทำงานอยู่แทน local venv ก็ได้:
> `docker compose exec -w /migrations backend alembic -c alembic.ini upgrade head`
> (ทำแบบไหนก็ได้ผลเหมือนกัน — ที่เลือกให้เป็นขั้นตอนที่ต้องรันเองแทนการฝังไว้ใน
> `CMD` ก็เพื่อไม่ให้ container restart แล้วรัน migration ซ้ำแบบไม่รู้ตัว และ
> เพื่อไม่ให้ migration ที่ล้มเหลวไป crash ตัว API process) ค่า `-w /migrations`
> สำคัญมาก: `script_location = .` ใน `alembic.ini` จะถูกตีความเทียบกับ
> ไดเรกทอรีที่รันคำสั่งอยู่ ไม่ใช่เทียบกับตำแหน่งไฟล์ `.ini` เอง ถ้ารันจาก
> working directory เริ่มต้นของ container (`/app`) จะ error
> `Can't find Python file ./env.py`

### 4. เปิดใช้งานทั้งระบบ

```bash
docker compose up --build
```

```powershell
docker compose up --build
```

- Backend: http://localhost:9000
- Frontend: http://localhost:5173

> **URL ของ API ฝั่ง frontend ถูกฝังไว้ตอน build time** `VITE_API_BASE_URL`
> เป็นตัวแปรระดับ build time ของ Vite ไม่ใช่ runtime — Dockerfile ของ service
> `frontend` จะคอมไพล์ค่านี้เข้าไปใน static JS bundle เลย `docker-compose.yml`
> ส่งค่านี้เป็น build arg (`http://localhost:9000/api/v1` ตรงกับ port ของ
> backend ด้านบน) ดังนั้น `docker compose up --build` จะได้ค่านี้ไปใช้เองอยู่แล้ว
> ถ้าเปลี่ยน host port ของ backend อีก ต้องอัปเดต build arg นี้ด้วยแล้ว build
> ใหม่ด้วย `docker compose build --build-arg VITE_API_BASE_URL=... frontend`
> — การตั้งเป็น environment variable ของ container ตอน `docker compose up`
> จะไม่มีผลอะไรกับ bundle ที่ build ไปแล้ว

### 5. (ทางเลือก) Seed ข้อมูลเชื่อมต่อ Impala จริง

แทนที่จะเพิ่ม `Connection` แรกด้วยมือผ่าน API/UI สามารถตั้งค่า
`IMPALA_HOST`/`IMPALA_PORT`/`IMPALA_USER`/`IMPALA_PASS` (และถ้าต้องการ
`IMPALA_CONNECTION_NAME`/`IMPALA_DEFAULT_DATABASE`/`IMPALA_AUTH_MECHANISM`/
`IMPALA_USE_SSL`) ใน `backend/.env` แล้วรัน:

```bash
# รันจาก backend/ โดยเปิด venv จากขั้นตอนที่ 3 ไว้
python scripts/seed_connections.py
```

```powershell
python scripts\seed_connections.py
```

คำสั่งนี้ idempotent (รันซ้ำจะอัปเดตแถวเดิมตาม `IMPALA_CONNECTION_NAME`
ไม่สร้างซ้ำ) และเข้ารหัสรหัสผ่านด้วยวิธีเดียวกับที่ API ใช้ก่อนบันทึก
มันอ่านแค่ตัวแปร `IMPALA_*` เท่านั้น — จะไม่ปรากฏใน git history หรือใน
`.env.example` ด้วยค่าจริงเด็ดขาด เพราะ `backend/.env` ถูกกันไว้ใน
`.gitignore` อยู่แล้ว

## ตัวแปรสภาพแวดล้อมที่สำคัญ (Key environment variables)

ตัวแปรทั้งหมดนี้ถูกอ่านโดย `backend/app/core/config.py::Settings` จาก
`backend/.env` (ดู `backend/.env.example`):

| ตัวแปร | ค่า default | ใช้ทำอะไร |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://lineage:lineage@localhost:5432/lineage` | connection string ของ SQLAlchemy ถูก override ใน `docker-compose.yml` ให้ชี้ไปที่ hostname ของ service `postgres` |
| `SECRET_KEY` | *(ค่า placeholder สำหรับ dev เปลี่ยนก่อนใช้จริง)* | ใช้สร้าง Fernet key สำหรับเข้ารหัส credential ของ connection ที่บันทึกไว้ |
| `API_KEY` | *(ไม่มี)* | ถ้าตั้งค่าไว้ ทุก request ของ API ต้องส่งค่านี้มาใน header `X-API-Key` |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | รายการ origin ของ frontend ที่อนุญาต (เป็น JSON array) |
| `ANTHROPIC_API_KEY` | *(ไม่มี)* | เปิดใช้งาน AI-assisted lineage fallback ดูหมายเหตุด้านล่าง |
| `ANTHROPIC_MODEL` | `claude-sonnet-5` | โมเดลที่ใช้สำหรับ AI lineage fallback |
| `AI_LINEAGE_FALLBACK_ENABLED` | `true` | สวิตช์หลักของ fallback นี้ ยังต้องมี `ANTHROPIC_API_KEY` ด้วย |
| `DEFAULT_QUERY_TIMEOUT_SECONDS` | `120` | timeout ที่ใช้กับ query ของ Impala/Metastore ระหว่างสแกน |
| `SCAN_MAX_CONCURRENT_OBJECTS` | `8` | จำนวน object สูงสุดที่สแกนพร้อมกันต่อ scan job |
| `APP_NAME`, `ENVIRONMENT`, `LOG_LEVEL` | | ข้อมูลทั่วไปของแอป / การตั้งค่า logging |

### AI-assisted lineage fallback

เมื่อ parser แบบ static ที่ใช้ `sqlglot` ไม่สามารถสรุปผล column-level
lineage ของ view ได้อย่างมั่นใจ บริการนี้สามารถเรียก Claude แบบ tool-use
หนึ่งครั้งเพื่อช่วยเติมส่วนที่ขาดได้ (เป็นทางเลือก ไม่บังคับ): ถ้าไม่ได้ตั้งค่า
`ANTHROPIC_API_KEY` ไว้ ระบบจะข้าม fallback นี้ไปเงียบๆ (ไม่ error) ไม่ว่า
`AI_LINEAGE_FALLBACK_ENABLED` จะเป็นอะไรก็ตาม — การหา lineage จะหยุดอยู่
แค่เท่าที่ static parser หาได้เท่านั้น

## หมายเหตุ / ส่วนที่ทำต่างจาก spec แบบตรงตัว

- Alembic migration เขียนโค้ดจำลอง (hand-encode) พฤติกรรมจริงของ column
  type `Enum(SomePyEnum)` ของ SQLAlchemy ไว้ตรงๆ: โดย default แล้วมันจะเก็บ
  **ชื่อ** (name) ของ enum member ของ Python ไม่ใช่ค่า `.value` ของมัน
  เรื่องนี้มีผลแค่กับ `ConnectionType` เท่านั้น (ค่าที่เก็บจริงคือ
  `IMPALA`/`HIVE_METASTORE` ไม่ใช่ `.value` ตัวพิมพ์เล็ก
  `impala`/`hive_metastore`) — enum ตัวอื่นๆทุกตัวชื่อกับค่าบังเอิญเป็น
  string เดียวกันอยู่แล้ว ทั้งเจ็ด Postgres enum type ถูกสร้างด้วย
  `create_type=False` ตรงๆ และถูกสร้าง/ลบเองใน `upgrade()`/`downgrade()`
  เพื่อไม่ให้เจอ error ประเภทซ้ำ (duplicate-type)
- service `backend` ใน `docker-compose.yml` ไม่มี `healthcheck` ทำให้
  `depends_on: backend` ของ `frontend` รอแค่ container เริ่มทำงานเท่านั้น
  ไม่ได้รอจนกว่า API จะพร้อมรับ request จริงๆ
