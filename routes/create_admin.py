# create_admin.py
import os
import sys
import bcrypt

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.operations import create_admin, get_admin_by_username

def main():
    admin_username = os.getenv('INITIAL_ADMIN_USERNAME', 'admin')
    admin_password = os.getenv('INITIAL_ADMIN_PASSWORD', 'admin123')
    
    # Check if admin exists
    if get_admin_by_username(admin_username):
        print(f"Admin user '{admin_username}' already exists.")
        return
    
    # Create admin
    hashed_password = bcrypt.hashpw(admin_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    create_admin(admin_username, hashed_password)
    
    print(f"Admin user '{admin_username}' created successfully.")

if __name__ == '__main__':
    main()
