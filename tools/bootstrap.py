import sys
import os
import subprocess
import argparse
from urllib.parse import urlparse

# 确保能导入 app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import config
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

def parse_db_url(url):
    """
    解析 DATABASE_URL: postgresql+asyncpg://user:pass@host:port/dbname
    返回 (user, password, host, port, dbname)
    """
    # 移除 driver 部分 (+asyncpg) 以便标准 urlparse 解析
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "")
    
    parsed = urlparse(url)
    dbname = parsed.path.lstrip('/')
    return parsed.username, parsed.password, parsed.hostname, parsed.port or 5432, dbname

def check_and_create_db():
    db_url = config.get("DATABASE_URL")
    if not db_url or "sqlite" in db_url:
        print(f"Skipping PG check for non-PG URL: {db_url}")
        return True

    try:
        user, password, host, port, dbname = parse_db_url(db_url)
    except Exception as e:
        print(f"Error parsing DATABASE_URL: {e}")
        return False

    print(f"Checking PostgreSQL at {host}:{port}...")

    try:
        # 连接到默认 postgres 库
        con = psycopg2.connect(
            dbname="postgres",
            user=user,
            password=password,
            host=host,
            port=port
        )
        con.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = con.cursor()

        # 检查是否存在
        cur.execute(f"SELECT 1 FROM pg_catalog.pg_database WHERE datname = '{dbname}'")
        exists = cur.fetchone()

        if not exists:
            print(f"Database '{dbname}' does not exist. Creating...")
            cur.execute(f"CREATE DATABASE {dbname}")
            print(f"✅ Database '{dbname}' created.")
        else:
            print(f"✅ Database '{dbname}' already exists.")

        cur.close()
        con.close()
        return True

    except psycopg2.OperationalError as e:
        # 尝试解码错误信息
        error_msg = str(e)
        try:
            if hasattr(e, 'pgerror') and e.pgerror:
                error_msg = e.pgerror
        except:
            pass
        print(f"❌ Connection failed: {error_msg}")
        return False
    except UnicodeDecodeError as e:
        # 专门处理 Windows 下 GBK 错误信息导致的解码失败
        try:
            # e.object 包含原始字节流
            raw_bytes = e.object
            decoded_msg = raw_bytes.decode('gbk', errors='replace')
            print(f"❌ Connection failed (Decoded): {decoded_msg}")
        except Exception:
            print(f"❌ Connection failed (Raw): {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {repr(e)}")
        return False

def run_migrations():
    print("Running Alembic migrations...")
    # 检查是否有 versions 文件夹，如果没有初始化过，可能需要先 revision
    # 但通常我们假设代码库里已经有了 versions（或者这是第一次初始化）
    
    # 尝试运行 upgrade head
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"❌ Migration failed:\n{result.stderr}")
        # 如果是因为没有 migration 脚本，尝试生成一个初始脚本
        if "Can't locate revision identifier" in result.stderr or "No such revision" in result.stderr: 
             print("No migrations found. Generating initial migration...")
             gen_result = subprocess.run([sys.executable, "-m", "alembic", "revision", "--autogenerate", "-m", "init"], capture_output=True, text=True)
             if gen_result.returncode == 0:
                 print("✅ Initial migration generated. Retrying upgrade...")
                 result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], capture_output=True, text=True)
             else:
                 print(f"❌ Failed to generate migration:\n{gen_result.stderr}")
                 return False
    
    if result.returncode == 0:
        print("✅ Database schema is up to date.")
        return True
    else:
        print(f"❌ Migration failed:\n{result.stderr}")
        return False

if __name__ == "__main__":
    print("=== Procurator Database Bootstrap ===")
    
    if not check_and_create_db():
        print("💥 Bootstrap failed at DB connection step.")
        sys.exit(1)
        
    if not run_migrations():
        print("💥 Bootstrap failed at Migration step.")
        sys.exit(1)
        
    print("✨ Bootstrap completed successfully!")
