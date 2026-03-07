#!/usr/bin/env python
"""
重置admin用户密码脚本
用法: python reset_admin.py [新密码]
如果不提供新密码，默认使用 123456
"""
import sys
import os

# 确保在正确的目录中
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from database import db, User
from werkzeug.security import generate_password_hash

def reset_admin_password(new_password='123456'):
    """重置admin用户密码"""
    with app.app_context():
        admin_user = User.query.filter_by(username='admin').first()
        
        if not admin_user:
            # 如果admin用户不存在，创建它
            admin_user = User(
                username='admin',
                password=generate_password_hash(new_password),
                role='admin'
            )
            db.session.add(admin_user)
            print(f"✅ 创建admin用户（密码: {new_password}）")
        else:
            # 更新密码
            admin_user.password = generate_password_hash(new_password)
            print(f"✅ 重置admin用户密码（新密码: {new_password}）")
        
        db.session.commit()
        print(f"✅ 操作完成！")
        print(f"   用户名: admin")
        print(f"   密码: {new_password}")
        print(f"   角色: admin")

if __name__ == "__main__":
    new_password = sys.argv[1] if len(sys.argv) > 1 else '123456'
    reset_admin_password(new_password)
