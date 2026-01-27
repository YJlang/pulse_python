import logging
import sys

# =========================================================
# 🪵 로거 설정 (Logging Utility)
# =========================================================

def get_logger(name: str):
    """
    애플리케이션 전역에서 사용할 로거를 생성합니다.
    콘솔에 로그를 출력하도록 설정되어 있습니다.
    
    Args:
        name: 로거 이름 (보통 __name__ 사용)
    """
    logger = logging.getLogger(name)
    
    # 이미 핸들러가 설정되어 있다면 중복 추가 방지
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        # 콘솔 출력을 위한 핸들러
        handler = logging.StreamHandler(sys.stdout)
        
        # 로그 포맷 설정 (시간 - 레벨 - 로거명 - 메시지)
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s [%(name)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
    return logger
