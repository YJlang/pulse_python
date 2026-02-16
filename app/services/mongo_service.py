"""
MongoDB 연결 및 데이터 저장 서비스
"""
import os
from pymongo import MongoClient
from app.utils.logger import get_logger

logger = get_logger(__name__)

class MongoService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoService, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def initialize(self):
        if self.initialized:
            return
            
        # 로컬 MongoDB 연결 (기본 포트 27017)
        # 실제 배포 시에는 환경변수에서 MONGO_URI를 가져와야 합니다.
        mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
        db_name = os.getenv("MONGO_DB_NAME", "pulse_db")
        
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name] # DB 이름: pulse_db
        self.collection = self.db["analysis_results"] # 컬렉션: analysis_results
        
        self.initialized = True
        logger.info("✅ [MongoService] Connected to MongoDB (pulse_db.analysis_results)")

    def save_result(self, task_id: str, data: dict):
        """
        분석 결과를 MongoDB에 저장합니다.
        """
        if not self.initialized:
            self.initialize()
            
        try:
             # task_id를 _id로 사용하거나 별도 필드로 저장
            document = data.copy()
            document["task_id"] = task_id
            
            self.collection.insert_one(document)
            logger.info(f"💾 [MongoService] Result saved for task {task_id}")
            return True
        except Exception as e:
            logger.error(f"❌ [MongoService] Failed to save result: {e}")
            return False
