import asyncio
import sys
import os

# Ensure we can import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.auth_service import create_user
from app.core.log_utils import get_logger

logger = get_logger("tools")

async def main():
    username = input("Enter username (default: admin): ").strip() or "admin"
    role = input("Enter role (admin/ops/dev) [default: admin]: ").strip() or "admin"
    desc = input("Enter description: ").strip()
    
    try:
        print(f"Creating user '{username}' with role '{role}'...")
        user, raw_key = await create_user(username, role, desc)
        print("\n" + "="*50)
        print(f"✅ User Created Successfully!")
        print(f"👤 Username: {user.username}")
        print(f"🔑 API Key:  {raw_key}")
        print("="*50)
        print("⚠️  Please save this key immediately. It cannot be retrieved later!")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
