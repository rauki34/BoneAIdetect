#!/usr/bin/env python
import os
import sys

# 确保在正确的目录中
os.chdir(r'd:\grauateDesign\backend')
sys.path.insert(0, r'd:\grauateDesign\backend')

from app import app, models

if __name__ == '__main__':
    print(f"Working directory: {os.getcwd()}")
    print(f"Available models: {list(models.keys())}")
    app.run(debug=False, host='127.0.0.1', port=5000)
