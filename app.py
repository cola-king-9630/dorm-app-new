import os
import logging
import sys
from flask import Flask, request, jsonify, render_template
import pg8000
from datetime import datetime, time
import urllib.parse
from urllib.parse import urlparse  # 使用更标准的 urlparse

# 设置详细的日志记录，以便在 Vercel 日志中看到错误信息
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 从环境变量获取 Supabase PostgreSQL 数据库连接字符串
DATABASE_URL = os.environ.get('DATABASE_POSTGRES_URL')
logger.debug(f"DATABASE_URL retrieved: {DATABASE_URL is not None}")  # 日志检查

def get_db_connection():
    """创建并返回数据库连接"""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is not set")
    
    # 使用 urlparse 解析数据库连接字符串（更标准的方式）
    url = urlparse(DATABASE_URL)
    
    # 提取连接参数
    dbname = url.path[1:]  # 去掉路径开头的 '/'
    user = url.username
    password = url.password
    host = url.hostname
    port = url.port or 5432  # 默认 PostgreSQL 端口
    
    logger.debug(f"Connecting to: host={host}, port={port}, dbname={dbname}, user={user}")
    
    try:
        # 使用 pg8000 建立连接
        conn = pg8000.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=dbname,
            ssl_context=True
        )
        logger.debug("Database connection successful")
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise

def init_db():
    """初始化数据库表（如果不存在则创建）"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # 创建记录表
        cur.execute('''
            CREATE TABLE IF NOT EXISTS sleep_records (
                id SERIAL PRIMARY KEY,
                sleep_time TIME NOT NULL,
                record_date DATE NOT NULL UNIQUE, -- 确保同一天只有一条记录
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        cur.close()
        conn.close()
        logger.debug("Database initialization successful")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

@app.route('/')
def index():
    """主页面，返回HTML"""
    logger.debug("Index page requested")
    return render_template('index.html')

@app.route('/api/records', methods=['GET', 'POST'])
def handle_records():
    """处理睡眠记录的获取和提交"""
    logger.debug(f"Records endpoint called with method: {request.method}")
    
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        # 提交新记录
        data = request.get_json()  # 使用 get_json() 方法更安全
        if not data:
            return jsonify({"status": "错误", "message": "无效的JSON数据"}), 400
            
        try:
            sleep_time = data.get('sleep_time')
            record_date = data.get('record_date')
            
            if not sleep_time or not record_date:
                return jsonify({"status": "错误", "message": "缺少必要参数"}), 400
                
            cur.execute(
                "INSERT INTO sleep_records (sleep_time, record_date) VALUES (%s, %s) RETURNING id, sleep_time, record_date",
                (sleep_time, record_date)
            )
            conn.commit()
            record = cur.fetchone()
            cur.close()
            conn.close()
            return jsonify({"status": "记录成功！", "record": {"id": record[0], "sleep_time": str(record[1]), "record_date": record[2].isoformat()}})
        except pg8000.IntegrityError:
            # 处理同一天重复提交的情况
            cur.close()
            conn.close()
            return jsonify({"status": "错误", "message": "今日记录已存在！"}), 400
        except Exception as e:
            logger.error(f"Error inserting record: {e}")
            cur.close()
            conn.close()
            return jsonify({"status": "错误", "message": "服务器错误"}), 500

    else:
        # 获取所有记录
        try:
            cur.execute("SELECT id, sleep_time, record_date FROM sleep_records ORDER BY record_date DESC")
            records = cur.fetchall()
            cur.close()
            conn.close()
            
            records_list = [{"id": r[0], "sleep_time": str(r[1]), "record_date": r[2].isoformat()} for r in records]
            return jsonify(records_list)
        except Exception as e:
            logger.error(f"Error fetching records: {e}")
            cur.close()
            conn.close()
            return jsonify({"status": "错误", "message": "获取记录失败"}), 500

@app.route('/api/stats')
def get_stats():
    """获取统计信息（总记录数、总熬夜时间）"""
    logger.debug("Stats endpoint called")
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT COUNT(*) as total_count FROM sleep_records")
        total_count = cur.fetchone()[0]
        
        cur.execute("SELECT sleep_time FROM sleep_records")
        times = [row[0] for row in cur.fetchall()]
        
        # 计算总熬夜时间（假设23:00后睡觉算熬夜）
        total_late_minutes = 0
        for t in times:
            if isinstance(t, time) and t.hour >= 23:
                total_late_minutes += (t.hour - 23) * 60 + t.minute
        
        cur.close()
        conn.close()
        return jsonify({
            "total_records": total_count,
            "total_late_minutes": total_late_minutes
        })
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        return jsonify({"status": "错误", "message": "获取统计失败"}), 500

# 应用启动时初始化数据库
try:
    init_db()
    logger.info("Application started successfully")
except Exception as e:
    logger.error(f"Application failed to start: {e}")

# Vercel 需要这个变量
app = app
